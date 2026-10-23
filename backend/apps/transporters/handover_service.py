"""Shared, retry-safe pickup and dropoff transitions."""

import hashlib
import hmac
import json
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.intracity.models import (
    HandoverAttempt,
    Invoice,
    Package,
    PackageAssignment,
    PackageImage,
    PackageStatus,
)
from apps.intracity.services.current_package_updates import notify_current_packages_changed
from apps.intracity.services.package_assignment import assign_pending_packages_safely
from apps.notifications.services import queue_package_customer_notification
from apps.users.models import Biker

from .services import CashConfirmationError, confirm_cash_received


def _fingerprint(*, package_id, stage, assignment_id, image_id, code, cash_received, captured_at):
    payload = json.dumps(
        [package_id, stage, str(assignment_id), image_id, code, cash_received,
         captured_at.isoformat() if captured_at else None],
        separators=(",", ":"),
    ).encode()
    return hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()


def _latest_status(package):
    return (
        PackageStatus.objects.filter(package=package)
        .order_by("-updated_at", "-pk")
        .values_list("status", flat=True)
        .first()
    )


def _record_attempt(*, request_id, package, biker, assignment, image, stage,
                    cash_received, fingerprint, captured_at, code_valid, outcome,
                    response_status, response_data, conflict_reason=""):
    if request_id is not None:
        if outcome == "conflict":
            response_data = {
                **response_data,
                "request_id": str(request_id),
                "review_status": "pending",
            }
        HandoverAttempt.objects.create(
            id=request_id,
            package=package,
            biker=biker,
            assignment=assignment,
            image=image,
            stage=stage,
            cash_received=cash_received,
            fingerprint=fingerprint,
            captured_at=captured_at,
            code_valid=code_valid,
            outcome=outcome,
            response_status=response_status,
            response_data=response_data,
            conflict_reason=conflict_reason,
        )
    return response_status, response_data


def _transition(package, *, stage, biker_user, cash_received):
    """Return (HTTP status, response, reason); caller holds the package lock."""
    if not package.biker or package.biker.user_id != biker_user.id:
        return 409, {"error": "Assignment changed"}, "assignment_changed"

    current_status = _latest_status(package)
    allowed = {"Pending", "Assigned"} if stage == "pickup" else {"In Transit"}
    if current_status not in allowed:
        return 409, {"error": "Package stage changed", "current_status": current_status}, "stage_changed"

    invoice = Invoice.objects.select_for_update().filter(package=package).first()
    if invoice is None:
        return 409, {"error": "Invoice is missing"}, "invoice_missing"
    cash_due = (stage == "dropoff") == invoice.is_pay_forward
    if cash_received:
        if invoice.is_paid or not cash_due:
            return 409, {"error": "Cash cannot be recorded at this stage"}, "cash_conflict"
        try:
            confirm_cash_received(package_id=package.pk, biker_user=biker_user)
        except CashConfirmationError as error:
            return 409, {"error": str(error)}, "cash_conflict"
    elif cash_due and not invoice.is_paid:
        return 409, {"error": "Cash must be confirmed before handover"}, "cash_required"

    PackageStatus.objects.create(
        package=package,
        status="In Transit" if stage == "pickup" else "Delivered",
    )
    if stage == "pickup":
        notify_current_packages_changed(package=package, reason="picked_up")
        queue_package_customer_notification(package=package, event_type="package.picked_up")
        return 200, {
            "message": "Package collected successfully",
            "package_id": package.pk,
            "status": "In Transit",
        }, ""

    package.delivered_at = timezone.now()
    package.save(update_fields=["delivered_at"])
    notify_current_packages_changed(package=package, reason="delivered")
    queue_package_customer_notification(package=package, event_type="package.delivered")
    transaction.on_commit(assign_pending_packages_safely)
    return 200, {
        "message": "Package delivered successfully",
        "package_id": package.pk,
        "status": "Delivered",
        "delivered_at": package.delivered_at.isoformat(),
    }, ""


