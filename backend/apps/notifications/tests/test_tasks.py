import os
from types import SimpleNamespace
from unittest.mock import patch, sentinel

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from apps.notifications.models import DeviceToken, Notification, NotificationOutbox
from apps.notifications.tasks import _firebase_app, deliver_notification_outbox


class FirebaseAppTests(SimpleTestCase):
    @patch.dict(
        os.environ,
        {"FIREBASE_CREDENTIALS_PATH": "", "FIREBASE_CREDENTIALS_JSON": ""},
    )
    @patch("apps.notifications.tasks.initialize_app")
    @patch("apps.notifications.tasks.credentials.ApplicationDefault")
    @patch("firebase_admin.get_app", side_effect=ValueError)
    def test_uses_application_default_credentials_without_explicit_secret(
        self, get_app, application_default, initialize_app
    ):
        application_default.return_value = sentinel.credential

        _firebase_app()

        initialize_app.assert_called_once_with(sentinel.credential)


class ShiftNotificationDeliveryTests(TestCase):
    @patch("apps.notifications.tasks.messaging.send_each_for_multicast")
    @patch("apps.notifications.tasks._firebase_app")
    def test_shift_alert_only_uses_biker_device_tokens(self, firebase_app, send):
        user = User.objects.create_user(username="shift-push-driver")
        DeviceToken.objects.create(
            user=user,
            token="biker-token",
            app=DeviceToken.App.BIKER,
            platform=DeviceToken.Platform.ANDROID,
        )
        DeviceToken.objects.create(
            user=user,
            token="customer-token",
            app=DeviceToken.App.CUSTOMER,
            platform=DeviceToken.Platform.ANDROID,
        )
        notification = Notification.objects.create(
            user=user,
            event_type="shift.closing_soon",
            title="Shift ending soon",
            body="Your shift closes at 17:00.",
            payload={"type": "shift.closing_soon"},
        )
        outbox = NotificationOutbox.objects.create(
            notification=notification,
            idempotency_key="shift.closing_soon:test",
        )
        send.return_value = SimpleNamespace(
            responses=[SimpleNamespace(success=True, exception=None)]
        )

        deliver_notification_outbox.run(outbox.pk)

        firebase_app.assert_called_once_with()
        message = send.call_args.args[0]
        self.assertEqual(message.tokens, ["biker-token"])
        outbox.refresh_from_db()
        self.assertEqual(outbox.status, NotificationOutbox.Status.DELIVERED)
