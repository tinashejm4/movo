import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from .round_trip_notifications import send_round_trip_sms


OTP_LIFETIME = timedelta(hours=24)
OTP_MAX_FAILURES = 5


def issue_stop_otp(stop, assignment):
    code = f"{secrets.randbelow(1_000_000):06d}"
    stop.otp_hash = make_password(code)
    stop.otp_issued_at = timezone.now()
    stop.otp_used_at = None
    stop.otp_failures = 0
    stop.otp_assignment = assignment
    stop.save(update_fields=["otp_hash", "otp_issued_at", "otp_used_at",
                             "otp_failures", "otp_assignment"])
    phone = stop.contact.user.username
    message = f"Movo {stop.order.slug} stop {stop.sequence} verification code: {code}. Give it only to your assigned driver at handover."
    transaction.on_commit(lambda: send_round_trip_sms(phone, message))


def check_stop_otp(stop, assignment, code):
    if stop.otp_assignment_id != assignment.pk:
        return "assignment_changed"
    if stop.otp_used_at is not None:
        return "already_used"
    if stop.otp_failures >= OTP_MAX_FAILURES:
        return "too_many_attempts"
    if not stop.otp_issued_at or timezone.now() - stop.otp_issued_at > OTP_LIFETIME:
        return "expired"
    if not check_password(code, stop.otp_hash):
        stop.otp_failures += 1
        stop.save(update_fields=["otp_failures"])
        return "invalid_code"
    return None
