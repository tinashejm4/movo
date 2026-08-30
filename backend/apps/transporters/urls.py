from django.urls import path

from .views import TransporterView, test_assign_pending_packages

pickup_package = TransporterView.as_view({"post": "pickup_package"})
dropoff_package = TransporterView.as_view({"post": "dropoff_package"})
activate_deactivate = TransporterView.as_view({"post": "activate_deactivate"})
cancel_package = TransporterView.as_view({"post": "cancel_package"})
get_sales = TransporterView.as_view({"get": "daily_sales"})
get_orders = TransporterView.as_view({"get": "order_summary"})

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
    path(
        "activate-deactivate/",
        activate_deactivate,
        name="activate_deactivate"
    ),
    path(
        "cancel-package/",
        cancel_package,
        name="cancel_package"
    ),
    path(
        "get-sales/",
        get_sales,
        name="get_sales"
    ),
    path(
        "get-orders/",
        get_orders,
        name="get_orders"
    ),
]

