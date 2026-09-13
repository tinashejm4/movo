import logging

from django.db import transaction

from .models import Notification, NotificationOutbox


EVENT_COPY = {
    "package.assigned": ("Driver assigned", "A driver has been assigned to your package."),
    "package.picked_up": ("Package collected", "Your package has been collected and is on its way."),
    "package.delivered": ("Package delivered", "Your package has been delivered."),
    "package.cancelled": ("Package cancelled", "This package has been cancelled."),
}

logger = logging.getLogger(__name__)


def queue_package_notification(
    *, package, event_type, recipient_user_ids, title=None, body=None
):
    """Persist recipient notifications and enqueue FCM only after commit."""
    try:
        default_title, default_body = EVENT_COPY[event_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported package notification: {event_type}") from exc

    title = title or default_title
    body = body or default_body
    payload = {
        "type": event_type,
        "package_id": str(package.id),
        "package_slug": package.slug,
    }
    for user_id in set(recipient_user_ids):
        if not user_id:
            continue
        notification = Notification.objects.create(
            user_id=user_id,
            package=package,
            event_type=event_type,
            title=title,
            body=body,
            payload=payload,
        )
        outbox = NotificationOutbox.objects.create(
            notification=notification,
            idempotency_key=f"{event_type}:{package.id}:{user_id}:{notification.id}",
        )
        transaction.on_commit(lambda outbox_id=outbox.id: _enqueue(outbox_id))


def queue_package_assignment_notifications(*, package, biker):
    """Biker receives a job alert; sender and receiver get a driver update."""
    queue_package_notification(
        package=package,
        event_type="package.assigned",
        recipient_user_ids=[package.sender.user_id, package.receiver.user_id],
    )
    queue_package_notification(
        package=package,
        event_type="package.assigned",
        recipient_user_ids=[biker.user_id],
        title="New delivery assigned",
        body="A package has been assigned to you.",
    )


def queue_package_customer_notification(*, package, event_type):
    queue_package_notification(
        package=package,
        event_type=event_type,
        recipient_user_ids=[package.sender.user_id, package.receiver.user_id],
    )


def _enqueue(outbox_id):
    from .tasks import deliver_notification_outbox

    try:
        deliver_notification_outbox.delay(outbox_id)
    except Exception:
        # The committed outbox row remains pending and can be replayed; never
        # turn a completed package transition into an HTTP failure.
        logger.exception("Could not enqueue notification outbox=%s", outbox_id)


def enqueue_pending_notification_outboxes(*, limit=None):
    """Replay committed outbox records that were created while no worker ran."""
    queryset = NotificationOutbox.objects.filter(
        status=NotificationOutbox.Status.PENDING
    ).order_by("id")
    if limit is not None:
        queryset = queryset[:limit]

    outbox_ids = list(queryset.values_list("id", flat=True))
    for outbox_id in outbox_ids:
        _enqueue(outbox_id)
    return len(outbox_ids)
