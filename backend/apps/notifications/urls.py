from django.urls import path

from .views import DeviceTokenView


urlpatterns = [path("devices/", DeviceTokenView.as_view(), name="notification_devices")]