@transaction.atomic
def process_handover(*, package_id, biker_user, stage, code, request_id=None,
                     assignment_id=None, image_id=None, cash_received=False,
                     captured_at=None):
    package = Package.objects.select_for_update().filter(pk=package_id).first()
    if package is None:
        return 404, {"error": "Package not found"}

    fingerprint = None
    if request_id is not None:
        fingerprint = _fingerprint(
            package_id=package_id, stage=stage, assignment_id=assignment_id,
            image_id=image_id, code=code, cash_received=cash_received,
            captured_at=captured_at,
        )
        existing = HandoverAttempt.objects.filter(pk=request_id).first()
        if existing:
            if existing.biker.user_id != biker_user.id or not secrets.compare_digest(
                existing.fingerprint, fingerprint
            ):
                return 409, {"error": "request_id was reused with different data"}
            return existing.response_status, existing.response_data

    biker = Biker.objects.filter(user=biker_user).first()
    if biker is None:
        return 403, {"error": "Driver profile not found"}
    if request_id is None and (
        not package.biker or package.biker.user_id != biker_user.id
    ):
        return 403, {"error": "You are not assigned to this package"}
    assignment = image = None
    if request_id is not None:
        assignment = PackageAssignment.objects.filter(
            pk=assignment_id, package=package, biker=biker
        ).first()
        if image_id is not None:
            image = PackageImage.objects.filter(
                pk=image_id, package=package, assignment=assignment,
                uploaded_by=biker_user, stage=stage,
            ).first()
        if assignment is None or (stage == "pickup" and image is None) or (image_id is not None and image is None):
            return 400, {"error": "Valid assignment_id and pickup image_id are required"}
        if image is not None and HandoverAttempt.objects.filter(
            image=image, outcome__in=["accepted", "conflict"]
        ).exists():
            return 409, {"error": "POD image is already linked to another handover"}

    valid_code = secrets.compare_digest(
        package.sender_code if stage == "pickup" else package.receiver_code, code
    )
    if not valid_code:
        data = {"error": "Invalid sender code" if stage == "pickup" else "Invalid receiver code"}
        return _record_attempt(
            request_id=request_id, package=package, biker=biker,
            assignment=assignment, image=image, stage=stage,
            cash_received=cash_received, fingerprint=fingerprint,
            captured_at=captured_at, code_valid=False, outcome="rejected",
            response_status=400, response_data=data,
        )

    if request_id is not None:
        latest_assignment = PackageAssignment.objects.filter(
            package=package
        ).order_by("-assigned_at", "-pk").first()
        if latest_assignment is None or latest_assignment.pk != assignment.pk:
            data = {"error": "Assignment changed"}
            return _record_attempt(
                request_id=request_id, package=package, biker=biker,
                assignment=assignment, image=image, stage=stage,
                cash_received=cash_received, fingerprint=fingerprint,
                captured_at=captured_at, code_valid=True, outcome="conflict",
                response_status=409, response_data=data,
                conflict_reason="assignment_changed",
            )

    result_status, data, reason = _transition(
        package, stage=stage, biker_user=biker_user, cash_received=cash_received
    )
    if request_id is None:
        if reason == "assignment_changed":
            return 403, {"error": "You are not assigned to this package"}
        if reason:
            return 400, data
        return result_status, data
    return _record_attempt(
        request_id=request_id, package=package, biker=biker,
        assignment=assignment, image=image, stage=stage,
        cash_received=cash_received, fingerprint=fingerprint,
        captured_at=captured_at, code_valid=True,
        outcome="accepted" if not reason else "conflict",
        response_status=result_status, response_data=data, conflict_reason=reason,
    )


@transaction.atomic
def resolve_handover_attempt(*, attempt_id, reviewer, action, reason):
    attempt_package_id = HandoverAttempt.objects.filter(pk=attempt_id).values_list(
        "package_id", flat=True
    ).first()
    if attempt_package_id is None:
        return 404, {"error": "Review case not found"}
    package = Package.objects.select_for_update().filter(pk=attempt_package_id).first()
    if package is None:
        return 404, {"error": "Package not found"}
    attempt = HandoverAttempt.objects.select_for_update().filter(pk=attempt_id).first()
    if attempt is None:
        return 404, {"error": "Review case not found"}
    if attempt.outcome != "conflict":
        return 409, {"error": "Only unresolved conflicts can be reviewed"}
    if action == "reject":
        attempt.outcome = "rejected"
        attempt.response_data = {
            "error": "Handover rejected by staff",
            "request_id": str(attempt.pk),
            "review_status": "rejected",
        }
        attempt.resolved_by = reviewer
        attempt.resolution_reason = reason
        attempt.resolved_at = timezone.now()
        attempt.save(update_fields=[
            "outcome", "response_data", "resolved_by", "resolution_reason", "resolved_at"
        ])
        return 200, {"id": str(attempt.pk), "outcome": "rejected"}

    latest_assignment = PackageAssignment.objects.filter(
        package=package
    ).order_by("-assigned_at", "-pk").first()
    if latest_assignment is None or latest_assignment.pk != attempt.assignment_id:
        return 409, {"error": "Assignment is still changed"}
    if not attempt.code_valid or (attempt.stage == "pickup" and not attempt.image_id):
        return 409, {"error": "Code or POD has not been verified"}
    result_status, data, conflict_reason = _transition(
        package, stage=attempt.stage, biker_user=attempt.biker.user,
        cash_received=attempt.cash_received,
    )
    if conflict_reason:
        return 409, data
    attempt.outcome = "accepted"
    attempt.conflict_reason = ""
    attempt.response_status = result_status
    attempt.response_data = data
    attempt.resolved_by = reviewer
    attempt.resolution_reason = reason
    attempt.resolved_at = timezone.now()
    attempt.save(update_fields=[
        "outcome", "conflict_reason", "response_status", "response_data",
        "resolved_by", "resolution_reason", "resolved_at",
    ])
    return 200, {"id": str(attempt.pk), "outcome": "accepted", "result": data}
