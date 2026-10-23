from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import Biker, City, Customer
from apps.transporters.models import BikerDailySession, WeeklyDriverShift
from ..models import Invoice, Package, PackageStatus, RefundReview
from ..services.package_expiration import expire_uncollected_packages
from ..services.package_assignment import assign_pending_packages


class PackageRenewalTests(APITestCase):
    def setUp(self):
        city = City.objects.create(name="Harare", province="Harare", country="Zimbabwe")
        self.owner = User.objects.create_user(username="renew-owner")
        self.other = User.objects.create_user(username="renew-other")
        sender = Customer.objects.create(user=self.owner)
        receiver = Customer.objects.create(user=self.other)
        self.package = Package.objects.create(
            sender=sender, receiver=receiver, city=city,
            pickup_address="A", dropoff_address="B",
            sender_code="111111", receiver_code="222222",
        )
        self.invoice = Invoice.objects.create(package=self.package, amount=Decimal("12.50"), payment_method="PaynowEcocash")
        PackageStatus.objects.create(package=self.package, status="Pending")
        Package.objects.filter(pk=self.package.pk).update(added_at=timezone.now() - timedelta(days=2))
        self.package.refresh_from_db()

    def test_expiry_renewal_and_second_missed_day(self):
        with patch("apps.intracity.services.package_expiration.notify_current_packages_changed"), patch("apps.intracity.services.package_expiration.queue_package_customer_notification"):
            self.assertEqual(expire_uncollected_packages()["expired"], 1)
            self.assertEqual(expire_uncollected_packages()["expired"], 0)
        self.client.force_authenticate(user=self.other)
        url = reverse("intracity_renew_package")
        self.assertEqual(self.client.post(url, {"package_id": self.package.pk}).status_code, 403)
        self.client.force_authenticate(user=self.owner)
        with patch("apps.intracity.views.package_views.notify_current_packages_changed"), patch("apps.intracity.views.package_views.queue_package_customer_notification"):
            response = self.client.post(url, {"package_id": self.package.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post(url, {"package_id": self.package.pk}).status_code, 409)
        self.package.refresh_from_db()
        self.assertTrue(self.package.is_renewed)
        self.assertEqual(timezone.localdate(self.package.renewed_at), timezone.localdate())
        self.invoice.is_paid = True
        self.invoice.save(update_fields=["is_paid"])
        Package.objects.filter(pk=self.package.pk).update(renewed_at=timezone.now() - timedelta(days=1))
        with patch("apps.intracity.services.package_expiration.notify_current_packages_changed"), patch("apps.intracity.services.package_expiration.queue_package_customer_notification"):
            self.assertEqual(expire_uncollected_packages()["cancelled"], 1)
            self.assertEqual(expire_uncollected_packages()["cancelled"], 0)
        self.assertEqual(RefundReview.objects.count(), 1)
        self.assertEqual(RefundReview.objects.get().amount, Decimal("12.50"))
        self.assertEqual(PackageStatus.objects.latest("pk").status, "Cancelled")

    def test_paid_expired_cancellation_requests_full_refund(self):
        PackageStatus.objects.create(package=self.package, status="Expired")
        self.invoice.is_paid = True
        self.invoice.save(update_fields=["is_paid"])
        self.client.force_authenticate(user=self.owner)
        with patch("apps.intracity.views.delivery_views.notify_current_packages_changed"), patch("apps.intracity.views.delivery_views.queue_package_customer_notification"):
            response = self.client.post(reverse("intracity_cancel_order"), {"package_id": self.package.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["refund_status"], "pending_review")
        self.assertEqual(RefundReview.objects.get().recipient_id, self.package.sender_id)
        self.assertEqual(RefundReview.objects.get().amount, self.invoice.amount)

    def test_refund_resolution_requires_staff(self):
        self.invoice.is_paid = True
        self.invoice.save(update_fields=["is_paid"])
        PackageStatus.objects.create(package=self.package, status="Cancelled")
        from ..services.package_expiration import ensure_refund_review
        review = ensure_refund_review(self.package)
        url = reverse("admin_refund_review_resolve", args=[review.pk])
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.post(url, {"status": "refunded", "reference": "R-1"}).status_code, 403)
        staff = User.objects.create_superuser(username="refund-admin", password="pass", email="admin@example.com")
        self.client.force_authenticate(user=staff)
        self.assertEqual(self.client.post(url, {"status": "refunded", "reference": "R-1"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"status": "refunded", "reference": "R-1"}).status_code, 409)

    def test_expiry_clears_driver_and_renewed_package_leads_queue(self):
        driver_user = User.objects.create_user(username="renew-driver")
        driver = Biker.objects.create(user=driver_user)
        self.package.biker = driver
        self.package.assigned_at = timezone.now() - timedelta(days=2)
        self.package.save(update_fields=["biker", "assigned_at"])
        PackageStatus.objects.create(package=self.package, status="Assigned")
        with patch("apps.intracity.services.package_expiration.notify_current_packages_changed"), patch("apps.intracity.services.package_expiration.queue_package_customer_notification"):
            expire_uncollected_packages()
        self.package.refresh_from_db()
        self.assertIsNone(self.package.biker_id)
        self.assertEqual(self.package.assignments.count(), 1)
        self.client.force_authenticate(user=self.owner)
        with patch("apps.intracity.views.package_views.notify_current_packages_changed"), patch("apps.intracity.views.package_views.queue_package_customer_notification"):
            self.assertEqual(self.client.post(reverse("intracity_renew_package"), {"package_id": self.package.pk}).status_code, 200)
        fresh = Package.objects.create(
            sender=self.package.sender, receiver=self.package.receiver, city=self.package.city,
            pickup_address="C", dropoff_address="D", sender_code="333333", receiver_code="444444",
            is_fast_delivery=True,
        )
        PackageStatus.objects.create(package=fresh, status="Pending")
        WeeklyDriverShift.objects.get_or_create(weekday=timezone.localdate().weekday())
        WeeklyDriverShift.objects.update(is_open=True, start_time=time.min, end_time=time.max)
        BikerDailySession.objects.create(biker=driver, date=timezone.localdate(), start_time=timezone.now(), is_active=True)
        with patch("apps.intracity.services.package_assignment.notify_current_packages_changed"), patch("apps.intracity.services.package_assignment.queue_package_assignment_notifications"):
            result = assign_pending_packages()
        self.assertEqual(result["assigned_packages"][0]["package_id"], self.package.pk)

    def test_old_in_transit_assignment_remains_visible(self):
        driver_user = User.objects.create_user(username="transit-driver")
        driver = Biker.objects.create(user=driver_user)
        self.package.biker = driver
        self.package.save(update_fields=["biker"])
        PackageStatus.objects.create(package=self.package, status="In Transit")
        with patch("apps.intracity.services.package_expiration.notify_current_packages_changed"), patch("apps.intracity.services.package_expiration.queue_package_customer_notification"):
            self.assertEqual(expire_uncollected_packages(), {"expired": 0, "cancelled": 0})
        self.client.force_authenticate(user=driver_user)
        response = self.client.get(reverse("current_assignment"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assignment"]["package_id"], self.package.pk)

    def test_late_online_payment_creates_refund_case_after_cancellation(self):
        PackageStatus.objects.create(package=self.package, status="Expired")
        self.client.force_authenticate(user=self.owner)
        with patch("apps.intracity.views.delivery_views.notify_current_packages_changed"), patch("apps.intracity.views.delivery_views.queue_package_customer_notification"):
            self.assertEqual(self.client.post(reverse("intracity_cancel_order"), {"package_id": self.package.pk}).status_code, 200)
        self.assertFalse(RefundReview.objects.exists())
        response = self.client.post(
            reverse("intracity_ecocash_notify"),
            {"ecocashResponseCode": "SUCCEEDED", "orginalMerchantReference": str(self.invoice.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.is_paid)
        self.assertEqual(RefundReview.objects.get().status, "pending_review")
