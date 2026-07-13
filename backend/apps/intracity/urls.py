from django.urls import path

from .views.delivery_views import DeliveryViewSet
from .views.invoice_views import InvoiceViewSet
from .views.package_views import PackageViewSet
from .views.payments_views import PaymentViewSet

package_create = PackageViewSet.as_view({"post": "create_package"})
package_detail = PackageViewSet.as_view({"get": "package_detail"})
package_list = PackageViewSet.as_view({"get": "list_packages"})
assign_pending_packages = DeliveryViewSet.as_view({"post": "assign_pending_packages"})
pickup_verify = DeliveryViewSet.as_view({"post": "pickup_verify"})
dropoff_verify = DeliveryViewSet.as_view({"post": "dropoff_verify"})
cancel_order = DeliveryViewSet.as_view({"post": "cancel_order"})
invoice_amount = InvoiceViewSet.as_view({"get": "amount", "post": "quote"})
ecocash_payment = PaymentViewSet.as_view({"post": "ecocash_payment"})
package_price = PaymentViewSet.as_view({"get": "calculate_package_price"})

urlpatterns = [
    path("create-package/", 
         package_create, 
         name="intracity_create_package"
         ),
    path("amount/", 
         invoice_amount, 
         name="intracity_invoice_amount"
         ),
    path("package/", 
         package_detail, 
         name="intracity_package_detail"
         ),
    path("packages/", 
         package_list, 
         name="intracity_package_list"
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
    path(
        "ecocash-payment/",
        ecocash_payment,
        name="intracity_ecocash_payment",
    ),
    path(
        "package-price/",
        package_price,
        name="intracity_package_price",
    ),
]
