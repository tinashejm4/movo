import base64
import logging

import requests
from django.conf import settings

from apps.users.utils import normalize_zimbabwean_number


logger = logging.getLogger(__name__)


def build_package_booking_message(package, invoice):
    address_char_len = 25

    if package.is_sender_initiated:
        address = _truncate_address(package.dropoff_address, address_char_len)
        sender = package.sender.user
        sender_name = f"{sender.first_name} {sender.last_name}".strip()
        message = (
            f"Incoming package from {sender_name} to you @{address}. "
            f"Collection OTP: {package.receiver_code}. "
            f"Tracking No: {package.slug}."
        )
        if invoice.is_pay_forward:
            return " ".join(
                [message, f"Amount Due on Delivery: ${invoice.amount:.2f}. movo.co.zw/check?p={package.id}"]
            )
        return " ".join(
            [message, f"movo.co.zw/check?p={package.id}"]
        )

    address = _truncate_address(package.pickup_address, address_char_len)
    receiver = package.receiver.user
    receiver_name = f"{receiver.first_name} {receiver.last_name}".strip()
    message = (
        f"A package for {receiver_name} has been booked from you @{address}. "
        f"Collection OTP: {package.sender_code}. "
        f"Tracking No: {package.slug}."
    )
    if not invoice.is_pay_forward:
        return " ".join(
            [message, f"Amount Due on Collection: ${invoice.amount:.2f}. movo.co.zw/check?p={package.id}"]
        )
    return " ".join([message, f"movo.co.zw/check?p={package.id}"])


def send_package_booking_sms(phone_number, package, invoice):
    """Send the booking SMS without failing the package-creation workflow."""
    if not settings.TXTCONSOLE_SYSTEM_ID or not settings.TXTCONSOLE_PASSWORD:
        logger.error(
            "Package SMS skipped for package %s: provider credentials are missing",
            package.slug,
        )
        return False

    credentials = (
        f"{settings.TXTCONSOLE_SYSTEM_ID}:{settings.TXTCONSOLE_PASSWORD}".encode()
    )
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": "Basic " + base64.b64encode(credentials).decode(),
    }
    payload = {
        "destination": f"263{normalize_zimbabwean_number(phone_number)}",
        "text": build_package_booking_message(package, invoice),
        "source": settings.TXTCONSOLE_SOURCE,
    }
    if settings.TXTCONSOLE_RECEIPT_URL:
        payload["receiptURL"] = settings.TXTCONSOLE_RECEIPT_URL

    try:
        provider_response = requests.post(
            settings.TXTCONSOLE_SMS_URL + "/sms",
            json=payload,
            headers=headers,
            timeout=20,
        )
    except requests.RequestException:
        logger.exception(
            "txtConsole OTP send exception for package %s",
            package.slug,
        )
        return False

    if provider_response.status_code < 400:
        return True

    try:
        error_details = provider_response.json()
    except ValueError:
        error_details = {"message": provider_response.text}

    logger.warning(
        "txtConsole OTP send failed for package %s: %s",
        package.slug,
        error_details,
    )
    return False


def _truncate_address(address, max_length):
    if len(address) > max_length:
        return address[:max_length] + "..."
    return address
