"""JWT authentication for Channels WebSocket connections."""

import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken


logger = logging.getLogger(__name__)


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
        scope["auth_error"] = None

        if not raw_token:
            scope["auth_error"] = "Missing 'token' query parameter."
        else:
            try:
                token = AccessToken(raw_token)
                user_id = token.get("user_id")
                if user_id is None:
                    scope["auth_error"] = "Token has no user_id claim."
                else:
                    resolved_user = await _get_user(user_id)
                    if resolved_user is None:
                        scope["auth_error"] = "Token user not found or inactive."
                    else:
                        user = resolved_user
            except Exception as exc:
                # Catch-all: any malformed/expired token or unexpected decode error
                # must not raise here, or Daphne aborts the handshake as code 1006.
                logger.warning("WebSocket JWT auth failed: %s: %s", exc.__class__.__name__, exc)
                scope["auth_error"] = f"{exc.__class__.__name__}: {exc}"

        scope["user"] = user
        return await self.app(scope, receive, send)


def JwtAuthMiddlewareStack(app):
    return JwtAuthMiddleware(app)
