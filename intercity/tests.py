from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import IntracityOrder


class IntracityInitiationTests(APITestCase):
	def test_initiation_creates_order_and_returns_mapping_payload(self):
		payload = {
			"pickup_location": "Avondale, Harare",
			"dropoff_location": "Borrowdale, Harare",
			"sender_name": "Tariro M",
			"sender_phone": "0771000001",
			"receiver_name": "Nyasha K",
			"receiver_phone": "0771000002",
			"receiver_other_details": "Blue gate house",
			"payment_stage": "dropoff",
			"payment_mode": "cash",
		}

		response = self.client.post(reverse("intracity_initiation"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertIn("to_sender", response.data)
		self.assertIn("to_biker", response.data)
		self.assertIn("to_receiver", response.data)
		self.assertTrue(response.data["system"]["saved"])

		package_id = response.data["system"]["package_id"]
		order = IntracityOrder.objects.get(package_id=package_id)
		self.assertEqual(order.sender_phone, payload["sender_phone"])
		self.assertEqual(order.receiver_phone, payload["receiver_phone"])
		self.assertEqual(len(order.receiver_otp), 6)
