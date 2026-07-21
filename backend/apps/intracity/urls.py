from django.urls import path

from .views.delivery_views import DeliveryViewSet
from .views.invoice_views import InvoiceViewSet
from .views.package_views import PackageViewSet
from .views.payments_views import PaymentViewSet

package_create = PackageViewSet.as_view({"post": "create_package"})
package_detail = PackageViewSet.as_view({"get": "package_detail"})
package_list = PackageViewSet.as_view({"get": "list_packages"})
search_suburb = PackageViewSet.as_view({"post": "search_suburb"})
package_price = PackageViewSet.as_view({"post": "package_price"})

assign_pending_packages = DeliveryViewSet.as_view({"post": "assign_pending_packages"})
pickup_verify = DeliveryViewSet.as_view({"post": "pickup_verify"})
dropoff_verify = DeliveryViewSet.as_view({"post": "dropoff_verify"})
cancel_order = DeliveryViewSet.as_view({"post": "cancel_order"})
invoice_details = InvoiceViewSet.as_view({"get": "invoice_details"})
is_biker_assigned = DeliveryViewSet.as_view({"get": "is_biker_assigned"})

ecocash_payment = PaymentViewSet.as_view({"post": "ecocash_payment"})
ecocash_notify = PaymentViewSet.as_view({"post": "ecocash_notify"})


urlpatterns = [
    path("create-package/", 
         package_create, 
         name="intracity_create_package"
         ),
    path("invoice-details/", 
         invoice_details, 
         name="intracity_invoice_details"
         ),
    path("package/", 
         package_detail, 
         name="intracity_package_detail"
         ),
    path("calculate-price/", 
         package_price, 
         name="intracity_package_price"
         ),
    path("packages/", 
         package_list, 
         name="intracity_package_list"
         ),
    path(
        "is-biker-assigned/",
        is_biker_assigned,
        name="intracity_is_biker_assigned",
    ),
    path(
        "assign-pending-packages/",
        assign_pending_packages,
        name="intracity_assign_pending_packages",
    ),
    path(
        "pickup-verify/",
        pickup_verify,
        name="intracity_pickup_verify",
    ),
    path(
        "dropoff-verify/",
        dropoff_verify,
        name="intracity_dropoff_verify",
    ),
    path("cancel-order/", 
         cancel_order, 
         name="intracity_cancel_order"
         ),
    path("search-suburbs/", 
         search_suburb, 
         name="intracity_search_suburb"
         ),
    path(
        "ecocash-payment/",
        ecocash_payment,
        name="intracity_ecocash_payment",
    ),
    path(
        "ecocash-notify/",
        ecocash_notify,
        name="intracity_ecocash_notify",
    ),
    path(
        "package-price/",
        package_price,
        name="intracity_package_price",
    ),
]
