from django.urls import path

from .views import TransporterView

pickup_package = TransporterView.as_view({"post": "pickup_package"})
dropoff_package = TransporterView.as_view({"post": "dropoff_package"})

urlpatterns = [
    path(
        "pickup-package/",
        pickup_package,
        name="pickup_package"
        ),
    path(
        "dropoff-package/",
        dropoff_package,
        name="dropoff_package"
        ),

]

