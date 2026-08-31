from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Biker

from .models import BikerDailySession


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
