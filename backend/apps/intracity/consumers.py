import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer


logger = logging.getLogger(__name__)


class PackageAssignmentConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.global_group = "package_assignments"
        self.package_id = self.scope["url_route"]["kwargs"].get("package_id")
        self.group_name = (
            f"package_{self.package_id}"
            if self.package_id is not None
            else self.global_group
        )

        self.subscribed_to_groups = False
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            self.subscribed_to_groups = True
        except Exception as exc:
            logger.warning("WebSocket group subscribe failed: %s", exc)

        await self.accept()
        await self.send(
            text_data=json.dumps(
                {
                    "event": "connected",
                    "data": {
                        "group": self.group_name,
                        "package_id": self.package_id,
                        "subscribed": self.subscribed_to_groups,
                    },
                }
            )
        )

    async def disconnect(self, close_code):
        if not self.subscribed_to_groups:
            return

        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception as exc:
            logger.warning("WebSocket group unsubscribe failed: %s", exc)

    async def package_assigned(self, event):
        logger.info(
            "WebSocket event delivered: package_assigned package_id=%s",
            event.get("payload", {}).get("package_id"),
        )
        await self.send(
            text_data=json.dumps(
                {
                    "event": "package_assigned",
                    "data": event["payload"],
                },
                default=str,
            )
        )
