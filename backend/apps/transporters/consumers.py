import asyncio
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.users.models import Biker


logger = logging.getLogger(__name__)


class BikerOrderConsumer(AsyncWebsocketConsumer):
    """Deliver newly assigned collection orders to an authenticated biker."""

    subscribed_to_group = False

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            reason = self.scope.get("auth_error") or "Authentication required."
            await self.close(code=4401, reason=reason)
            return

        biker = await self._get_biker(user.id)
        if not biker:
            await self.close(code=4403, reason="Biker access is required.")
            return

        self.group_name = f"biker_orders_{biker.id}"
        await self.accept()

        try:
            await asyncio.wait_for(
                self.channel_layer.group_add(self.group_name, self.channel_name),
                timeout=5,
            )
            self.subscribed_to_group = True
        except Exception as exc:
            logger.warning("Biker order subscription failed: %s", exc)

        await self.send(
            text_data=json.dumps(
                {
                    "event": "connected",
                    "data": {
                        "group": self.group_name,
                        "subscribed": self.subscribed_to_group,
                    },
                }
            )
        )

    async def disconnect(self, close_code):
        if not self.subscribed_to_group:
            return

        try:
            await asyncio.wait_for(
                self.channel_layer.group_discard(self.group_name, self.channel_name),
                timeout=5,
            )
        except Exception as exc:
            logger.warning("Biker order unsubscribe failed: %s", exc)

    async def order_assigned(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "event": "order_assigned",
                    "data": event.get("payload", {}),
                },
                default=str,
            )
        )

    @database_sync_to_async
    def _get_biker(self, user_id):
        return Biker.objects.filter(user_id=user_id).only("id").first()