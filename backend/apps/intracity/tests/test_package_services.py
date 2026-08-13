from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import City, Contact, Customer, Suburb

from ..models import Price
from ..services.customer_provisioning import resolve_or_create_customer
from ..services.package_notifications import (
    build_package_booking_message,
    send_package_booking_sms,
)
from ..services.package_pricing import calculate_package_price


class CustomerProvisioningServiceTests(TestCase):
    def test_resolve_or_create_customer_accepts_integer_phone_number(self):
        customer = resolve_or_create_customer(771000002, "nyasha kamba")

        self.assertEqual(customer.user.username, "771000002")
        self.assertTrue(
            Contact.objects.filter(
                user=customer.user,
                phone_number="771000002",
            ).exists()
        )

    def test_resolve_or_create_customer_normalizes_phone_and_name(self):
        customer = resolve_or_create_customer("0771000002", "nyasha kamba")

        self.assertEqual(customer.user.username, "771000002")
        self.assertEqual(customer.user.first_name, "Nyasha")
        self.assertEqual(customer.user.last_name, "Kamba")
        self.assertTrue(
            Contact.objects.filter(
                user=customer.user,
                phone_number="771000002",
            ).exists()
        )

    def test_resolve_or_create_customer_reuses_existing_user(self):
        user = User.objects.create_user(username="771000002", password="pass")

        first = resolve_or_create_customer("0771000002", "Receiver")
        second = resolve_or_create_customer("263771000002", "Different Name")

        self.assertEqual(first.id, second.id)
        self.assertEqual(Customer.objects.filter(user=user).count(), 1)


class PackagePricingServiceTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(
            name="Harare",
            province="Harare",
            country="Zimbabwe",
        )
        self.pickup = Suburb.objects.create(
            city=self.city,
            name="Pickup",
            x_pos=0,
            y_pos=0,
        )
        self.dropoff = Suburb.objects.create(
            city=self.city,
            name="Dropoff",
            x_pos=3,
            y_pos=4,
        )
        Price.objects.create(
            city=self.city,
            base_price=Decimal("5.00"),
            rate_per_km=Decimal("2.00"),
            fast_delivery_multiplier=Decimal("1.50"),
        )

    def test_calculate_package_price_preserves_standard_formula(self):
        result = calculate_package_price(
            from_suburb_id=self.pickup.id,
            to_suburb_id=self.dropoff.id,
            city_id=self.city.id,
            is_fast_delivery=False,
        )

        self.assertEqual(result["distance_km"], 5)
        self.assertEqual(result["amount"], 15)
        self.assertFalse(result["is_fast_delivery"])

    def test_calculate_package_price_preserves_fast_delivery_rounding(self):
        result = calculate_package_price(
            from_suburb_id=self.pickup.id,
            to_suburb_id=self.dropoff.id,
            city_id=self.city.id,
            is_fast_delivery=True,
        )

        self.assertEqual(result["amount"], 23)
        self.assertTrue(result["is_fast_delivery"])

    def test_calculate_price_endpoint_delegates_to_pricing_service(self):
        response = APIClient().post(
            reverse("intracity_package_price"),
            {
                "from_suburb_id": self.pickup.id,
                "to_suburb_id": self.dropoff.id,
                "city_id": self.city.id,
                "is_fast_delivery": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["distance_km"], 5)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("15.00"))


class PackageNotificationServiceTests(TestCase):
    def _package(self):
        sender_user = SimpleNamespace(first_name="Tariro", last_name="Moyo")
        receiver_user = SimpleNamespace(first_name="Nyasha", last_name="Kamba")
        return SimpleNamespace(
            is_sender_initiated=True,
            dropoff_address="Borrowdale",
            pickup_address="Avondale",
            sender=SimpleNamespace(user=sender_user),
            receiver=SimpleNamespace(user=receiver_user),
            receiver_code="123456",
            sender_code="654321",
            slug="mov-test",
        )

    def test_build_message_preserves_pay_forward_wording(self):
        invoice = SimpleNamespace(
            is_pay_forward=True,
            amount=Decimal("10.00"),
        )

        message = build_package_booking_message(self._package(), invoice)

        self.assertIn("Collection OTP: 123456", message)
        self.assertIn("Amount Due on Delivery: $10.00", message)

    @override_settings(
        TXTCONSOLE_SYSTEM_ID="system",
        TXTCONSOLE_PASSWORD="password",
        TXTCONSOLE_SMS_URL="https://sms.example.test",
        TXTCONSOLE_SOURCE="MOVO",
        TXTCONSOLE_RECEIPT_URL=None,
    )
    @patch("apps.intracity.services.package_notifications.requests.post")
    def test_send_sms_uses_normalized_destination(self, post):
        post.return_value = Mock(status_code=200)
        invoice = SimpleNamespace(
            is_pay_forward=False,
            amount=Decimal("10.00"),
        )

        sent = send_package_booking_sms(
            "0771000002",
            self._package(),
            invoice,
        )

        self.assertTrue(sent)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["destination"], "263771000002")
        self.assertEqual(post.call_args.kwargs["timeout"], 20)
