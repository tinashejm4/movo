from django.urls import path

from .views import TransporterView, test_assign_pending_packages

pickup_package = TransporterView.as_view({"post": "pickup_package"})
dropoff_package = TransporterView.as_view({"post": "dropoff_package"})

urlpatterns = [
    path(
        "test-assign-pending-packages/",
        test_assign_pending_packages,
        name="test_assign_pending_packages",
    ),
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

