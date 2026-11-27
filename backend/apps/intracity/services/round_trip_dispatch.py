import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.users.models import Biker

from ..models import RoundTripAssignment, RoundTripOrder
from .package_assignment import is_biker_busy
from .round_trip_notifications import notify_round_trip

logger = logging.getLogger(__name__)


@transaction.atomic
def assign_pending_round_trips():
    bikers = list(Biker.objects.select_for_update().order_by("pk"))
    orders = list(RoundTripOrder.objects.select_for_update().filter(
        status="Pending",
    ).filter(
        Q(is_renewed=False, created_at__date=timezone.localdate())
        | Q(is_renewed=True, renewed_at__date=timezone.localdate())
    ).order_by("-is_fast_delivery", "created_at", "pk"))
    free = [biker for biker in bikers if not is_biker_busy(biker)]
    payloads = []
    for order, biker in zip(orders, free):
        order.biker = biker
        order.assigned_at = timezone.now()
        order.status = "Assigned"
        order.save(update_fields=["biker", "assigned_at", "status"])
        assignment = RoundTripAssignment.objects.create(order=order, biker=biker)
        first_stop = order.stops.get(sequence=1)
        notify_round_trip(
            order=order, user_ids=[order.sender.user_id, order.recipient.user_id, biker.user_id],
            event_type="round_trip.assigned", title="Round trip assigned",
            body="A driver has been assigned to the round trip.", suffix=str(assignment.pk),
        )
        payloads.append({"round_trip_id": order.pk, "slug": order.slug,
                         "biker_id": biker.pk,
                         "active_stop_id": first_stop.pk})
    transaction.on_commit(lambda: _publish_assignments(payloads))
    return {"assigned_count": len(payloads), "assigned_orders": payloads,
            "unassigned_count": max(0, len(orders) - len(payloads))}


def assign_pending_round_trips_safely():
    try:
        return assign_pending_round_trips()
    except Exception:
        logger.exception("Round-trip auto-dispatch failed")
        return {"assigned_count": 0, "assigned_orders": []}


def _publish_assignments(payloads):
    layer = get_channel_layer()
    if not layer:
        return
    for payload in payloads:
        try:
            async_to_sync(layer.group_send)(
                f"round_trip_{payload['round_trip_id']}",
                {"type": "round_trip.assigned", "payload": payload},
            )
        except Exception:
            logger.exception("Could not publish round-trip assignment %s", payload["round_trip_id"])
