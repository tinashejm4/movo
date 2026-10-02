import os
from unittest.mock import patch, sentinel

from django.test import SimpleTestCase

from apps.notifications.tasks import _firebase_app


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
