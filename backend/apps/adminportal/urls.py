from django.urls import path

from .views import DeliveryPageView


delivery_metrics = DeliveryPageView.as_view({"get": "delivery_metrics"})
delivery_order_list = DeliveryPageView.as_view({"get": "delivery_order_list"})
today_delivery_metrics = DeliveryPageView.as_view({"get": "today_delivery_metrics"})


urlpatterns = [
    path("delivery_metrics/", delivery_metrics, name="admin_delivery_metrics"),
    path("deliveries/", delivery_order_list, name="admin_delivery_order_list"),
    path("deliveries/today/", today_delivery_metrics, name="admin_today_delivery_metrics"),
]