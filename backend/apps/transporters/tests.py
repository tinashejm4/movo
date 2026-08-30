from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


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
