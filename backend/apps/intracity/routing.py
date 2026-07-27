from django.urls import path

from .consumers import PackageAssignmentConsumer


websocket_urlpatterns = [
    path("ws/intracity/assignments/", PackageAssignmentConsumer.as_asgi()),
    path("ws/intracity/assignments", PackageAssignmentConsumer.as_asgi()),
    path(
        "ws/intracity/assignments/<int:package_id>/",
        PackageAssignmentConsumer.as_asgi(),
    ),
    path(
        "ws/intracity/assignments/<int:package_id>",
        PackageAssignmentConsumer.as_asgi(),
    ),
]
