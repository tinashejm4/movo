import base64
import hashlib
import secrets

from cryptography.fernet import Fernet
from django.contrib.auth.hashers import check_password, make_password
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .round_trip_notifications import send_round_trip_sms


OTP_MAX_FAILURES = 5


def _cipher():
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def issue_stop_otp(stop):
    code = f"{secrets.randbelow(1_000_000):06d}"
    stop.otp_hash = make_password(code)
    stop.otp_encrypted = _cipher().encrypt(code.encode()).decode()
    stop.otp_issued_at = timezone.now()
    stop.otp_used_at = None
    stop.otp_failures = 0
    stop.save(update_fields=[
        "otp_hash", "otp_encrypted", "otp_issued_at", "otp_used_at", "otp_failures",
    ])
    phone = stop.contact.user.username
    message = f"Movo {stop.order.slug} stop {stop.sequence} verification code: {code}. Give it only to your assigned driver at handover."
    transaction.on_commit(lambda: send_round_trip_sms(phone, message))


def reveal_stop_otp(stop):
    if not stop.otp_encrypted or stop.otp_used_at is not None:
        return None
    return _cipher().decrypt(stop.otp_encrypted.encode()).decode()


def check_stop_otp(stop, code):
    if stop.otp_used_at is not None:
        return "already_used"
    if stop.otp_failures >= OTP_MAX_FAILURES:
        return "too_many_attempts"
    if not stop.otp_issued_at:
        return "expired"
    if not check_password(code, stop.otp_hash):
        stop.otp_failures += 1
        stop.save(update_fields=["otp_failures"])
        return "invalid_code"
    return None
