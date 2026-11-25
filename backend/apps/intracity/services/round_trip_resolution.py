from django.db import transaction
from django.utils import timezone

from ..models import RoundTripCashEvent, RoundTripOrder, RoundTripResolution
from .invoice_owner import ensure_invoice_refund_review
from .round_trip_notifications import notify_round_trip
from .round_trip_stop import _active_stop, _current_assignment, _advance_order


@transaction.atomic
def fail_round_trip_stop(*, order_id, stop_id, user, data):
    order = RoundTripOrder.objects.select_for_update().filter(pk=order_id).first()
    if not order:
        return None, "Order not found", 404
    assignment = _current_assignment(order, user)
    if not assignment:
        return None, "Active assignment required", 403
    stop = _active_stop(order)
    if not stop or stop.pk != stop_id or order.status not in {"Assigned", "In Transit"}:
        return None, "Only the active stop can be reported failed", 409
    order.status = "Exception"
    order.exception_reason = data["reason"]
    order.save(update_fields=["status", "exception_reason"])
    notify_round_trip(
        order=order, user_ids=[order.sender.user_id],
        event_type="round_trip.exception", title="Round trip needs review",
        body="The driver reported a stop issue.", suffix=f"{stop.pk}:failed",
    )
    return order, None, 200


@transaction.atomic
def cancel_round_trip(*, order_id, user, reason):
    order = RoundTripOrder.objects.select_for_update().filter(pk=order_id, sender__user=user).first()
    if not order:
        return None, "Order not found", 404
    if order.status not in {"Pending", "Assigned"} or order.stops.filter(sequence=1, completed_at__isnull=False).exists():
        return None, "Cancellation is available only before pickup", 409
    now = timezone.now()
    order.status = "Cancelled"
    order.cancelled_at = now
    order.exception_reason = reason
    order.save(update_fields=["status", "cancelled_at", "exception_reason"])
    order.assignments.filter(ended_at__isnull=True).update(ended_at=now)
    order.stops.update(otp_hash="", otp_used_at=now)
    ensure_invoice_refund_review(order.invoice)
    notify_round_trip(
        order=order, user_ids=[order.sender.user_id, order.recipient.user_id,
                              order.biker.user_id if order.biker_id else None],
        event_type="round_trip.cancelled", title="Round trip cancelled",
        body="The round trip was cancelled before pickup.", suffix=str(now.timestamp()),
    )
    from .package_assignment import assign_pending_packages_safely
    transaction.on_commit(assign_pending_packages_safely)
    return order, None, 200


@transaction.atomic
def resolve_round_trip(*, order_id, user, data):
    order = RoundTripOrder.objects.select_for_update().filter(pk=order_id).first()
    if not order:
        return None, "Order not found", 404
    if order.status != "Exception":
        return None, "Order is not in exception", 409
    outcome = data["outcome"]
    collected = data.get("actual_collected")
    returned = data.get("actual_returned")
    stop = _active_stop(order) if outcome == "resume" else None
    assignment = (order.assignments.filter(ended_at__isnull=True).order_by("-assigned_at").first()
                  if outcome == "resume" else None)
    if outcome == "resume" and (not stop or not assignment):
        return None, "No active assignment to resume", 409
    cash_event = RoundTripCashEvent.objects.filter(stop=stop).first() if stop else None
    if outcome == "resume" and order.exception_reason == "cash_mismatch":
        expected = order.cash_amount
        if stop.kind == "sender_return":
            event = order.cash_events.filter(kind="collected").first()
            expected = event.amount if event else None
        confirmed = collected if stop.kind == "recipient" else returned
        if not cash_event or expected is None or confirmed != expected:
            return None, "Cash mismatch must be fully reconciled before resuming", 400
    if outcome == "cancelled":
        recipient_stop = order.stops.get(sequence=2)
        if recipient_stop.completed_at is not None:
            return None, "Delivered parcel requires route completion", 409
        if order.stops.get(sequence=1).completed_at is not None and not data.get("item_returned_to_sender"):
            return None, "Confirm item return before cancelling", 400
        collected_event = order.cash_events.filter(kind="collected").first()
        if collected_event:
            if collected != collected_event.amount or returned != collected_event.amount:
                return None, "Collected cash must be returned before cancelling", 400
    was_cash_mismatch = order.exception_reason == "cash_mismatch"
    RoundTripResolution.objects.create(
        order=order, outcome=outcome, reason=data["reason"],
        actual_collected=collected, actual_returned=returned, resolved_by=user,
        reported_amount=cash_event.amount if cash_event else None,
        reported_currency=cash_event.currency if cash_event else "",
        item_returned_to_sender=data.get("item_returned_to_sender", False),
    )
    order.exception_reason = ""
    if outcome == "resume":
        if cash_event and was_cash_mismatch:
            cash_event.amount = collected if stop.kind == "recipient" else returned
            cash_event.currency = order.cash_currency
            cash_event.save(update_fields=["amount", "currency"])
            _advance_order(order, stop, assignment, timezone.now())
        else:
            stop.otp_failures = 0
            stop.save(update_fields=["otp_failures"])
            order.status = "Assigned" if stop.sequence == 1 else "In Transit"
    else:
        order.status = "Cancelled"
        now = timezone.now()
        order.cancelled_at = now
        order.assignments.filter(ended_at__isnull=True).update(ended_at=now)
        from .package_assignment import assign_pending_packages_safely
        transaction.on_commit(assign_pending_packages_safely)
    order.save()
    if outcome == "cancelled":
        ensure_invoice_refund_review(order.invoice)
    return order, None, 200


