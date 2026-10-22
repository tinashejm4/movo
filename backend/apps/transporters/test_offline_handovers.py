import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from apps.bookkeeping.models import Account, IntracitySale
from apps.intracity.models import HandoverAttempt, Invoice, Package, PackageImage, PackageStatus
from apps.users.models import Biker, City, Customer
from .handover_service import process_handover
from .handover_verifiers import make_offline_verifier


class OfflineVerifierVectorTests(SimpleTestCase):
    def test_fixed_vector_for_dart_implementation(self):
        verifier = make_offline_verifier(
            "012345", salt=bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        )
        self.assertEqual(verifier, {
            "version": 1,
            "algorithm": "pbkdf2_sha256",
            "iterations": 600_000,
            "salt": "AAECAwQFBgcICQoLDA0ODw==",
            "digest": "UTlLVv5gSoMgRDHVh6jC2Zxc1zX/hZV7edf76/tYV0M=",
        })


class OfflineHandoverTests(APITestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        storage_settings = override_settings(
            MEDIA_ROOT=self.media_dir.name,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        storage_settings.enable()
        self.addCleanup(storage_settings.disable)

        self.driver_user = User.objects.create_user(username="offline-driver")
        self.driver = Biker.objects.create(user=self.driver_user)
        self.other_driver_user = User.objects.create_user(username="offline-other")
        self.other_driver = Biker.objects.create(user=self.other_driver_user)
        self.staff_user = User.objects.create_user(username="offline-staff", is_superuser=True)
        self.sender = Customer.objects.create(user=User.objects.create_user(username="offline-sender"))
        self.receiver = Customer.objects.create(user=User.objects.create_user(username="offline-receiver"))
        self.package = Package.objects.create(
            sender=self.sender, receiver=self.receiver,
            city=City.objects.create(name="Offline City"), biker=self.driver,
            assigned_at=timezone.now() - timedelta(days=1),
            pickup_address="A", dropoff_address="B",
            sender_code="012345", receiver_code="654321",
        )
        PackageStatus.objects.create(package=self.package, status="Assigned")
        self.invoice = Invoice.objects.create(package=self.package, amount="12.00", is_paid=False)
        Account.objects.create(name="Offline Cash", owner=self.driver_user, currency="USD")
        self.assignment = self.package.assignments.get()
        self.client.force_authenticate(user=self.driver_user)
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), "blue").save(image_buffer, format="PNG")
        self.original_image = image_buffer.getvalue()

    def upload(self, stage, *, upload_id=None, content=None, assignment=None):
        upload_id = upload_id or uuid4()
        content = self.original_image if content is None else content
        assignment = assignment or self.assignment
        response = self.client.post(
            reverse("intracity_package_images", args=[self.package.pk]),
            {
                "image": SimpleUploadedFile("pod.png", content, content_type="image/png"),
                "upload_id": str(upload_id),
                "assignment_id": str(assignment.pk),
                "stage": stage,
            }, format="multipart",
        )
        return response, upload_id

    def handover(self, stage, image_id, *, request_id=None, assignment=None,
                 cash_received=False):
        request_id = request_id or uuid4()
        response = self.client.post(
            reverse("pickup_package" if stage == "pickup" else "dropoff_package"),
            {
                "package_id": self.package.pk,
                "sender_code" if stage == "pickup" else "receiver_code":
                    "012345" if stage == "pickup" else "654321",
                "request_id": str(request_id),
                "assignment_id": str((assignment or self.assignment).pk),
                "image_id": image_id,
                "cash_received": cash_received,
            }, format="json",
        )
        return response, request_id

    def test_assignment_across_midnight_contains_verifiers_and_payment(self):
        response = self.client.get(reverse("current_assignment"))
        self.assertEqual(response.status_code, 200)
        assignment = response.data["assignment"]
        self.assertEqual(assignment["assignment_id"], str(self.assignment.pk))
        self.assertEqual(assignment["payment"]["cash_due_stage"], "pickup")
        verifier = assignment["pickup_code_verifier"]
        self.assertEqual(verifier["algorithm"], "pbkdf2_sha256")
        self.assertEqual(verifier["iterations"], 600_000)
        digest = hashlib.pbkdf2_hmac(
            "sha256", b"012345", base64.b64decode(verifier["salt"]),
            verifier["iterations"],
        )
        self.assertEqual(base64.b64encode(digest).decode(), verifier["digest"])
        self.assertNotEqual(
            assignment["pickup_code_verifier"], assignment["dropoff_code_verifier"]
        )

    def test_pod_upload_is_idempotent_and_preserves_bytes(self):
        upload_id = uuid4()
        first, _ = self.upload("pickup", upload_id=upload_id)
        second, _ = self.upload("pickup", upload_id=upload_id)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(PackageImage.objects.count(), 1)
        with PackageImage.objects.get().image.open("rb") as saved:
            self.assertEqual(saved.read(), self.original_image)
        different = self.original_image + b"different"
        conflict, _ = self.upload("pickup", upload_id=upload_id, content=different)
        self.assertEqual(conflict.status_code, 409)

    def test_cash_pickup_then_dropoff_and_retries(self):
        pickup_image, _ = self.upload("pickup")
        self.assertEqual(pickup_image.status_code, 201)
        request_id = uuid4()
        first, _ = self.handover(
            "pickup", pickup_image.data["id"], request_id=request_id,
            cash_received=True,
        )
        second, _ = self.handover(
            "pickup", pickup_image.data["id"], request_id=request_id,
            cash_received=True,
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PackageStatus.objects.filter(package=self.package, status="In Transit").count(), 1)
        self.assertEqual(IntracitySale.objects.filter(invoice=self.invoice).count(), 1)
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.is_paid)

        changed, _ = self.handover(
            "pickup", pickup_image.data["id"], request_id=request_id,
            cash_received=False,
        )
        self.assertEqual(changed.status_code, 409)

        dropoff_image, _ = self.upload("dropoff")
        delivered, _ = self.handover("dropoff", dropoff_image.data["id"])
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(PackageStatus.objects.filter(package=self.package, status="Delivered").count(), 1)

    def test_pay_forward_cash_is_recorded_with_dropoff(self):
        self.invoice.is_pay_forward = True
        self.invoice.save(update_fields=["is_pay_forward"])
        pickup_image, _ = self.upload("pickup")
        picked_up, _ = self.handover("pickup", pickup_image.data["id"])
        self.assertEqual(picked_up.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertFalse(self.invoice.is_paid)

        dropoff_image, _ = self.upload("dropoff")
        delivered, _ = self.handover(
            "dropoff", dropoff_image.data["id"], cash_received=True
        )
        self.assertEqual(delivered.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.is_paid)
        self.assertEqual(IntracitySale.objects.filter(invoice=self.invoice).count(), 1)

    def test_pod_fields_are_required_together(self):
        response = self.client.post(
            reverse("pickup_package"),
            {
                "package_id": self.package.pk,
                "sender_code": "012345",
                "request_id": str(uuid4()),
            }, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            PackageStatus.objects.filter(package=self.package, status="In Transit").exists()
        )

    def test_cancelled_handover_and_cash_go_to_review_without_payment(self):
        image, _ = self.upload("pickup")
        PackageStatus.objects.create(package=self.package, status="Cancelled")
        result, request_id = self.handover("pickup", image.data["id"], cash_received=True)
        self.assertEqual(result.status_code, 409)
        attempt = HandoverAttempt.objects.get(pk=request_id)
        self.assertEqual(attempt.outcome, "conflict")
        self.assertEqual(attempt.conflict_reason, "stage_changed")
        self.assertTrue(attempt.code_valid)
        self.invoice.refresh_from_db()
        self.assertFalse(self.invoice.is_paid)
        self.assertFalse(IntracitySale.objects.filter(invoice=self.invoice).exists())

        self.client.force_authenticate(user=self.staff_user)
        review = self.client.get(reverse("admin_handover_reviews"))
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.data["results"][0]["image_id"], image.data["id"])
        accept = self.client.post(
            reverse("admin_handover_review_resolve", args=[request_id]),
            {"action": "accept", "reason": "Checked proof"}, format="json",
        )
        self.assertEqual(accept.status_code, 409)
        reject = self.client.post(
            reverse("admin_handover_review_resolve", args=[request_id]),
            {"action": "reject", "reason": "Order cancelled"}, format="json",
        )
        self.assertEqual(reject.status_code, 200)
        self.client.force_authenticate(user=self.driver_user)
        replay, _ = self.handover(
            "pickup", image.data["id"], request_id=request_id, cash_received=True
        )
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(replay.data["review_status"], "rejected")

    def test_electronic_payment_conflicts_with_queued_cash_claim(self):
        image, _ = self.upload("pickup")
        self.invoice.is_paid = True
        self.invoice.payment_method = "Ecocash"
        self.invoice.save(update_fields=["is_paid", "payment_method"])
        result, request_id = self.handover(
            "pickup", image.data["id"], cash_received=True
        )
        self.assertEqual(result.status_code, 409)
        self.assertEqual(HandoverAttempt.objects.get(pk=request_id).conflict_reason, "cash_conflict")
        self.assertFalse(IntracitySale.objects.filter(invoice=self.invoice).exists())

    def test_former_driver_can_upload_evidence_but_cannot_complete(self):
        self.package.biker = self.other_driver
        self.package.save(update_fields=["biker"])
        image, _ = self.upload("pickup")
        self.assertEqual(image.status_code, 201)
        result, request_id = self.handover("pickup", image.data["id"], cash_received=True)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(HandoverAttempt.objects.get(pk=request_id).conflict_reason, "assignment_changed")
        self.invoice.refresh_from_db()
        self.assertFalse(self.invoice.is_paid)

    def test_staff_accepts_only_after_payment_block_is_cleared(self):
        image, _ = self.upload("pickup")
        result, request_id = self.handover("pickup", image.data["id"])
        self.assertEqual(result.status_code, 409)
        self.assertEqual(HandoverAttempt.objects.get(pk=request_id).conflict_reason, "cash_required")
        self.assertEqual(
            self.client.get(reverse("admin_handover_reviews")).status_code, 403
        )

        self.client.force_authenticate(user=self.staff_user)
        url = reverse("admin_handover_review_resolve", args=[request_id])
        blocked = self.client.post(
            url, {"action": "accept", "reason": "Payment checked"}, format="json"
        )
        self.assertEqual(blocked.status_code, 409)
        self.invoice.is_paid = True
        self.invoice.save(update_fields=["is_paid"])
        with self.captureOnCommitCallbacks(execute=False):
            accepted = self.client.post(
                url, {"action": "accept", "reason": "Payment confirmed"}, format="json"
            )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(HandoverAttempt.objects.get(pk=request_id).outcome, "accepted")
        self.assertEqual(
            PackageStatus.objects.filter(package=self.package, status="In Transit").count(), 1
        )


