from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import (RoundTripAssignment, RoundTripCashEvent,
                      RoundTripOrder, RoundTripStop,
                      RoundTripVerificationAttempt)
from .round_trip_notifications import notify_round_trip
from .round_trip_otp import check_stop_otp, issue_stop_otp


def _active_stop(order):
    return order.stops.filter(completed_at__isnull=True).order_by("sequence").first()


def _current_assignment(order, assignment_id, user):
    return RoundTripAssignment.objects.filter(
        pk=assignment_id, order=order, biker=order.biker, biker__user=user,
        ended_at__isnull=True,
    ).first()


def _advance_order(order, stop, assignment, now):
    stop.otp_used_at = now
    stop.completed_at = now
    stop.save(update_fields=["otp_used_at", "completed_at"])
    stop.actions.filter(completed_at__isnull=True).update(completed_at=now)
    if stop.kind == "recipient":
        notify_round_trip(
            order=order, user_ids=[order.sender.user_id],
            event_type="round_trip.pod_ready", title="Delivery proof available",
            body="The recipient handoff proof is available in your round-trip order.",
            suffix=str(stop.pk),
        )
    next_stop = _active_stop(order)
    if next_stop is None:
        order.status = "Completed"
        order.completed_at = now
        order.save(update_fields=["status", "completed_at"])
        assignment.ended_at = now
        assignment.save(update_fields=["ended_at"])
        notify_round_trip(
            order=order, user_ids=[order.sender.user_id, order.recipient.user_id],
            event_type="round_trip.completed", title="Round trip completed",
            body="Delivery and cash return are complete.", suffix=str(stop.pk),
        )
        from .package_assignment import assign_pending_packages_safely
        transaction.on_commit(assign_pending_packages_safely)
    else:
        order.status = "In Transit"
        order.save(update_fields=["status"])
        issue_stop_otp(next_stop, assignment)


@transaction.atomic
def verify_round_trip_stop(*, order_id, stop_id, user, data):
    order = RoundTripOrder.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        return None, "Order not found", 404
    assignment = _current_assignment(order, data["assignment_id"], user)
    if assignment is None:
        return None, "Active assignment required", 403
    stop = RoundTripStop.objects.select_for_update().filter(pk=stop_id, order=order).first()
    if stop is None:
        return None, "Stop not found", 404
    if order.status not in {"Assigned", "In Transit"}:
        return None, "Order is not ready for verification", 409
    if _active_stop(order).pk != stop.pk:
        return None, "Only the active stop can be verified", 409
    reason = check_stop_otp(stop, assignment, data["otp"])
    if reason:
        RoundTripVerificationAttempt.objects.create(
            stop=stop, assignment=assignment, biker=assignment.biker,
            reason=reason,
        )
        return None, reason, 400
    if stop.kind == "recipient" and not hasattr(stop, "pod"):
        return None, "Recipient POD is required", 400
    if stop.kind == "recipient" and stop.pod.assignment_id != assignment.pk:
        return None, "POD belongs to a different assignment", 409

    if stop.kind in {"recipient", "sender_return"}:
        amount = data.get("cash_amount")
        currency = data.get("cash_currency")
        if amount is None or currency is None:
            return None, "cash_amount and cash_currency are required", 400
        expected = order.cash_amount
        if stop.kind == "sender_return":
            collected = order.cash_events.filter(kind="collected").first()
            if collected is None:
                return None, "Cash collection has not been recorded", 409
            expected = collected.amount
        RoundTripCashEvent.objects.create(
            order=order, stop=stop, assignment=assignment,
            kind="collected" if stop.kind == "recipient" else "returned",
            amount=amount, currency=currency, recorded_by=user,
        )
        if amount != expected or currency != order.cash_currency:
            stop.otp_used_at = timezone.now()
            stop.save(update_fields=["otp_used_at"])
            order.status = "Exception"
            order.exception_reason = "cash_mismatch"
            order.save(update_fields=["status", "exception_reason"])
            RoundTripVerificationAttempt.objects.create(
                stop=stop, assignment=assignment, biker=assignment.biker,
                accepted=False, reason="cash_mismatch",
            )
            notify_round_trip(
                order=order, user_ids=[order.sender.user_id],
                event_type="round_trip.exception", title="Round trip needs review",
                body="A cash amount needs staff review.", suffix=f"{stop.pk}:cash",
            )
            return None, "Cash amount differs from the expected amount; staff review required", 409

    now = timezone.now()
    RoundTripVerificationAttempt.objects.create(
        stop=stop, assignment=assignment, biker=assignment.biker, accepted=True,
    )
    _advance_order(order, stop, assignment, now)
    return order, None, 200


@transaction.atomic
def resend_round_trip_otp(*, order_id, stop_id, user, is_staff=False):
    order = RoundTripOrder.objects.select_for_update().filter(pk=order_id).first()
    if not order:
        return "Order not found", 404
    stop = _active_stop(order)
    if not stop or stop.pk != stop_id or order.status not in {"Assigned", "In Transit"}:
        return "Only the active stop can receive a new code", 409
    if user.pk != stop.contact.user_id and not is_staff:
        return "Stop contact or staff access required", 403
    assignment = order.assignments.filter(ended_at__isnull=True).order_by("-assigned_at").first()
    if not assignment:
        return "Active assignment required", 409
    if stop.otp_issued_at and timezone.now() - stop.otp_issued_at < timedelta(seconds=60):
        return "Wait one minute before requesting another code", 429
    issue_stop_otp(stop, assignment)
    return None, 200
