from django.test import TestCase

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.intracity.models import Package, PackageStatus
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
