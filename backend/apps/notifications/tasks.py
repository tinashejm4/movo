import json
import logging
import os

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from firebase_admin import credentials, initialize_app, messaging

from .models import DeviceToken, NotificationOutbox

logger = logging.getLogger(__name__)


def _firebase_app():
    """Initialize Firebase Admin once, from a mounted file or JSON secret."""
    from firebase_admin import get_app

    try:
        return get_app()
    except ValueError:
        credentials_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "").strip()
        credentials_json = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
        if credentials_path:
            credential = credentials.Certificate(credentials_path)
        elif credentials_json:
            credential = credentials.Certificate(json.loads(credentials_json))
        else:
            raise RuntimeError(
                "Set FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON for FCM delivery"
            )
        return initialize_app(credential)


@shared_task(bind=True, max_retries=5)
def deliver_notification_outbox(self, outbox_id):
    try:
        # Retries/replays can result in multiple Celery messages for one
        # durable outbox row. Only one worker may deliver it at a time.
        with transaction.atomic():
            try:
                outbox = (
                    NotificationOutbox.objects.select_for_update()
                    .select_related("notification")
                    .get(pk=outbox_id)
                )
            except NotificationOutbox.DoesNotExist:
                return
            if outbox.status in {
                NotificationOutbox.Status.DELIVERED,
                NotificationOutbox.Status.DELIVERING,
            }:
                return
            outbox.status = NotificationOutbox.Status.DELIVERING
            outbox.attempts += 1
            outbox.save(update_fields=["status", "attempts"])

        notification = outbox.notification
        tokens = list(
            DeviceToken.objects.filter(user=notification.user, is_active=True).values_list(
                "token", flat=True
            )
        )
        if tokens:
            _firebase_app()
            response = messaging.send_each_for_multicast(
                messaging.MulticastMessage(
                    tokens=tokens,
                    notification=messaging.Notification(
                        title=notification.title, body=notification.body
                    ),
                    data={key: str(value) for key, value in notification.payload.items()},
                )
            )
            stale_tokens = [
                tokens[index]
                for index, send_response in enumerate(response.responses)
                if not send_response.success
                and isinstance(
                    send_response.exception,
                    (messaging.UnregisteredError, messaging.SenderIdMismatchError),
                )
            ]
            if stale_tokens:
                DeviceToken.objects.filter(token__in=stale_tokens).update(is_active=False)

        outbox.status = NotificationOutbox.Status.DELIVERED
        outbox.last_error = ""
        outbox.delivered_at = timezone.now()
        outbox.save(update_fields=["status", "last_error", "delivered_at"])
    except Exception as exc:
        outbox.last_error = str(exc)[:2000]
        if self.request.retries >= self.max_retries:
            outbox.status = NotificationOutbox.Status.FAILED
            outbox.save(update_fields=["status", "last_error"])
            logger.exception("FCM delivery permanently failed for outbox=%s", outbox_id)
            return
        outbox.status = NotificationOutbox.Status.PENDING
        outbox.save(update_fields=["status", "last_error"])
        raise self.retry(exc=exc, countdown=min(2 ** self.request.retries * 30, 900))
