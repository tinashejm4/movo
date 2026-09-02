from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Biker, Contact, Customer, OTP, ProfileImage


class CustomerOtpAuthTests(APITestCase):
    def test_otp_creation_creates_or_refreshes_expiry(self):
        phone_number = "0771234567"

        OTP.objects.create(
            username=phone_number,
            otp_code="000000",
            expiry_time=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.post(
            reverse("customer_otp"), {"phone_number": phone_number}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        otp = OTP.objects.get(username=phone_number)
        self.assertEqual(len(response.data["otp"]), 6)
        self.assertEqual(otp.otp_code, response.data["otp"])
        self.assertGreater(otp.expiry_time, timezone.now())

    def test_customer_register_with_valid_otp_returns_tokens(self):
        phone_number = "0777654321"

        otp_response = self.client.post(
            reverse("customer_otp"), {"phone_number": phone_number}, format="json"
        )
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
        self.assertTrue(
            Contact.objects.filter(user=user, phone_number=phone_number).exists()
        )
        self.assertFalse(OTP.objects.filter(username=phone_number).exists())

    def test_customer_login_with_valid_otp_returns_tokens(self):
        phone_number = "0770000000"
        User.objects.create_user(username=phone_number, password="Pass@123")

        otp_response = self.client.post(
            reverse("customer_otp"), {"phone_number": phone_number}, format="json"
        )
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


class LogoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="logout-user", password="Pass@123"
        )
        refresh = RefreshToken.for_user(self.user)
        self.refresh = str(refresh)
        self.access = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_logout_blacklists_refresh_token(self):
        logout_response = self.client.post(
            reverse("token_logout"),
            {"refresh": self.refresh},
            format="json",
        )

        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertEqual(logout_response.data["message"], "Logged out successfully")

        refresh_response = self.client.post(
            reverse("staff_token_refresh"),
            {"refresh": self.refresh},
            format="json",
        )
        self.assertIn(
            refresh_response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_logout_requires_refresh_token(self):
        response = self.client.post(reverse("token_logout"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_requires_authentication(self):
        self.client.credentials()
        response = self.client.post(
            reverse("token_logout"),
            {"refresh": self.refresh},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CustomerProfileEditTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="0777654321",
            password="Pass@123",
            first_name="Alice",
            last_name="Moyo",
        )
        self.customer = Customer.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

    def test_customer_can_update_existing_name_fields(self):
        response = self.client.patch(
            reverse("customer_profile-detail", kwargs={"pk": self.customer.pk}),
            {"first_name": "Alicia", "last_name": "Moyo-Smith"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Alicia")
        self.assertEqual(self.user.last_name, "Moyo-Smith")
        self.assertEqual(response.data["first_name"], "Alicia")
        self.assertEqual(response.data["last_name"], "Moyo-Smith")


class DriverProfileTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="0771234567",
            password="Pass@123",
            first_name="Test",
            last_name="Driver",
        )
        self.biker = Biker.objects.create(user=self.user)
        Contact.objects.create(user=self.user, phone_number="771234567")
        ProfileImage.objects.create(user=self.user)

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse("driver_profile"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_returns_authenticated_driver(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(reverse("driver_profile"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "first_name": "Test",
                "last_name": "Driver",
                "username": "0771234567",
                "phone_number": "0771234567",
                "profile_image": "/media/profile_pics/profile_default.png",
                "joined_on": self.biker.date_joined,
            },
        )
