from io import BytesIO
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from PIL import Image

from apps.users.models import Biker, City, Customer, Suburb
from apps.bookkeeping.models import Account, IntracitySale
from apps.transporters.models import BikerDailySession

from ..models import (Invoice, Package, PackageStatus, Price, RoundTripCashEvent, RoundTripOrder,
                      PaynowPayment, RefundReview, RoundTripPOD, RoundTripResolution,
                      RoundTripVerificationAttempt)
from ..services.round_trip_dispatch import assign_pending_round_trips
from ..services.package_assignment import assign_pending_packages, is_biker_busy

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def pod_image():
    output = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format="PNG")
    return SimpleUploadedFile("pod.png", output.getvalue(), content_type="image/png")


@override_settings(STORAGES=TEST_STORAGES)
class RoundTripBackendTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Harare")
        self.cbd = Suburb.objects.create(city=self.city, name="CBD", x_coord=0, y_coord=0)
        self.pickup = Suburb.objects.create(city=self.city, name="North", x_coord=0.01, y_coord=0.01, is_active=True)
        self.recipient_area = Suburb.objects.create(city=self.city, name="South", x_coord=0.02, y_coord=0.02, is_active=True)
        Price.objects.create(city=self.city, base_price=Decimal("5.00"), rate_per_km=Decimal("1.00"))
        self.sender_user = User.objects.create_user(username="771111111", password="x")
        self.sender = Customer.objects.create(user=self.sender_user)
        self.recipient_user = User.objects.create_user(username="772222222", password="x")
        self.recipient = Customer.objects.create(user=self.recipient_user)
        self.biker_user = User.objects.create_user(username="773333333", password="x")
        self.biker = Biker.objects.create(user=self.biker_user)
        self.stranger = User.objects.create_user(username="774444444", password="x")
        self.staff = User.objects.create_user(username="775555555", password="x", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.sender_user)

    def request_data(self):
        return {
            "pickup": {"area_id": self.pickup.pk, "address": "1 Sender Road"},
            "stops": [{
                "area_id": self.recipient_area.pk, "address": "2 Recipient Road",
                "contact": {"name": "Recipient", "phone": self.recipient_user.username},
                "actions": ["DROP_OFF_ITEM", "COLLECT_CASH", "VERIFY_HANDOFF"],
            }],
            "parcels": [{"description": "One sealed parcel"}],
            "collection": {"amount": "25.00", "currency": "USD"},
            "return_to_sender": True,
        }

    def create_order(self):
        with patch("apps.intracity.services.round_trip_otp.secrets.randbelow",
                   side_effect=[123456, 234567, 345678]):
            response = self.client.post(
                reverse("intracity_round_trip_collection"), self.request_data(), format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        return RoundTripOrder.objects.get(pk=response.data["round_trip_id"])

    def assign(self, order):
        with patch("apps.intracity.services.round_trip_dispatch.is_biker_busy", return_value=False), \
             patch("apps.intracity.services.round_trip_otp.secrets.randbelow", return_value=123456):
            result = assign_pending_round_trips()
        self.assertEqual(result["assigned_count"], 1)
        order.refresh_from_db()
        return order.assignments.get(ended_at__isnull=True)

    def verify(self, order, stop, assignment, **cash):
        self.client.force_authenticate(self.biker_user)
        otp = {1: "123456", 2: "234567", 3: "345678"}[stop.sequence]
        return self.client.post(
            reverse("intracity_round_trip_verify", kwargs={"pk": order.pk, "stop_id": stop.pk}),
            {"otp": otp, **cash}, format="json",
        )

    def test_create_quote_and_separate_paginated_list(self):
        quote = self.client.post(reverse("intracity_round_trip_price"), {
            "pickup_area_id": self.pickup.pk, "recipient_area_id": self.recipient_area.pk,
        }, format="json")
        self.assertEqual(quote.status_code, 200, quote.data)
        self.assertEqual(Decimal(quote.data["amount"]), Decimal(quote.data["one_way_amount"]) * Decimal("1.5"))
        order = self.create_order()
        self.assertEqual(order.invoice.amount, Decimal(quote.data["amount"]))
        self.assertIsNone(order.invoice.package_id)
        self.assertEqual(list(order.stops.values_list("sequence", "kind")), [
            (1, "sender_pickup"), (2, "recipient"), (3, "sender_return"),
        ])
        self.assertEqual(order.stops.get(sequence=1).address, order.stops.get(sequence=3).address)
        page = self.client.get(reverse("intracity_round_trip_collection"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.data["count"], 1)
        self.assertEqual(page.data["results"][0]["round_trip_id"], order.pk)
        self.assertEqual(page.data["results"][0]["active_stop"]["kind"], "sender_pickup")
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(reverse("intracity_round_trip_detail", kwargs={"pk": order.pk})).status_code, 404)

    def test_create_limits_and_same_city(self):
        data = self.request_data()
        data["parcels"].append({"description": "Second parcel"})
        self.assertEqual(self.client.post(reverse("intracity_round_trip_collection"), data, format="json").status_code, 400)
        data = self.request_data()
        data["return_to_sender"] = False
        self.assertEqual(self.client.post(reverse("intracity_round_trip_collection"), data, format="json").status_code, 400)
        other_city = City.objects.create(name="Bulawayo")
        other_area = Suburb.objects.create(city=other_city, name="Other", x_coord=0, y_coord=0)
        data = self.request_data()
        data["stops"][0]["area_id"] = other_area.pk
        self.assertEqual(self.client.post(reverse("intracity_round_trip_collection"), data, format="json").status_code, 400)

    def test_stop_verification_pod_cash_and_completion(self):
        order = self.create_order()
        assignment = self.assign(order)
        pickup, recipient, sender_return = list(order.stops.all())
        self.assertEqual(self.verify(order, recipient, assignment).status_code, 409)
        self.client.force_authenticate(self.biker_user)
        wrong = self.client.post(
            reverse("intracity_round_trip_verify", kwargs={"pk": order.pk, "stop_id": pickup.pk}),
            {"otp": "000000"}, format="json",
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertTrue(RoundTripVerificationAttempt.objects.filter(stop=pickup, reason="invalid_code").exists())
        with patch("apps.intracity.services.round_trip_otp.secrets.randbelow", return_value=123456):
            self.assertEqual(self.verify(order, pickup, assignment).status_code, 200)
        self.assertEqual(self.verify(order, pickup, assignment).status_code, 409)
        self.assertEqual(self.verify(order, recipient, assignment, cash_amount="25.00", cash_currency="USD").status_code, 400)
        image = pod_image()
        pod_url = reverse("intracity_round_trip_pod", kwargs={"pk": order.pk, "stop_id": recipient.pk})
        uploaded = self.client.post(pod_url, {
            "upload_id": "77777777-7777-4777-8777-777777777777",
            "image": image,
        }, format="multipart")
        self.assertEqual(uploaded.status_code, 201, uploaded.data)
        self.client.force_authenticate(self.sender_user)
        self.assertEqual(self.client.get(pod_url).status_code, 409)
        self.client.force_authenticate(self.biker_user)
        with patch("apps.intracity.services.round_trip_otp.secrets.randbelow", return_value=123456):
            self.assertEqual(self.verify(order, recipient, assignment, cash_amount="25.00", cash_currency="USD").status_code, 200)
        self.client.force_authenticate(self.sender_user)
        self.assertEqual(self.client.get(pod_url).status_code, 200)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(pod_url).status_code, 200)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(pod_url).status_code, 403)
        self.client.force_authenticate(self.biker_user)
        self.assertEqual(self.verify(order, sender_return, assignment, cash_amount="25.00", cash_currency="USD").status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "Completed")
        self.assertEqual(RoundTripCashEvent.objects.filter(order=order).count(), 2)

    def test_round_trip_assignment_blocks_legacy_dispatch_until_completion(self):
        order = self.create_order()
        self.assign(order)
        BikerDailySession.objects.create(
            biker=self.biker, date=timezone.localdate(), start_time=timezone.now(), is_active=True,
        )
        package = Package.objects.create(
            sender=self.sender, receiver=self.recipient, city=self.city,
            pickup_address="Pickup", dropoff_address="Dropoff",
            sender_code="111111", receiver_code="222222",
        )
        PackageStatus.objects.create(package=package, status="Pending")
        with patch("apps.intracity.services.package_assignment.shift_allows_work", return_value=True):
            self.assertTrue(is_biker_busy(self.biker))
            result = assign_pending_packages()
        self.assertEqual(result["assigned_count"], 0)
        package.refresh_from_db()
        self.assertIsNone(package.biker_id)

    def test_cash_mismatch_staff_resolution_and_cancel_rules(self):
        order = self.create_order()
        assignment = self.assign(order)
        pickup, recipient, _ = list(order.stops.all())
        self.client.force_authenticate(self.sender_user)
        cancel_url = reverse("intracity_round_trip_cancel", kwargs={"pk": order.pk})
        self.assertEqual(self.client.post(cancel_url, {}, format="json").status_code, 200)
        self.assertEqual(order.invoice.package_id, None)
        order = self.create_order()
        assignment = self.assign(order)
        pickup, recipient, _ = list(order.stops.all())
        with patch("apps.intracity.services.round_trip_otp.secrets.randbelow", return_value=123456):
            self.assertEqual(self.verify(order, pickup, assignment).status_code, 200)
        self.client.force_authenticate(self.sender_user)
        self.assertEqual(self.client.post(reverse("intracity_round_trip_cancel", kwargs={"pk": order.pk}), {}, format="json").status_code, 409)
        self.client.force_authenticate(self.biker_user)
        image = pod_image()
        self.assertEqual(self.client.post(
            reverse("intracity_round_trip_pod", kwargs={"pk": order.pk, "stop_id": recipient.pk}),
            {"upload_id": "88888888-8888-4888-8888-888888888888", "image": image},
            format="multipart",
        ).status_code, 201)
        mismatch = self.verify(order, recipient, assignment, cash_amount="20.00", cash_currency="USD")
        self.assertEqual(mismatch.status_code, 409)
        order.refresh_from_db()
        self.assertEqual(order.status, "Exception")
        self.client.force_authenticate(self.staff)
        with patch("apps.intracity.services.round_trip_otp.secrets.randbelow", return_value=123456):
            resolved = self.client.post(
                reverse("intracity_round_trip_resolve", kwargs={"pk": order.pk}),
                {"outcome": "resume", "reason": "Verified full amount with both parties", "actual_collected": "25.00"},
                format="json",
            )
        self.assertEqual(resolved.status_code, 200, resolved.data)
        order.refresh_from_db()
        self.assertEqual(order.status, "In Transit")
        self.assertEqual(RoundTripResolution.objects.get(order=order).reported_amount, Decimal("20.00"))
        self.assertEqual(RoundTripCashEvent.objects.get(order=order).amount, Decimal("25.00"))

    def test_round_trip_invoice_details_use_sender_as_payer(self):
        order = self.create_order()
        response = self.client.get(reverse("intracity_invoice_details"), {"invoice_id": order.invoice.pk})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["round_trip_id"], order.pk)
        self.assertIsNone(response.data["package_id"])
        self.assertTrue(response.data["is_payer"])
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(reverse("intracity_invoice_details"), {"invoice_id": order.invoice.pk}).status_code, 403)

    @patch("apps.intracity.services.round_trip_otp.send_round_trip_sms")
    def test_stop_codes_are_created_once_at_order_creation(self, send_sms):
        with patch("apps.intracity.services.round_trip_dispatch.assign_pending_round_trips_safely"):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                order = self.create_order()
        self.assertEqual(len(callbacks), 4)  # three SMS sends plus dispatch
        self.assertEqual(send_sms.call_count, 3)
        self.assertEqual(send_sms.call_args_list[0].args[0], self.sender_user.username)
        self.assertEqual(send_sms.call_args_list[1].args[0], self.recipient_user.username)
        self.assertEqual(send_sms.call_args_list[2].args[0], self.sender_user.username)
        self.assign(order)
        order.refresh_from_db()
        pickup = order.stops.get(sequence=1)
        verify_url = reverse("intracity_round_trip_verify", kwargs={"pk": order.pk, "stop_id": pickup.pk})
        original_hash = pickup.otp_hash
        self.assertTrue(original_hash)
        self.assertTrue(pickup.otp_issued_at)
        self.assertEqual(order.stops.get(sequence=2).otp_hash != pickup.otp_hash, True)
        self.client.force_authenticate(self.biker_user)
        self.assertEqual(self.client.post(verify_url, {"otp": "123456"}, format="json").status_code, 200)
        pickup.refresh_from_db()
        self.assertEqual(pickup.otp_hash, original_hash)

    def test_fixed_code_lockout_requires_staff_resume_without_reissuing(self):
        order = self.create_order()
        self.assign(order)
        pickup = order.stops.get(sequence=1)
        verify_url = reverse("intracity_round_trip_verify", kwargs={"pk": order.pk, "stop_id": pickup.pk})
        self.client.force_authenticate(self.biker_user)
        for _ in range(5):
            response = self.client.post(verify_url, {"otp": "000000"}, format="json")
            self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "Exception")
        original_hash = pickup.otp_hash
        self.client.force_authenticate(self.staff)
        resolution = self.client.post(reverse("intracity_round_trip_resolve", kwargs={"pk": order.pk}), {
            "outcome": "resume", "reason": "Confirmed sender still has the original code",
        }, format="json")
        self.assertEqual(resolution.status_code, 200, resolution.data)
        pickup.refresh_from_db()
        self.assertEqual(pickup.otp_hash, original_hash)
        self.assertEqual(pickup.otp_failures, 0)
        self.client.force_authenticate(self.biker_user)
        self.assertEqual(self.client.post(verify_url, {"otp": "123456"}, format="json").status_code, 200)

    @patch("apps.intracity.views.payments_views.requests.post")
    def test_round_trip_ecocash_uses_sender_and_order_reference(self, post):
        order = self.create_order()
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"clientCorrelator": "provider-reference"}
        response = self.client.post(reverse("intracity_ecocash_payment"), {
            "invoice_id": order.invoice.pk, "phone_number": "0771234567",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(order.slug, post.call_args.kwargs["json"]["clientCorrelator"])
        self.assertEqual(order.invoice.ecocashpayment_set.get().customer, self.sender)

    @patch("apps.intracity.views.payments_views.paynow.send_mobile")
    def test_round_trip_paynow_uses_sender_and_order_reference(self, send_mobile):
        order = self.create_order()
        send_mobile.return_value = SimpleNamespace(success=True, poll_url="https://example.com/poll")
        response = self.client.post(reverse("intracity_paynow_payment"), {
            "invoice_id": order.invoice.pk, "phone_number": "0771234567",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        attempt = PaynowPayment.objects.get(invoice=order.invoice)
        self.assertEqual(attempt.customer, self.sender)
        self.assertIn(order.slug, attempt.reference)

    @patch("apps.intracity.views.payments_views.paynow.check_transaction_status")
    def test_late_paynow_payment_after_round_trip_cancel_creates_refund_review(self, check_status):
        order = self.create_order()
        self.client.post(reverse("intracity_round_trip_cancel", kwargs={"pk": order.pk}), {}, format="json")
        Account.objects.create(name="FBC", currency="USD")
        PaynowPayment.objects.create(
            customer=self.sender, invoice=order.invoice, phone_number="263771234567",
            reference="REF-ROUND-TRIP-LATE", poll_url="https://example.com/poll",
        )
        check_status.return_value = SimpleNamespace(status="paid")
        first = self.client.get(reverse("intracity_paynow_notify"), {"invoice_id": order.invoice.pk})
        second = self.client.get(reverse("intracity_paynow_notify"), {"invoice_id": order.invoice.pk})
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertTrue(RefundReview.objects.filter(invoice=order.invoice, recipient=self.sender).exists())
        self.assertEqual(IntracitySale.objects.filter(invoice=order.invoice).count(), 1)
