from django.urls import path

from .views import AssignPendingPackagesView, CancelOrderView, DropoffVerificationView, EcocashPaymentView, LocalPackageView, PickupVerificationView, UserPackageListView

urlpatterns = [
    path("create-package/", LocalPackageView.as_view(), name="intracity_create_package"),
    path("package/", LocalPackageView.as_view(), name="intracity_package_detail"),
    path("packages/", UserPackageListView.as_view(), name="intracity_package_list"),
    path("assign-pending-packages/", AssignPendingPackagesView.as_view(), name="intracity_assign_pending_packages"),
    path("pickup-verify/", PickupVerificationView.as_view(), name="intracity_pickup_verify"),
    path("dropoff-verify/", DropoffVerificationView.as_view(), name="intracity_dropoff_verify"),
    path("cancel-order/", CancelOrderView.as_view(), name="intracity_cancel_order"),
    path("ecocash-payment/", EcocashPaymentView.as_view(), name="intracity_ecocash_payment"),
]