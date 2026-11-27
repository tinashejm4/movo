"""Pickup-day expiry lifecycle for round-trip orders."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .invoice_owner import ensure_invoice_refund_review
from .round_trip_notifications import notify_round_trip
from ..models import RoundTripOrder


def pickup_date(order):
    return timezone.localdate(order.renewed_at or order.created_at)


def expire_uncollected_round_trips(*, today=None):
    today = today or timezone.localdate()
    candidates = RoundTripOrder.objects.filter(status__in=("Pending", "Assigned"))
    candidates = candidates.filter(
        Q(is_renewed=False, created_at__date__lt=today)
        | Q(is_renewed=True, renewed_at__date__lt=today)
    ).filter(stops__sequence=1, stops__completed_at__isnull=True)
    result = {"expired": 0, "cancelled": 0}

    for order_id in candidates.values_list("pk", flat=True).distinct():
        with transaction.atomic():
            order = RoundTripOrder.objects.select_for_update().filter(pk=order_id).first()
            if (not order or order.status not in {"Pending", "Assigned"}
                    or pickup_date(order) >= today
                    or not order.stops.filter(sequence=1, completed_at__isnull=True).exists()):
                continue

            now = timezone.now()
            next_status = "Cancelled" if order.is_renewed else "Expired"
            former_biker_id = order.biker.user_id if order.biker_id else None
            order.status = next_status
            order.biker = None
            order.assigned_at = None
            update_fields = ["status", "biker", "assigned_at"]
            if next_status == "Expired":
                order.expired_at = now
                update_fields.append("expired_at")
            else:
                order.cancelled_at = now
                update_fields.append("cancelled_at")
            order.save(update_fields=update_fields)
            order.assignments.filter(ended_at__isnull=True).update(ended_at=now)
            if next_status == "Cancelled":
                ensure_invoice_refund_review(order.invoice)
            notify_round_trip(
                order=order,
                user_ids=[order.sender.user_id, order.recipient.user_id, former_biker_id],
                event_type=f"round_trip.{next_status.lower()}",
                title=f"Round trip {next_status.lower()}",
                body=("The pickup day ended before the parcel was collected. Renew the order to choose a new pickup day."
                      if next_status == "Expired" else
                      "The renewed pickup day ended before the parcel was collected."),
                suffix=f"{next_status.lower()}:{now.date().isoformat()}",
            )
            result[next_status.lower()] += 1
    return result
