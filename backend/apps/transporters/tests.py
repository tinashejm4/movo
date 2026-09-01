from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APITestCase

from apps.bookkeeping.models import Account, IntracitySale
from apps.intracity.models import Invoice, Package, PackageStatus
from apps.users.models import Biker, City, Customer, Suburb

from .models import BikerDailySession
from .services import free_drivers_and_close_packages


class TestAssignPendingPackagesEndpointTests(APITestCase):
	@patch("apps.transporters.views.assign_pending_packages")
	def test_triggers_assignment_without_authentication(self, assign_packages):
		assign_packages.return_value = {
			"message": "Pending packages assigned successfully",
			"assigned_count": 1,
			"unassigned_count": 0,
			"assigned_packages": [],
		}

		response = self.client.post(reverse("test_assign_pending_packages"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data, assign_packages.return_value)
		assign_packages.assert_called_once_with()


class FreeDriversTestEndpointTests(APITestCase):
	def setUp(self):
		self.admin = User.objects.create_user(
			username="reset-admin",
			password="Pass@123",
			is_staff=True,
		)
		self.biker_user = User.objects.create_user(username="reset-driver")
		self.biker = Biker.objects.create(user=self.biker_user)
		sender_user = User.objects.create_user(username="reset-sender")
		receiver_user = User.objects.create_user(username="reset-receiver")
		self.sender = Customer.objects.create(user=sender_user)
		self.receiver = Customer.objects.create(user=receiver_user)
		self.city = City.objects.create(name="Reset City")

	def create_assigned_package(self, current_status):
		package = Package.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			city=self.city,
			biker=self.biker,
			pickup_address="Pickup",
			dropoff_address="Dropoff",
			sender_code="111111",
			receiver_code="222222",
			assigned_at=timezone.now(),
		)
		PackageStatus.objects.create(package=package, status=current_status)
		return package

	def test_requires_staff_authentication(self):
		url = reverse("test_free_drivers")

		self.assertEqual(
			self.client.post(url).status_code,
			status.HTTP_401_UNAUTHORIZED,
		)
		self.client.force_authenticate(user=self.biker_user)
		self.assertEqual(
			self.client.post(url).status_code,
			status.HTTP_403_FORBIDDEN,
		)

	def test_frees_all_bikers_and_closes_active_packages(self):
		pending = self.create_assigned_package("Pending")
		in_transit = self.create_assigned_package("In Transit")
		delivered = self.create_assigned_package("Delivered")
		self.client.force_authenticate(user=self.admin)

		response = self.client.post(reverse("test_free_drivers"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(
			response.data,
			{
				"message": "Drivers freed and assigned packages closed",
				"freed_driver_assignments": 3,
				"delivered_packages": 1,
				"cancelled_packages": 1,
			},
		)
		for package in (pending, in_transit, delivered):
			package.refresh_from_db()
			self.assertIsNone(package.biker_id)
			self.assertIsNone(package.assigned_at)
		self.assertIsNotNone(in_transit.delivered_at)
		self.assertEqual(
			PackageStatus.objects.filter(package=pending)
			.order_by("-updated_at", "-pk")
			.first()
			.status,
			"Cancelled",
		)
		self.assertEqual(
			PackageStatus.objects.filter(package=in_transit)
			.order_by("-updated_at", "-pk")
			.first()
			.status,
			"Delivered",
		)
		self.assertEqual(
			PackageStatus.objects.filter(package=delivered).count(),
			1,
		)

	def test_service_is_idempotent_after_assignments_are_freed(self):
		package = self.create_assigned_package("Assigned")

		first_result = free_drivers_and_close_packages()
		second_result = free_drivers_and_close_packages()

		self.assertEqual(first_result["cancelled_packages"], 1)
		self.assertEqual(second_result["freed_driver_assignments"], 0)
		self.assertEqual(
			PackageStatus.objects.filter(package=package, status="Cancelled").count(),
			1,
		)


class BikerDailySessionEndpointTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="session-driver",
			password="Pass@123",
		)
		self.biker = Biker.objects.create(user=self.user)
		self.url = reverse("activate_deactivate")

	def test_get_requires_authentication(self):
		response = self.client.get(self.url)

		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

	def test_get_returns_inactive_when_driver_has_no_session_today(self):
		self.client.force_authenticate(user=self.user)

		response = self.client.get(self.url)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data, {"is_biker_activated": False})
		self.assertFalse(BikerDailySession.objects.filter(biker=self.biker).exists())

	def test_get_returns_current_driver_session_state(self):
		BikerDailySession.objects.create(
			biker=self.biker,
			date=timezone.now().date(),
			start_time=timezone.now(),
			is_active=True,
		)
		self.client.force_authenticate(user=self.user)

		response = self.client.get(self.url)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data, {"is_biker_activated": True})

	def test_patch_creates_driver_session_with_requested_state(self):
		self.client.force_authenticate(user=self.user)

		response = self.client.patch(
			self.url,
			{"is_biker_activated": True},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data, {"is_biker_activated": True})
		self.assertTrue(
			BikerDailySession.objects.get(
				biker=self.biker,
				date=timezone.now().date(),
			).is_active
		)

	def test_patch_updates_session_idempotently(self):
		session = BikerDailySession.objects.create(
			biker=self.biker,
			date=timezone.now().date(),
			start_time=timezone.now(),
			is_active=True,
		)
		self.client.force_authenticate(user=self.user)

		for _ in range(2):
			response = self.client.patch(
				self.url,
				{"is_biker_activated": False},
				format="json",
			)
			self.assertEqual(response.status_code, status.HTTP_200_OK)
			self.assertEqual(response.data, {"is_biker_activated": False})

		session.refresh_from_db()
		self.assertFalse(session.is_active)
		self.assertEqual(
			BikerDailySession.objects.filter(
				biker=self.biker,
				date=timezone.now().date(),
			).count(),
			1,
		)

	def test_post_is_not_allowed(self):
		self.client.force_authenticate(user=self.user)

		response = self.client.post(
			self.url,
			{"is_biker_activated": True},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class BikerSalesAndOrdersEndpointTests(APITestCase):
	def setUp(self):
		self.biker_user = User.objects.create_user(
			username="sales-driver",
			password="Pass@123",
		)
		self.biker = Biker.objects.create(user=self.biker_user)
		self.account = Account.objects.create(
			name="Sales driver cash",
			owner=self.biker_user,
			currency="USD",
		)
		sender_user = User.objects.create_user(username="sales-sender")
		receiver_user = User.objects.create_user(username="sales-receiver")
		self.sender = Customer.objects.create(user=sender_user)
		self.receiver = Customer.objects.create(user=receiver_user)
		self.city = City.objects.create(name="Harare")
		self.pickup_area = Suburb.objects.create(
			city=self.city,
			name="Avondale",
			x_pos=Decimal("1.000"),
			y_pos=Decimal("1.000"),
		)
		self.dropoff_area = Suburb.objects.create(
			city=self.city,
			name="Borrowdale",
			x_pos=Decimal("2.000"),
			y_pos=Decimal("2.000"),
		)
		self.client.force_authenticate(user=self.biker_user)

	def create_order(
		self,
		amount,
		payment_method="Cash",
		delivered=False,
		package_status=None,
	):
		package = Package.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			city=self.city,
			biker=self.biker,
			pickup_area=self.pickup_area,
			pickup_address="1 Pickup Road",
			dropoff_area=self.dropoff_area,
			dropoff_address="2 Dropoff Road",
			sender_code="111111",
			receiver_code="222222",
			delivered_at=timezone.now() if delivered else None,
		)
		PackageStatus.objects.create(
			package=package,
			status=package_status or ("Delivered" if delivered else "In Transit"),
		)
		invoice = Invoice.objects.create(
			package=package,
			amount=amount,
			payment_method=payment_method,
			is_paid=delivered,
		)
		return package, invoice

	def test_order_summary_includes_slug_and_first_collection_time(self):
		package, _ = self.create_order(
			Decimal("12.50"),
			package_status="Pending",
		)
		first_collection = PackageStatus.objects.create(
			package=package,
			status="In Transit",
		)
		second_collection = PackageStatus.objects.create(
			package=package,
			status="In Transit",
		)
		first_collected_at = timezone.now() - timedelta(hours=2)
		second_collected_at = timezone.now() - timedelta(hours=1)
		PackageStatus.objects.filter(pk=first_collection.pk).update(
			updated_at=first_collected_at
		)
		PackageStatus.objects.filter(pk=second_collection.pk).update(
			updated_at=second_collected_at
		)

		response = self.client.get(reverse("get_orders"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		order = response.data["orders"][0]
		self.assertEqual(order["slug"], package.slug)
		self.assertEqual(order["collected_at"], first_collected_at)

	def test_order_summary_returns_null_when_package_was_not_collected(self):
		self.create_order(Decimal("10.00"), package_status="Assigned")

		response = self.client.get(reverse("get_orders"))

		self.assertIsNone(response.data["orders"][0]["collected_at"])

	def test_order_summary_normalizes_payment_methods(self):
		payment_methods = [
			("Cash", "cash"),
			("Ecocash", "card"),
			("PaynowEcocash", "card"),
			(None, "card"),
			("BankTransfer", "card"),
		]
		expected_by_package_id = {}
		for index, (stored_method, expected_method) in enumerate(payment_methods):
			package, _ = self.create_order(
				Decimal("10.00") + index,
				payment_method=stored_method,
			)
			expected_by_package_id[package.id] = expected_method

		response = self.client.get(reverse("get_orders"))

		actual_by_package_id = {
			order["package_id"]: order["payment_method"]
			for order in response.data["orders"]
		}
		self.assertEqual(actual_by_package_id, expected_by_package_id)

	def test_order_summary_normalizes_all_driver_statuses(self):
		status_values = {
			"Pending": "pending",
			"Assigned": "assigned",
			"In Transit": "in_transit",
			"Delivered": "delivered",
			"Cancelled": "cancelled",
		}
		expected_by_package_id = {}
		for index, (stored_status, expected_status) in enumerate(
			status_values.items()
		):
			package, _ = self.create_order(
				Decimal("20.00") + index,
				package_status=stored_status,
			)
			expected_by_package_id[package.id] = expected_status

		response = self.client.get(reverse("get_orders"))

		actual_by_package_id = {
			order["package_id"]: order["latest_status"]
			for order in response.data["orders"]
		}
		self.assertEqual(actual_by_package_id, expected_by_package_id)

	def test_daily_sales_returns_recorded_cash_collections(self):
		_, cash_invoice = self.create_order(Decimal("12.50"))
		self.create_order(Decimal("30.00"), payment_method="PaynowEcocash")
		IntracitySale.objects.create(
			account=self.account,
			invoice=cash_invoice,
			amount=12.50,
		)

		response = self.client.get(reverse("get_sales"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["total_sales"], Decimal("12.50"))
		self.assertEqual(len(response.data["sales"]), 1)
		self.assertEqual(response.data["sales"][0]["payment_method"], "Cash")
		self.assertEqual(response.data["sales"][0]["collected_at"], timezone.localdate())

	def test_order_cash_collected_uses_sale_records_not_delivery_state(self):
		_, collected_invoice = self.create_order(Decimal("12.50"))
		self.create_order(Decimal("20.00"), delivered=True)
		IntracitySale.objects.create(
			account=self.account,
			invoice=collected_invoice,
			amount=12.50,
		)

		response = self.client.get(reverse("get_orders"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["total_orders"], 2)
		self.assertEqual(response.data["cash_collected"], Decimal("12.50"))
		cash_by_amount = {
			order["amount"]: order["cash_collected"]
			for order in response.data["orders"]
		}
		self.assertEqual(cash_by_amount[Decimal("12.50")], Decimal("12.50"))
		self.assertEqual(cash_by_amount[Decimal("20.00")], Decimal("0.00"))

	def test_endpoints_default_to_today_and_accept_an_inclusive_date_range(self):
		_, today_invoice = self.create_order(Decimal("10.00"))
		IntracitySale.objects.create(
			account=self.account,
			invoice=today_invoice,
			amount=10.00,
		)
		historical_package, historical_invoice = self.create_order(Decimal("25.00"))
		historical_sale = IntracitySale.objects.create(
			account=self.account,
			invoice=historical_invoice,
			amount=25.00,
		)
		historical_date = timezone.localdate() - timedelta(days=7)
		Package.objects.filter(pk=historical_package.pk).update(
			added_at=timezone.now() - timedelta(days=7)
		)
		IntracitySale.objects.filter(pk=historical_sale.pk).update(
			added_at=historical_date
		)

		default_sales = self.client.get(reverse("get_sales"))
		default_orders = self.client.get(reverse("get_orders"))

		self.assertEqual(default_sales.data["total_sales"], Decimal("10.00"))
		self.assertEqual(default_orders.data["total_orders"], 1)
		self.assertEqual(default_orders.data["cash_collected"], Decimal("10.00"))

		params = {
			"start_date": historical_date.isoformat(),
			"end_date": historical_date.isoformat(),
		}
		ranged_sales = self.client.get(reverse("get_sales"), params)
		ranged_orders = self.client.get(reverse("get_orders"), params)

		self.assertEqual(ranged_sales.status_code, status.HTTP_200_OK)
		self.assertEqual(ranged_sales.data["total_sales"], Decimal("25.00"))
		self.assertEqual(ranged_orders.status_code, status.HTTP_200_OK)
		self.assertEqual(ranged_orders.data["total_orders"], 1)
		self.assertEqual(ranged_orders.data["cash_collected"], Decimal("25.00"))

	def test_endpoints_reject_invalid_or_reversed_date_ranges(self):
		for endpoint_name in ("get_sales", "get_orders"):
			with self.subTest(endpoint=endpoint_name, case="invalid"):
				response = self.client.get(
					reverse(endpoint_name),
					{"start_date": "not-a-date"},
				)
				self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

			with self.subTest(endpoint=endpoint_name, case="reversed"):
				response = self.client.get(
					reverse(endpoint_name),
					{"start_date": "2026-08-10", "end_date": "2026-08-01"},
				)
				self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
