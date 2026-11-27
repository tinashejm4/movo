"""Sender-authorized one-time renewal for expired round trips."""

from django.db import transaction
from django.utils import timezone

from ..models import RoundTripOrder
from .round_trip_dispatch import assign_pending_round_trips_safely
from .round_trip_notifications import notify_round_trip


@transaction.atomic
def renew_round_trip(*, order_id, user):
    order = (RoundTripOrder.objects.select_for_update()
             .select_related("sender__user", "recipient__user")
             .filter(pk=order_id).first())
    if not order:
        return None, "Round trip not found", 404
    if user.id != order.sender.user_id:
        return None, "Only the sender can renew this round trip", 403
    if order.status != "Expired" or order.is_renewed:
        return None, "Round trip cannot be renewed", 409

    order.is_renewed = True
    order.renewed_at = timezone.now()
    order.status = "Pending"
    order.save(update_fields=["is_renewed", "renewed_at", "status"])
    notify_round_trip(
        order=order, user_ids=[order.sender.user_id, order.recipient.user_id],
        event_type="round_trip.renewed", title="Round trip renewed",
        body="The sender renewed the round trip for a new pickup day.",
        suffix=order.renewed_at.isoformat(),
    )
    transaction.on_commit(assign_pending_round_trips_safely)
    return order, None, 200
