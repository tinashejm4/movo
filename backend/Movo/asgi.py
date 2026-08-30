"""
ASGI config for Movo project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Movo.settings")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter

from apps.intracity.routing import websocket_urlpatterns as intracity_websocket_urlpatterns
from apps.transporters.routing import websocket_urlpatterns as transporter_websocket_urlpatterns
from Movo.websocket_auth import JwtAuthMiddlewareStack


websocket_urlpatterns = (
    intracity_websocket_urlpatterns + transporter_websocket_urlpatterns
)

if settings.DEBUG:
    django_asgi_app = ASGIStaticFilesHandler(django_asgi_app)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)

