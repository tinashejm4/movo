from django.urls import path

from .consumers import BikerOrderConsumer


websocket_urlpatterns = [
    path("ws/transporters/orders/", BikerOrderConsumer.as_asgi()),
    path("ws/transporters/orders", BikerOrderConsumer.as_asgi()),
]