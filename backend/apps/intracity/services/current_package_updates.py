"""WebSocket notifications for the customer current-packages dashboard."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction


logger = logging.getLogger(__name__)

CURRENT_PACKAGE_UPDATE_REASONS = frozenset(
    {"created", "assigned", "picked_up", "cancelled", "delivered"}
)


def current_packages_group_name(user_id):
    """Return the private Channels group for one authenticated customer."""
    return f"current_packages_user_{user_id}"


def notify_current_packages_changed(*, package, reason):
    """Publish a minimal dashboard invalidation after the transaction commits."""
    if reason not in CURRENT_PACKAGE_UPDATE_REASONS:
        raise ValueError(f"Unsupported current-package update reason: {reason}")

    recipient_user_ids = tuple(
        {
            package.sender.user_id,
            package.receiver.user_id,
        }
    )
    transaction.on_commit(
        lambda: _publish_current_packages_changed(
            package_id=package.id,
            recipient_user_ids=recipient_user_ids,
            reason=reason,
        )
    )


def _publish_current_packages_changed(
    *, package_id, recipient_user_ids, reason
):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning(
            "Current-packages WebSocket publish skipped: no channel layer configured"
        )
        return

    event = {
        "type": "current_packages.changed",
        "payload": {
            "package_id": package_id,
            "reason": reason,
        },
    }
    for user_id in recipient_user_ids:
        try:
            async_to_sync(channel_layer.group_send)(
                current_packages_group_name(user_id),
                event,
            )
        except Exception:
            logger.exception(
                "Current-packages WebSocket publish failed: package_id=%s "
                "user_id=%s reason=%s",
                package_id,
                user_id,
                reason,
            )
