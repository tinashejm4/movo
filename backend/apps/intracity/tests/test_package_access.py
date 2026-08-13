from types import SimpleNamespace

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import City, Customer

from ..models import Invoice, Package, PackageStatus
from ..services.package_access import (
    package_initiator_user_id,
    package_payer_user_id,
    package_user_can_cancel,
)


class PackageAccessServiceTests(APITestCase):
    def test_initiator_and_payer_follow_the_package_payment_choice(self):
        sender = SimpleNamespace(user_id=1)
        receiver = SimpleNamespace(user_id=2)
        package = SimpleNamespace(
            sender=sender,
            receiver=receiver,
            is_sender_initiated=True,
        )

        self.assertEqual(package_initiator_user_id(package), 1)
        self.assertEqual(
            package_payer_user_id(package, SimpleNamespace(is_pay_forward=False)),
            1,
        )
        self.assertEqual(
            package_payer_user_id(package, SimpleNamespace(is_pay_forward=True)),
            2,
        )

        package.is_sender_initiated = False
        self.assertEqual(package_initiator_user_id(package), 2)
        self.assertEqual(
            package_payer_user_id(package, SimpleNamespace(is_pay_forward=False)),
            2,
        )
        self.assertEqual(
            package_payer_user_id(package, SimpleNamespace(is_pay_forward=True)),
            1,
        )

    def test_initiator_and_payer_can_cancel(self):
        package = SimpleNamespace(
            sender=SimpleNamespace(user_id=1),
            receiver=SimpleNamespace(user_id=2),
            is_sender_initiated=True,
        )
        invoice = SimpleNamespace(is_pay_forward=True)

        self.assertTrue(package_user_can_cancel(package, invoice, 1))
        self.assertTrue(package_user_can_cancel(package, invoice, 2))
        self.assertFalse(package_user_can_cancel(package, invoice, 3))


class PackagePaymentAccessTests(APITestCase):
    def setUp(self):
        city = City.objects.create(
            name="Payment City", province="Harare", country="Zimbabwe"
        )
        self.sender_user = User.objects.create_user(
            username="0779000101", password="pass"
        )
        self.receiver_user = User.objects.create_user(
            username="0779000102", password="pass"
        )
        self.other_user = User.objects.create_user(
            username="0779000103", password="pass"
        )
        sender = Customer.objects.create(user=self.sender_user)
        receiver = Customer.objects.create(user=self.receiver_user)
        self.package = Package.objects.create(
            sender=sender,
            receiver=receiver,
            city=city,
            pickup_address="Pickup",
            dropoff_address="Drop-off",
            sender_code="111111",
            receiver_code="222222",
        )
        self.invoice = Invoice.objects.create(
            package=self.package,
            amount="10.00",
            is_pay_forward=False,
        )
        PackageStatus.objects.create(package=self.package, status="Pending")

    def test_unrelated_customer_cannot_read_package_or_invoice(self):
        self.client.force_authenticate(user=self.other_user)

        package_response = self.client.get(
            reverse("intracity_package_detail"),
            {"package_id": self.package.id},
        )
        invoice_response = self.client.get(
            reverse("intracity_invoice_details"),
            {"package_id": self.package.id},
        )

        self.assertEqual(package_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(invoice_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_initiator_cannot_cancel(self):
        self.client.force_authenticate(user=self.receiver_user)

        response = self.client.post(
            reverse("intracity_cancel_order"),
            {"package_id": self.package.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_receiver_initiator_can_cancel(self):
        self.package.is_sender_initiated = False
        self.package.save(update_fields=["is_sender_initiated"])
        self.client.force_authenticate(user=self.receiver_user)

        response = self.client.post(
            reverse("intracity_cancel_order"),
            {"package_id": self.package.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_forwarded_payer_can_cancel(self):
        self.invoice.is_pay_forward = True
        self.invoice.save(update_fields=["is_pay_forward"])
        self.client.force_authenticate(user=self.receiver_user)

        response = self.client.post(
            reverse("intracity_cancel_order"),
            {"package_id": self.package.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_payer_cannot_start_paynow_payment(self):
        self.client.force_authenticate(user=self.receiver_user)

        response = self.client.post(
            reverse("intracity_paynow_payment"),
            {"invoice_id": self.invoice.id, "phone_number": "0771234567"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_initiator_cannot_start_forwarded_ecocash_payment(self):
        self.invoice.is_pay_forward = True
        self.invoice.save(update_fields=["is_pay_forward"])
        self.client.force_authenticate(user=self.sender_user)

        response = self.client.post(
            reverse("intracity_ecocash_payment"),
            {"invoice_id": self.invoice.id, "phone_number": "0771234567"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