class ConcurrentHandoverTests(TransactionTestCase):
    def test_simultaneous_retries_create_one_pickup_status(self):
        driver_user = User.objects.create_user(username="concurrent-driver")
        driver = Biker.objects.create(user=driver_user)
        sender = Customer.objects.create(user=User.objects.create_user(username="concurrent-sender"))
        receiver = Customer.objects.create(user=User.objects.create_user(username="concurrent-receiver"))
        package = Package.objects.create(
            sender=sender, receiver=receiver,
            city=City.objects.create(name="Concurrency City"), biker=driver,
            pickup_address="A", dropoff_address="B",
            sender_code="123456", receiver_code="654321",
        )
        PackageStatus.objects.create(package=package, status="Assigned")
        Invoice.objects.create(package=package, amount="1.00", is_paid=True)
        assignment = package.assignments.get()
        image = PackageImage.objects.create(
            package=package, image="package_images/concurrent.png",
            uploaded_by=driver_user, assignment=assignment,
            stage="pickup", upload_id=uuid4(),
        )
        request_id = uuid4()

        def submit():
            close_old_connections()
            try:
                return process_handover(
                    package_id=package.pk, biker_user=driver_user,
                    stage="pickup", code="123456", request_id=request_id,
                    assignment_id=assignment.pk, image_id=image.pk,
                )
            finally:
                close_old_connections()

        with patch("apps.transporters.handover_service.notify_current_packages_changed"), \
             patch("apps.transporters.handover_service.queue_package_customer_notification"):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: submit(), range(2)))

        self.assertEqual([result[0] for result in results], [200, 200])
        self.assertEqual(
            PackageStatus.objects.filter(package=package, status="In Transit").count(), 1
        )
        self.assertEqual(HandoverAttempt.objects.filter(pk=request_id).count(), 1)
