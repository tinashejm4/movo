"""The local pickup-day boundary and its one-time renewal lifecycle."""

from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from apps.notifications.services import queue_package_customer_notification

from ..models import Invoice, Package, PackageStatus, RefundReview
from .current_package_updates import notify_current_packages_changed
from .package_access import package_payer


def latest_status_for(package):
    return (PackageStatus.objects.filter(package=package)
            .order_by("-updated_at", "-pk").values_list("status", flat=True).first())


def pickup_date(package):
    return timezone.localdate(package.renewed_at or package.added_at)


def refund_status_for(package):
    review = RefundReview.objects.filter(invoice__package=package).first()
    return review.status if review else None


def ensure_refund_review(package):
    invoice = Invoice.objects.filter(package=package, is_paid=True).first()
    if not invoice:
        return None
    review, _ = RefundReview.objects.get_or_create(
        invoice=invoice,
        defaults={
            "recipient": package_payer(package, invoice),
            "amount": invoice.amount,
            "payment_method": invoice.payment_method or "",
        },
    )
    return review


def expire_uncollected_packages(*, today=None):
    today = today or timezone.localdate()
    latest = (PackageStatus.objects.filter(package=OuterRef("pk"))
              .order_by("-updated_at", "-pk").values("status")[:1])
    candidate_ids = list(
        Package.objects.annotate(current_status=Subquery(latest))
        .filter(current_status__in=["Pending", "Assigned"])
        .filter(Q(is_renewed=False, added_at__date__lt=today)
                | Q(is_renewed=True, renewed_at__date__lt=today))
        .values_list("pk", flat=True)
    )
    result = {"expired": 0, "cancelled": 0}
    for package_id in candidate_ids:
        with transaction.atomic():
            package = Package.objects.select_for_update().get(pk=package_id)
            if latest_status_for(package) not in {"Pending", "Assigned"} or pickup_date(package) >= today:
                continue
            package.biker = None
            package.assigned_at = None
            package.save(update_fields=["biker", "assigned_at"])
            next_status = "Cancelled" if package.is_renewed else "Expired"
            PackageStatus.objects.create(
                package=package, status=next_status,
                comments="Pickup day ended without collection",
            )
            if next_status == "Cancelled":
                ensure_refund_review(package)
            notify_current_packages_changed(package=package, reason=next_status.lower())
            queue_package_customer_notification(
                package=package, event_type=f"package.{next_status.lower()}"
            )
            result[next_status.lower()] += 1
    return result
