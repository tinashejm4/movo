from django.test import TestCase

from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from PIL import Image

from apps.intracity.models import Package, PackageStatus
from apps.bookkeeping.models import Account, Expense, ExpenseAccount, LedgerEntry, Receipt
from apps.users.models import Branch, Biker, City, Customer, Staff
from apps.transporters.models import BikerDailySession, DriverShiftException


class DeliveryMetricsViewTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="metrics-admin")
		branch = Branch.objects.create(name="Main", address="Main street")
		Staff.objects.create(user=self.user, branch=branch, position="Manager")

		sender_user = User.objects.create_user(username="metrics-sender")
		receiver_user = User.objects.create_user(username="metrics-receiver")
		biker_user = User.objects.create_user(username="metrics-biker")
		self.sender = Customer.objects.create(user=sender_user)
		self.receiver = Customer.objects.create(user=receiver_user)
		self.biker = Biker.objects.create(user=biker_user)
		self.city = City.objects.create(name="Metrics City")

	def create_package(self, added_at, assigned_at=None, delivered_at=None):
		package = Package.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			city=self.city,
			biker=self.biker if assigned_at else None,
			pickup_address="Pickup",
			dropoff_address="Dropoff",
			sender_code="111111",
			receiver_code="222222",
			assigned_at=assigned_at,
			delivered_at=delivered_at,
		)
		Package.objects.filter(pk=package.pk).update(added_at=added_at)
		return package

	def test_returns_metrics_for_requested_date_range(self):
		target = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
		self.create_package(target)
		self.create_package(target, target + timedelta(hours=1))
		self.create_package(target, target + timedelta(hours=1), target + timedelta(hours=2))
		cancelled = self.create_package(target)
		cancelled_status = PackageStatus.objects.create(
			package=cancelled, status="Cancelled"
		)
		PackageStatus.objects.filter(pk=cancelled_status.pk).update(
			updated_at=target + timedelta(hours=3)
		)
		self.create_package(target - timedelta(days=1))

		self.client.force_authenticate(user=self.user)
		response = self.client.get(
			reverse("admin_delivery_metrics"),
			{"start_date": target.date(), "end_date": target.date()},
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(
			response.data,
			{
				"start_date": target.date().isoformat(),
				"end_date": target.date().isoformat(),
				"interval": "daily",
				"delivery_orders_added": [{"date": target.date().isoformat(), "value": 4}],
				"delivery_orders_assigned": [{"date": target.date().isoformat(), "value": 2}],
				"delivery_orders_completed": [{"date": target.date().isoformat(), "value": 1}],
				"delivery_orders_cancelled": [{"date": target.date().isoformat(), "value": 1}],
			},
		)

	def test_defaults_to_today_and_validates_dates(self):
		self.client.force_authenticate(user=self.user)

		response = self.client.get(reverse("admin_delivery_metrics"))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["start_date"], timezone.localdate().isoformat())
		self.assertEqual(response.data["end_date"], timezone.localdate().isoformat())

		invalid = self.client.get(
			reverse("admin_delivery_metrics"), {"start_date": "not-a-date"}
		)
		self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

		reversed_dates = self.client.get(
			reverse("admin_delivery_metrics"),
			{"start_date": "2026-09-02", "end_date": "2026-09-01"},
		)
		self.assertEqual(reversed_dates.status_code, status.HTTP_400_BAD_REQUEST)

# Create your tests here.


class BikerStatisticsViewTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="biker-statistics-admin")
		branch = Branch.objects.create(name="Main", address="Main street")
		Staff.objects.create(user=self.user, branch=branch, position="Manager")
		self.active_biker = Biker.objects.create(
			user=User.objects.create_user(username="on-shift")
		)
		self.outside_shift_biker = Biker.objects.create(
			user=User.objects.create_user(username="outside-shift")
		)
		self.inactive_biker = Biker.objects.create(
			user=User.objects.create_user(username="off-shift")
		)
		today = timezone.localdate()
		BikerDailySession.objects.create(
			biker=self.active_biker,
			date=today,
			start_time=timezone.now(),
			is_active=True,
		)
		BikerDailySession.objects.create(
			biker=self.outside_shift_biker,
			date=today,
			start_time=timezone.now(),
			is_active=True,
		)
		BikerDailySession.objects.create(
			biker=self.inactive_biker,
			date=today,
			start_time=timezone.now(),
			is_active=False,
		)

	@patch("apps.adminportal.views.bikers_views.shift_allows_work", side_effect=[True, False])
	@patch(
		"apps.adminportal.views.bikers_views.effective_shift",
		return_value={"is_open": True},
	)
	def test_counts_current_active_shifts_and_treats_others_as_inactive(
		self, _effective_shift, _shift_allows_work
	):
		self.client.force_authenticate(user=self.user)

		response = self.client.get(reverse("biker_statistics_view"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(
			response.data,
			{"total_bikers": 3, "active_bikers": 1, "inactive_bikers": 2},
		)


class DriverShiftExceptionOverviewTests(APITestCase):
	def setUp(self):
		self.staff_user = User.objects.create_user(username="shift-overview-staff", first_name="Shift", last_name="Manager")
		branch = Branch.objects.create(name="Shift Branch", address="Main street")
		Staff.objects.create(user=self.staff_user, branch=branch, position="Manager")
		self.first_biker = Biker.objects.create(user=User.objects.create_user(username="driver-one"))
		self.second_user = User.objects.create_user(username="driver-two", first_name="Taylor", last_name="Driver")
		self.second_biker = Biker.objects.create(user=self.second_user)

	def test_requires_staff_authentication(self):
		url = reverse("admin_driver_shift_exception_overview")
		self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)
		self.client.force_authenticate(user=User.objects.create_user(username="not-staff"))
		self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

	def test_returns_all_drivers_exceptions_with_expected_fields(self):
		DriverShiftException.objects.create(
			biker=self.first_biker,
			date=timezone.localdate() + timedelta(days=1),
			is_open=False,
			start_time=None,
			end_time=None,
		)
		DriverShiftException.objects.create(
			biker=self.second_biker,
			date=timezone.localdate() + timedelta(days=2),
			is_open=True,
			start_time="09:00",
			end_time="15:00",
		)
		self.client.force_authenticate(user=self.staff_user)

		response = self.client.get(reverse("admin_driver_shift_exception_overview"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data), 2)
		self.assertEqual(
			set(response.data[0]),
			{"biker_user_id", "biker_name", "date", "is_open", "start_time", "end_time"},
		)
		self.assertEqual(response.data[0]["biker_user_id"], self.first_biker.user_id)
		self.assertEqual(response.data[0]["biker_name"], "driver-one")
		self.assertEqual(response.data[1]["biker_name"], "Taylor Driver")


class AccountExpenseViewsTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="expense-staff")
		branch = Branch.objects.create(name="Expense Branch", address="Main street")
		Staff.objects.create(user=self.user, branch=branch, position="Manager")
		self.account = Account.objects.create(name="Expense account", currency="USD")
		self.other_account = Account.objects.create(name="Other account", currency="USD")
		self.expense_type = ExpenseAccount.objects.create(name="Supplies")
		self.client.force_authenticate(user=self.user)

	def test_creates_expense_for_user_and_records_ledger_entry(self):
		response = self.client.post(
			reverse("create_expense_view"),
			{
				"account_id": self.account.id,
				"expense_type_id": self.expense_type.id,
				"amount": "12.50",
				"supplier": "Supplier",
				"description": "Pens",
			},
			format="multipart",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		expense = Expense.objects.get(pk=response.data["expense_id"])
		self.assertEqual(expense.added_by, self.user)
		self.assertEqual(expense.account, self.account)
		self.assertEqual(expense.expense_type, self.expense_type)
		self.assertEqual(expense.ledger_entry.transaction_type, "expense")
		self.assertEqual(str(expense.ledger_entry.amount), "-12.50")

	def test_rejects_non_positive_and_invalid_amounts(self):
		for amount in ("0", "-1", "NaN", "abc"):
			with self.subTest(amount=amount):
				response = self.client.post(
					reverse("create_expense_view"),
					{"account_id": self.account.id, "expense_type_id": self.expense_type.id, "amount": amount},
					format="multipart",
				)
				self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertFalse(Expense.objects.exists())

	def test_creates_expense_with_receipt(self):
		with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
			response = self.client.post(
				reverse("create_expense_view"),
				{
					"account_id": self.account.id,
					"expense_type_id": self.expense_type.id,
					"amount": "5.00",
					"image": SimpleUploadedFile("receipt.png", b"receipt image", content_type="image/png"),
				},
				format="multipart",
			)
			self.assertEqual(response.status_code, status.HTTP_200_OK)
			expense = Expense.objects.get(pk=response.data["expense_id"])
			self.assertTrue(Receipt.objects.filter(expense=expense).exists())
			list_response = self.client.get(reverse("list_expenses_view", kwargs={"account_id": self.account.id}))
			self.assertTrue(list_response.data["expenses"][0]["has_image"])

	def test_lists_only_selected_account_with_inclusive_dates_and_receipt(self):
		today = timezone.localdate()
		expense = Expense.objects.create(account=self.account, expense_type=self.expense_type, amount=3, added_by=self.user)
		Receipt.objects.create(expense=expense, image="receipts/test.png")
		outside = Expense.objects.create(account=self.account, expense_type=self.expense_type, amount=4)
		Expense.objects.filter(pk=outside.pk).update(actual_date=timezone.now() - timedelta(days=3))
		Expense.objects.create(account=self.other_account, expense_type=self.expense_type, amount=5)
		url = reverse("list_expenses_view", kwargs={"account_id": self.account.id})

		response = self.client.get(url, {"start_date": today.isoformat(), "end_date": today.isoformat()})
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data["expenses"]), 1)
		self.assertEqual(response.data["expenses"][0]["id"], expense.id)
		self.assertEqual(response.data["expenses"][0]["added_by"], self.user.username)
		self.assertTrue(response.data["expenses"][0]["has_image"])

		response = self.client.get(url)
		self.assertEqual({item["id"] for item in response.data["expenses"]}, {expense.id, outside.id})
		self.assertFalse(next(item for item in response.data["expenses"] if item["id"] == outside.id)["has_image"])

	def test_rejects_invalid_date_ranges_and_missing_account(self):
		url = reverse("list_expenses_view", kwargs={"account_id": self.account.id})
		for params in (
			{"start_date": "2026-01-01"},
			{"start_date": "invalid", "end_date": "2026-01-01"},
			{"start_date": "2026-01-02", "end_date": "2026-01-01"},
		):
			with self.subTest(params=params):
				self.assertEqual(self.client.get(url, params).status_code, status.HTTP_400_BAD_REQUEST)
		missing = reverse("list_expenses_view", kwargs={"account_id": 999999})
		self.assertEqual(self.client.get(missing).status_code, status.HTTP_404_NOT_FOUND)

	def test_receipt_upload_and_authenticated_image_view(self):
		expense = Expense.objects.create(account=self.account, expense_type=self.expense_type, amount=3)
		url = reverse("expense_receipt_view", kwargs={"account_id": self.account.id, "expense_id": expense.id})
		wrong_account_url = reverse("expense_receipt_view", kwargs={"account_id": self.other_account.id, "expense_id": expense.id})
		image_data = BytesIO()
		Image.new("RGB", (2, 2), "red").save(image_data, format="PNG")

		def upload():
			return SimpleUploadedFile("receipt.png", image_data.getvalue(), content_type="image/png")

		with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
			self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
			self.assertEqual(self.client.post(wrong_account_url, {"image": upload()}, format="multipart").status_code, status.HTTP_404_NOT_FOUND)
			self.assertEqual(self.client.post(url, {}, format="multipart").status_code, status.HTTP_400_BAD_REQUEST)
			bad_image = SimpleUploadedFile("bad.png", b"not an image", content_type="image/png")
			self.assertEqual(self.client.post(url, {"image": bad_image}, format="multipart").status_code, status.HTTP_400_BAD_REQUEST)
			response = self.client.post(url, {"image": upload()}, format="multipart")
			self.assertEqual(response.status_code, status.HTTP_201_CREATED)
			self.assertEqual(self.client.post(url, {"image": upload()}, format="multipart").status_code, status.HTTP_409_CONFLICT)
			self.assertEqual(self.client.get(wrong_account_url).status_code, status.HTTP_404_NOT_FOUND)
			response = self.client.get(url)
			self.assertEqual(response.status_code, status.HTTP_200_OK)
			self.assertEqual(response["Content-Type"], "image/png")
			self.assertEqual(b"".join(response.streaming_content), image_data.getvalue())
			self.client.force_authenticate(user=None)
			self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

	def test_bulk_import_posts_historical_expenses_and_recalculates_balances(self):
		existing = Expense.objects.create(account=self.account, expense_type=self.expense_type, amount=10, added_by=self.user)
		existing_time = timezone.now() - timedelta(days=1)
		Expense.objects.filter(pk=existing.pk).update(actual_date=existing_time)
		LedgerEntry.objects.filter(pk=existing.ledger_entry_id).update(actual_date=existing_time)
		date = (timezone.localdate() - timedelta(days=3)).strftime("%d/%m/%Y")
		url = reverse("bulk_expenses_view", kwargs={"account_id": self.account.id})
		payload = [
			{"id": "external-1", "Date": date, "type": "supplies", "Supplier": "Shop", "description": "Pens", "amount": "5.25"},
			{"id": "external-2", "Date": date, "type": "New Type", "Supplier": "Shop", "amount": 2},
		]

		response = self.client.post(url, payload, format="json")
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data["imported"], 2)
		self.assertEqual(ExpenseAccount.objects.filter(name__iexact="supplies").count(), 1)
		self.assertTrue(ExpenseAccount.objects.filter(name="New Type").exists())
		entries = list(LedgerEntry.objects.filter(account=self.account).order_by("actual_date", "pk"))
		self.assertEqual([entry.running_balance for entry in entries], [Decimal("-5.25"), Decimal("-7.25"), Decimal("-17.25")])
		self.assertEqual(Decimal(str(self.account.get_balance())), Decimal("-17.25"))
		list_url = reverse("list_expenses_view", kwargs={"account_id": self.account.id})
		iso_date = (timezone.localdate() - timedelta(days=3)).isoformat()
		result = self.client.get(list_url, {"start_date": iso_date, "end_date": iso_date})
		self.assertEqual(len(result.data["expenses"]), 2)
		self.assertEqual(self.client.post(url, payload, format="json").status_code, status.HTTP_409_CONFLICT)
		other_url = reverse("bulk_expenses_view", kwargs={"account_id": self.other_account.id})
		self.assertEqual(self.client.post(other_url, payload, format="json").status_code, status.HTTP_409_CONFLICT)
		self.assertEqual(Expense.objects.filter(account=self.account).count(), 3)

	def test_bulk_import_rejects_bad_rows_without_partial_writes(self):
		url = reverse("bulk_expenses_view", kwargs={"account_id": self.account.id})
		base = {"id": "one", "date": "29/5/2026", "type": "new class", "supplier": "Shop", "amount": "2.00"}
		for invalid in (
			{**base, "id": "two", "date": "invalid"},
			{**base, "id": "two", "amount": "2.001"},
			{**base, "id": "two", "amount": "-2"},
			{**base, "id": "one"},
			{**base, "id": ""},
			{**base, "id": "two", "date": "01/01/9999"},
		):
			with self.subTest(invalid=invalid):
				response = self.client.post(url, [base, invalid], format="json")
				self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
				self.assertFalse(Expense.objects.exists())
				self.assertFalse(ExpenseAccount.objects.filter(name="new class").exists())
		self.client.force_authenticate(user=None)
		self.assertEqual(self.client.post(url, [base], format="json").status_code, status.HTTP_401_UNAUTHORIZED)
