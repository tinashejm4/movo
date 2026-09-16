from django.test import TestCase

from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.intracity.models import Package, PackageStatus
from apps.users.models import Branch, Biker, City, Customer, Staff


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
