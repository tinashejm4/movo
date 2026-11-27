from django.urls import path
from rest_framework.parsers import FormParser, MultiPartParser

from .views.delivery_views import DeliveryViewSet
from .views.invoice_views import InvoiceViewSet
from .views.package_views import PackageViewSet
from .views.payments_views import PaymentViewSet
from .views.round_trip_views import RoundTripViewSet

package_create = PackageViewSet.as_view({"post": "create_package"})
package_detail = PackageViewSet.as_view({"get": "package_detail"})
package_list = PackageViewSet.as_view({"get": "list_packages"})
package_status = PackageViewSet.as_view({"get": "current_status"})
search_suburb = PackageViewSet.as_view({"get": "search_suburb"})
package_price = PackageViewSet.as_view({"post": "package_price"})
sender_receiver_login = PackageViewSet.as_view({"post": "sender_receiver_login"})
current_packages = PackageViewSet.as_view({"get": "current_packages"})
renew_package = PackageViewSet.as_view({"post": "renew_package"})
cancel_all_packages = PackageViewSet.as_view({"post": "cancel_all_packages"})

assign_pending_packages = DeliveryViewSet.as_view({"post": "assign_pending_packages"})
pickup_verify = DeliveryViewSet.as_view({"post": "pickup_verify"})
dropoff_verify = DeliveryViewSet.as_view({"post": "dropoff_verify"})
cancel_order = DeliveryViewSet.as_view({"post": "cancel_order"})
is_biker_assigned = DeliveryViewSet.as_view({"get": "is_biker_assigned"})

invoice_details = InvoiceViewSet.as_view({"get": "invoice_details"})

ecocash_payment = PaymentViewSet.as_view({"post": "ecocash_payment"})
ecocash_notify = PaymentViewSet.as_view({"post": "ecocash_notify"})
paynow_payment = PaymentViewSet.as_view({"post": "paynow_payment"})
paynow_notify = PaymentViewSet.as_view({"get": "paynow_notify"})
package_images = PackageViewSet.as_view(
    {"get": "get_package_images", "post": "post_package_image"},
    parser_classes=[MultiPartParser, FormParser],
)

round_trip_price = RoundTripViewSet.as_view({"post": "calculate_price"})
round_trip_collection = RoundTripViewSet.as_view({"post": "create", "get": "list"})
round_trip_detail = RoundTripViewSet.as_view({"get": "retrieve"})
round_trip_verify = RoundTripViewSet.as_view({"post": "verify_stop"})
round_trip_fail = RoundTripViewSet.as_view({"post": "fail_stop"})
round_trip_pod = RoundTripViewSet.as_view({"post": "upload_pod", "get": "download_pod"},
                                         parser_classes=[MultiPartParser, FormParser])
round_trip_cancel = RoundTripViewSet.as_view({"post": "cancel"})
round_trip_resolve = RoundTripViewSet.as_view({"post": "resolve"})
round_trip_renew = RoundTripViewSet.as_view({"post": "renew"})


urlpatterns = [
    path("round-trips/calculate-price/", round_trip_price, name="intracity_round_trip_price"),
    path("round-trips/", round_trip_collection, name="intracity_round_trip_collection"),
    path("round-trips/<int:pk>/", round_trip_detail, name="intracity_round_trip_detail"),
    path("round-trips/<int:pk>/cancel/", round_trip_cancel, name="intracity_round_trip_cancel"),
    path("round-trips/<int:pk>/renew/", round_trip_renew, name="intracity_round_trip_renew"),
    path("round-trips/<int:pk>/resolve/", round_trip_resolve, name="intracity_round_trip_resolve"),
    path("round-trips/<int:pk>/stops/<int:stop_id>/verify/", round_trip_verify, name="intracity_round_trip_verify"),
    path("round-trips/<int:pk>/stops/<int:stop_id>/fail/", round_trip_fail, name="intracity_round_trip_fail"),
    path("round-trips/<int:pk>/stops/<int:stop_id>/pod/", round_trip_pod, name="intracity_round_trip_pod"),
    path(
        "sender-receiver-login/",
        sender_receiver_login,
        name="intracity_sender_receiver_login",
    ),
    path("create-package/", package_create, name="intracity_create_package"),
    path("renew/", renew_package, name="intracity_renew_package"),
    path("invoice-details/", invoice_details, name="intracity_invoice_details"),
    path("package/", package_detail, name="intracity_package_detail"),
    path(
        "package-status/",
        package_status,
        name="intracity_package_status",
    ),
    path("calculate-price/", package_price, name="intracity_package_price"),
    path("packages/", package_list, name="intracity_package_list"),
    path(
        "package-images/<int:package_id>/",
        package_images,
        name="intracity_package_images",
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
    path("cancel-order/", cancel_order, name="intracity_cancel_order"),
    path(
        "cancel-all-packages/",
        cancel_all_packages,
        name="intracity_cancel_all_packages",
    ),
    path("search-suburbs/", search_suburb, name="intracity_search_suburb"),
    path(
        "ecocash-payment/",
        ecocash_payment,
        name="intracity_ecocash_payment",
    ),
    path(
        "paynow-payment/",
        paynow_payment,
        name="intracity_paynow_payment",
    ),
    path(
        "ecocash-notify/",
        ecocash_notify,
        name="intracity_ecocash_notify",
    ),
    path(
        "paynow-notify/",
        paynow_notify,
        name="intracity_paynow_notify",
    ),
    path(
        "package-price/",
        package_price,
        name="intracity_package_price",
    ),
    path(
        "current-packages/",
        current_packages,
        name="intracity_current_packages",
    ),
]
