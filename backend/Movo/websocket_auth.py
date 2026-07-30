"""JWT authentication for Channels WebSocket connections."""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _get_user(user_id):
    return get_user_model().objects.filter(id=user_id, is_active=True).first()


class JwtAuthMiddleware:
    """Populate ``scope['user']`` from an access token in ``?token=...``.

    Browsers cannot reliably set an Authorization header for a WebSocket
    handshake, so the mobile/web client supplies its normal access JWT as the
    ``token`` query parameter. Refresh tokens are deliberately rejected.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
        raw_token = query.get("token", [None])[0]
        user = AnonymousUser()

        if raw_token:
            try:
                token = AccessToken(raw_token)
                user_id = token.get("user_id")
                if user_id is not None:
                    resolved_user = await _get_user(user_id)
                    if resolved_user is not None:
                        user = resolved_user
            except (TokenError, ValueError, TypeError, UnicodeDecodeError):
                pass

        scope["user"] = user
        return await self.app(scope, receive, send)


def JwtAuthMiddlewareStack(app):
    return JwtAuthMiddleware(app)
