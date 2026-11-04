from django.urls import path
from backend.apps.vehicles.views.vehicle_views import VehicleViewSet

urlpatterns = [
    path("vehicles/", VehicleViewSet.as_view({"get": "list", "post": "create"})),
]
