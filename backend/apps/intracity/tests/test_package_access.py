from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import City, Customer

from ..models import (
    EcocashPayment,
    Invoice,
    Package,
    PackageStatus,
    PaynowPayment,
)
from ..services.package_access import (
    package_confirmation_code_for_user,
    package_initiator_user_id,
    package_is_incoming_for_user,
    package_payer_user_id,
    package_user_can_cancel,
)
from ..services.invoice_payment import invoice_user_can_pay, invoice_user_is_payer


class PackageAccessServiceTests(APITestCase):
    def test_confirmation_code_is_selected_by_participant_role(self):
        package = SimpleNamespace(
            sender=SimpleNamespace(user_id=1),
            receiver=SimpleNamespace(user_id=2),
            sender_code="111111",
            receiver_code="222222",
        )

        self.assertEqual(package_confirmation_code_for_user(package, 1), "111111")
        self.assertEqual(package_confirmation_code_for_user(package, 2), "222222")
        self.assertIsNone(package_confirmation_code_for_user(package, 3))

    def test_self_send_confirmation_code_follows_delivery_stage(self):
        customer = SimpleNamespace(user_id=1)
        package = SimpleNamespace(
            sender=customer,
            receiver=customer,
            sender_code="111111",
            receiver_code="222222",
        )

        self.assertEqual(
            package_confirmation_code_for_user(
                package, 1, current_status="Pending"
            ),
            "111111",
        )
        self.assertEqual(
            package_confirmation_code_for_user(
                package, 1, current_status="In Transit"
            ),
            "222222",
        )

    def test_package_direction_is_relative_to_user_role(self):
        sender = SimpleNamespace(user_id=1)
        receiver = SimpleNamespace(user_id=2)
        package = SimpleNamespace(
            sender=sender,
            receiver=receiver,
            is_sender_initiated=True,
        )

        self.assertFalse(package_is_incoming_for_user(package, 1))
        self.assertTrue(package_is_incoming_for_user(package, 2))
        self.assertIsNone(package_is_incoming_for_user(package, 3))

        package.is_sender_initiated = False
        self.assertFalse(package_is_incoming_for_user(package, 1))
        self.assertTrue(package_is_incoming_for_user(package, 2))

    def test_self_send_is_incoming(self):
        customer = SimpleNamespace(user_id=1)
        package = SimpleNamespace(sender=customer, receiver=customer)

        self.assertTrue(package_is_incoming_for_user(package, 1))

    def test_payer_follows_pay_forward_independently_of_initiator(self):
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
            1,
        )
        self.assertEqual(
            package_payer_user_id(package, SimpleNamespace(is_pay_forward=True)),
            2,
        )

    def test_is_payer_fails_closed_for_missing_or_unrelated_user(self):
        package = SimpleNamespace(
            sender=SimpleNamespace(user_id=1),
            receiver=SimpleNamespace(user_id=2),
        )
        invoice = SimpleNamespace(package=package, is_pay_forward=False)

        self.assertTrue(invoice_user_is_payer(invoice, 1))
        self.assertFalse(invoice_user_is_payer(invoice, 2))
        self.assertFalse(invoice_user_is_payer(invoice, 3))
        self.assertFalse(invoice_user_is_payer(None, 1))

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
        self.sender = Customer.objects.create(user=self.sender_user)
        self.receiver = Customer.objects.create(user=self.receiver_user)
        self.package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
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

    def get_invoice_details(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get(
            reverse("intracity_invoice_details"),
            {"package_id": self.package.id},
        )

    def test_invoice_permissions_follow_pay_forward_not_initiator(self):
        self.package.is_sender_initiated = False
        self.package.save(update_fields=["is_sender_initiated"])

        sender_response = self.get_invoice_details(self.sender_user)
        self.assertTrue(sender_response.data["is_payer"])
        self.assertTrue(sender_response.data["can_pay"])

        receiver_response = self.get_invoice_details(self.receiver_user)
        self.assertFalse(receiver_response.data["is_payer"])
        self.assertFalse(receiver_response.data["can_pay"])

        self.invoice.is_pay_forward = True
        self.invoice.save(update_fields=["is_pay_forward"])

        receiver_response = self.get_invoice_details(self.receiver_user)
        self.assertTrue(receiver_response.data["is_payer"])
        self.assertTrue(receiver_response.data["can_pay"])

        sender_response = self.get_invoice_details(self.sender_user)
        self.assertFalse(sender_response.data["is_payer"])
        self.assertFalse(sender_response.data["can_pay"])

    def test_paid_invoice_identifies_payer_but_cannot_be_paid(self):
        self.invoice.is_paid = True
        self.invoice.save(update_fields=["is_paid"])

        response = self.get_invoice_details(self.sender_user)

        self.assertTrue(response.data["is_payer"])
        self.assertFalse(response.data["can_pay"])

    def test_cancelled_package_identifies_payer_but_cannot_be_paid(self):
        PackageStatus.objects.create(package=self.package, status="Cancelled")

        response = self.get_invoice_details(self.sender_user)

        self.assertTrue(response.data["is_payer"])
        self.assertFalse(response.data["can_pay"])

    def test_zero_amount_invoice_cannot_be_paid(self):
        self.invoice.amount = "0.00"
        self.invoice.save(update_fields=["amount"])

        response = self.get_invoice_details(self.sender_user)

        self.assertTrue(response.data["is_payer"])
        self.assertFalse(response.data["can_pay"])

    def test_pending_payment_attempt_remains_payable(self):
        EcocashPayment.objects.create(
            customer=self.sender,
            invoice=self.invoice,
            phone_number="263771234567",
        )

        response = self.get_invoice_details(self.sender_user)

        self.assertTrue(response.data["is_payer"])
        self.assertTrue(response.data["can_pay"])
        self.assertTrue(response.data["payment_pending"])
        self.assertTrue(invoice_user_can_pay(self.invoice, self.sender_user.id))

    def test_expired_payment_attempt_allows_an_unpaid_invoice_to_be_retried(self):
        attempt = PaynowPayment.objects.create(
            customer=self.sender,
            invoice=self.invoice,
            phone_number="263771234567",
            reference="REF-EXPIRED-ATTEMPT",
        )
        PaynowPayment.objects.filter(pk=attempt.pk).update(
            created_at=timezone.now() - timedelta(minutes=3)
        )

        response = self.get_invoice_details(self.sender_user)

        self.assertFalse(response.data["is_paid"])
        self.assertFalse(response.data["payment_pending"])
        self.assertTrue(response.data["can_pay"])

    def test_missing_invoice_returns_false_payment_permissions(self):
        package_without_invoice = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=self.package.city,
            pickup_address="Pickup",
            dropoff_address="Drop-off",
            sender_code="333333",
            receiver_code="444444",
        )
        self.client.force_authenticate(user=self.sender_user)

        response = self.client.get(
            reverse("intracity_invoice_details"),
            {"package_id": package_without_invoice.id},
        )

        self.assertFalse(response.data["is_payer"])
        self.assertFalse(response.data["can_pay"])

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
        self.assertFalse(invoice_response.data["is_payer"])
        self.assertFalse(invoice_response.data["can_pay"])

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

    def test_receiver_initiator_cannot_pay_non_forward_invoice(self):
        self.package.is_sender_initiated = False
        self.package.save(update_fields=["is_sender_initiated"])
        self.client.force_authenticate(user=self.receiver_user)

        response = self.client.post(
            reverse("intracity_ecocash_payment"),
            {"invoice_id": self.invoice.id, "phone_number": "0771234567"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancelled_invoice_cannot_start_payment(self):
        PackageStatus.objects.create(package=self.package, status="Cancelled")
        self.client.force_authenticate(user=self.sender_user)

        response = self.client.post(
            reverse("intracity_ecocash_payment"),
            {"invoice_id": self.invoice.id, "phone_number": "0771234567"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error"],
            "Payment cannot be started for this invoice",
        )

    @patch("apps.intracity.views.payments_views.paynow.send_mobile")
    def test_pending_attempt_allows_starting_another_payment(self, send_mobile):
        send_mobile.return_value = SimpleNamespace(
            success=True,
            poll_url="https://example.com/paynow/poll/retry",
        )
        EcocashPayment.objects.create(
            customer=self.sender,
            invoice=self.invoice,
            phone_number="263771234567",
        )
        self.client.force_authenticate(user=self.sender_user)

        response = self.client.post(
            reverse("intracity_paynow_payment"),
            {"invoice_id": self.invoice.id, "phone_number": "0771234567"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Payment request successful")
        self.assertTrue(PaynowPayment.objects.filter(invoice=self.invoice).exists())
