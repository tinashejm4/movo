from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Contact, Customer, OTP


class CustomerOtpAuthTests(APITestCase):
	def test_otp_creation_creates_or_refreshes_expiry(self):
		phone_number = "0771234567"

		OTP.objects.create(
			username=phone_number,
			otp_code="000000",
			expiry_time=timezone.now() - timedelta(minutes=1),
		)

		response = self.client.post(reverse("customer_otp"), {"phone_number": phone_number}, format="json")

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		otp = OTP.objects.get(username=phone_number)
		self.assertEqual(len(response.data["otp"]), 6)
		self.assertEqual(otp.otp_code, response.data["otp"])
		self.assertGreater(otp.expiry_time, timezone.now())

	def test_customer_register_with_valid_otp_returns_tokens(self):
		phone_number = "0777654321"

		otp_response = self.client.post(reverse("customer_otp"), {"phone_number": phone_number}, format="json")
		self.assertEqual(otp_response.status_code, status.HTTP_201_CREATED)

		register_response = self.client.post(
			reverse("customer_register"),
			{"phone_number": phone_number, "otp_code": otp_response.data["otp"]},
			format="json",
		)

		self.assertEqual(register_response.status_code, status.HTTP_200_OK)
		self.assertIn("access", register_response.data)
		self.assertIn("refresh", register_response.data)

		user = User.objects.get(username=phone_number)
		self.assertTrue(user.check_password("Pass@123"))
		self.assertTrue(Customer.objects.filter(user=user).exists())
		self.assertTrue(Contact.objects.filter(user=user, phone_number=phone_number).exists())
		self.assertFalse(OTP.objects.filter(username=phone_number).exists())

	def test_customer_login_with_valid_otp_returns_tokens(self):
		phone_number = "0770000000"
		User.objects.create_user(username=phone_number, password="Pass@123")

		otp_response = self.client.post(reverse("customer_otp"), {"phone_number": phone_number}, format="json")
		self.assertEqual(otp_response.status_code, status.HTTP_201_CREATED)

		login_response = self.client.post(
			reverse("customer_token_obtain_pair"),
			{"phone_number": phone_number, "otp_code": otp_response.data["otp"]},
			format="json",
		)

		self.assertEqual(login_response.status_code, status.HTTP_200_OK)
		self.assertIn("access", login_response.data)
		self.assertIn("refresh", login_response.data)
		self.assertFalse(OTP.objects.filter(username=phone_number).exists())
