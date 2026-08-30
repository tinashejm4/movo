import asyncio
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import Q

from .models import Package


logger = logging.getLogger(__name__)


class PackageAssignmentConsumer(AsyncWebsocketConsumer):
    subscribed_to_groups = False

    async def connect(self):
        try:
            await self._connect()
        except Exception as exc:
            logger.exception("WebSocket connect failed unexpectedly")
            try:
                await self.close(
                    code=4500,
                    reason=f"{exc.__class__.__name__}: {exc}",
                )
            except Exception:
                pass

    async def _connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            reason = self.scope.get("auth_error") or "Authentication required."
            await self.close(code=4401, reason=reason)
            return

        self.global_group = "package_assignments"
        self.package_id = self.scope["url_route"]["kwargs"].get("package_id")
        if self.package_id is not None and not await self._can_access_package(
            self.package_id
        ):
            await self.close(
                code=4403,
                reason="Not authorized to access this package.",
            )
            return

        self.group_name = (
            f"package_{self.package_id}"
            if self.package_id is not None
            else self.global_group
        )

        # Accept first so a slow/unreachable channel layer never blocks the handshake.
        await self.accept()

        self.subscribed_to_groups = False
        try:
            await asyncio.wait_for(
                self.channel_layer.group_add(self.group_name, self.channel_name),
                timeout=5,
            )
            self.subscribed_to_groups = True
        except Exception as exc:
            logger.warning("WebSocket group subscribe failed: %s", exc)

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
        logger.info(
            "WebSocket disconnect: group=%s close_code=%s",
            getattr(self, "group_name", None),
            close_code,
        )
        if not self.subscribed_to_groups:
            return

        try:
            await asyncio.wait_for(
                self.channel_layer.group_discard(self.group_name, self.channel_name),
                timeout=5,
            )
        except Exception as exc:
            logger.warning("WebSocket group unsubscribe failed: %s", exc)

    async def package_assigned(self, event):
        payload = event.get("payload", {})
        package_id = payload.get("package_id")
        if not package_id or not await self._can_access_package(package_id):
            return

        logger.info(
            "WebSocket event delivered: package_assigned package_id=%s",
            package_id,
        )
        await self.send(
            text_data=json.dumps(
                {
                    "event": "package_assigned",
                    "data": payload,
                },
                default=str,
            )
        )

    @database_sync_to_async
    def _can_access_package(self, package_id):
        """Allow only a package's sender, receiver, or assigned biker."""
        return Package.objects.filter(id=package_id).filter(
            Q(sender__user_id=self.user.id)
            | Q(receiver__user_id=self.user.id)
            | Q(biker__user_id=self.user.id)
        ).exists()
