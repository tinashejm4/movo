import base64
import logging

import requests
from django.conf import settings
from django.db import transaction

from apps.notifications.models import Notification, NotificationOutbox
from apps.notifications.services import _enqueue
from apps.users.utils import normalize_zimbabwean_number

logger = logging.getLogger(__name__)


def send_round_trip_sms(phone_number, message):
    if not settings.TXTCONSOLE_SYSTEM_ID or not settings.TXTCONSOLE_PASSWORD:
        logger.warning("Round-trip SMS skipped: provider credentials missing")
        return False
    credentials = f"{settings.TXTCONSOLE_SYSTEM_ID}:{settings.TXTCONSOLE_PASSWORD}".encode()
    payload = {
        "destination": f"263{normalize_zimbabwean_number(phone_number)}",
        "text": message,
        "source": settings.TXTCONSOLE_SOURCE,
    }
    headers = {
        "accept": "application/json", "content-type": "application/json",
        "authorization": "Basic " + base64.b64encode(credentials).decode(),
    }
    try:
        response = requests.post(settings.TXTCONSOLE_SMS_URL + "/sms", json=payload,
                                 headers=headers, timeout=20)
        return response.status_code < 400
    except requests.RequestException:
        logger.exception("Round-trip SMS failed")
        return False


def notify_round_trip(*, order, user_ids, event_type, title, body, suffix=""):
    for user_id in set(user_ids):
        if not user_id:
            continue
        key = f"{event_type}:{order.pk}:{user_id}:{suffix}"
        if NotificationOutbox.objects.filter(idempotency_key=key).exists():
            continue
        notification = Notification.objects.create(
            user_id=user_id, event_type=event_type, title=title, body=body,
            payload={"type": event_type, "round_trip_id": order.pk, "slug": order.slug},
        )
        outbox = NotificationOutbox.objects.create(notification=notification,
                                                    idempotency_key=key)
        transaction.on_commit(lambda outbox_id=outbox.pk: _enqueue(outbox_id))
