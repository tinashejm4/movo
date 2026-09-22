from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import City, Customer

from ..consumers import PackageAssignmentConsumer
from ..models import Package, PackageStatus
from ..routing import websocket_urlpatterns
from ..services.current_package_updates import (
    _publish_current_packages_changed,
    current_packages_group_name,
    notify_current_packages_changed,
)


IN_MEMORY_CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


class CurrentPackageUpdatePublisherTests(TestCase):
    def setUp(self):
        sender_user = User.objects.create_user(username="updates-sender")
        receiver_user = User.objects.create_user(username="updates-receiver")
        self.unrelated_user = User.objects.create_user(username="updates-unrelated")
        self.sender = Customer.objects.create(user=sender_user)
        self.receiver = Customer.objects.create(user=receiver_user)
        self.package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=City.objects.create(name="Updates City"),
            pickup_address="Pickup",
            dropoff_address="Dropoff",
            sender_code="111111",
            receiver_code="222222",
        )

    def test_notification_is_published_to_sender_and_receiver_after_commit(self):
        with patch(
            "apps.intracity.services.current_package_updates."
            "_publish_current_packages_changed"
        ) as publish:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                notify_current_packages_changed(
                    package=self.package,
                    reason="assigned",
                )

        self.assertEqual(len(callbacks), 1)
        publish.assert_called_once()
        call_kwargs = publish.call_args.kwargs
        self.assertEqual(call_kwargs["package_id"], self.package.id)
        self.assertEqual(call_kwargs["reason"], "assigned")
        self.assertCountEqual(
            call_kwargs["recipient_user_ids"],
            [self.sender.user_id, self.receiver.user_id],
        )
        self.assertNotIn(
            self.unrelated_user.id,
            call_kwargs["recipient_user_ids"],
        )

    def test_notification_is_discarded_when_transaction_rolls_back(self):
        with patch(
            "apps.intracity.services.current_package_updates."
            "_publish_current_packages_changed"
        ) as publish:
            try:
                from django.db import transaction

                with transaction.atomic():
                    notify_current_packages_changed(
                        package=self.package,
                        reason="cancelled",
                    )
                    raise RuntimeError("roll back")
            except RuntimeError:
                pass

        publish.assert_not_called()

    def test_publisher_sends_only_minimal_payload_to_customer_groups(self):
        sent = []

        class RecordingChannelLayer:
            async def group_send(self, group, event):
                sent.append((group, event))

        with patch(
            "apps.intracity.services.current_package_updates.get_channel_layer",
            return_value=RecordingChannelLayer(),
        ):
            _publish_current_packages_changed(
                package_id=self.package.id,
                recipient_user_ids=(self.sender.user_id, self.receiver.user_id),
                reason="delivered",
            )

        self.assertCountEqual(
            [group for group, _event in sent],
            [
                current_packages_group_name(self.sender.user_id),
                current_packages_group_name(self.receiver.user_id),
            ],
        )
        self.assertTrue(
            all(
                event
                == {
                    "type": "current_packages.changed",
                    "payload": {
                        "package_id": self.package.id,
                        "reason": "delivered",
                    },
                }
                for _group, event in sent
            )
        )


class CustomerCancellationUpdateTests(APITestCase):
    def setUp(self):
        self.sender_user = User.objects.create_user(username="cancel-sender")
        sender = Customer.objects.create(user=self.sender_user)
        receiver = Customer.objects.create(
            user=User.objects.create_user(username="cancel-receiver")
        )
        self.package = Package.objects.create(
            sender=sender,
            receiver=receiver,
            city=City.objects.create(name="Cancellation City"),
            pickup_address="Pickup",
            dropoff_address="Dropoff",
            sender_code="111111",
            receiver_code="222222",
        )
        PackageStatus.objects.create(package=self.package, status="Pending")
        self.client.force_authenticate(user=self.sender_user)

    @patch(
        "apps.intracity.views.delivery_views.notify_current_packages_changed"
    )
    def test_customer_cancellation_notifies_current_packages(self, notify):
        response = self.client.post(
            reverse("intracity_cancel_order"),
            {"package_id": self.package.id, "reason": "No longer required"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notify.assert_called_once_with(package=self.package, reason="cancelled")


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYERS)
class CurrentPackagesConsumerTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.sender_user = User.objects.create_user(username="socket-sender")
        receiver_user = User.objects.create_user(username="socket-receiver")
        self.sender = Customer.objects.create(user=self.sender_user)
        receiver = Customer.objects.create(user=receiver_user)
        self.package = Package.objects.create(
            sender=self.sender,
            receiver=receiver,
            city=City.objects.create(name="Socket City"),
            pickup_address="Pickup",
            dropoff_address="Dropoff",
            sender_code="111111",
            receiver_code="222222",
        )

    def test_global_socket_rejects_unauthenticated_user(self):
        accepted, close_code = async_to_sync(self._connect_and_close)(
            AnonymousUser(),
            "/ws/intracity/assignments/",
        )

        self.assertFalse(accepted)
        self.assertEqual(close_code, 4401)

    def test_global_socket_receives_current_packages_refresh_event(self):
        message = async_to_sync(self._receive_current_packages_event)()

        self.assertEqual(
            message,
            {
                "event": "current_packages_changed",
                "data": {"package_id": self.package.id, "reason": "picked_up"},
            },
        )

    def test_package_specific_assignment_socket_is_unchanged(self):
        message = async_to_sync(self._receive_package_assignment_event)()

        self.assertEqual(message["event"], "package_assigned")
        self.assertEqual(message["data"]["package_id"], self.package.id)

    async def _connect_and_close(self, user, path):
        communicator = WebsocketCommunicator(URLRouter(websocket_urlpatterns), path)
        communicator.scope["user"] = user
        accepted, close_code = await communicator.connect()
        if accepted:
            await communicator.disconnect()
        return accepted, close_code

    async def _receive_current_packages_event(self):
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            "/ws/intracity/assignments/",
        )
        communicator.scope["user"] = self.sender_user
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)
        connected = await communicator.receive_json_from()
        self.assertEqual(
            connected["data"]["group"],
            current_packages_group_name(self.sender_user.id),
        )

        await get_channel_layer().group_send(
            current_packages_group_name(self.sender_user.id),
            {
                "type": "current_packages.changed",
                "payload": {
                    "package_id": self.package.id,
                    "reason": "picked_up",
                },
            },
        )
        message = await communicator.receive_json_from()
        await communicator.disconnect()
        return message

    async def _receive_package_assignment_event(self):
        communicator = WebsocketCommunicator(
            PackageAssignmentConsumer.as_asgi(),
            f"/ws/intracity/assignments/{self.package.id}/",
        )
        communicator.scope["user"] = self.sender_user
        communicator.scope["url_route"] = {
            "kwargs": {"package_id": self.package.id}
        }
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)
        await communicator.receive_json_from()

        await get_channel_layer().group_send(
            f"package_{self.package.id}",
            {
                "type": "package.assigned",
                "payload": {"package_id": self.package.id, "biker_id": 7},
            },
        )
        message = await communicator.receive_json_from()
        await communicator.disconnect()
        return message
