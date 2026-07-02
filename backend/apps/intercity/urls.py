from django.urls import path
from .views import PackageView, PrePackageView, ReceivePackageView, RequestPaymentView, CheckPaymentStatusView, DispatchPackageView, BatchListView, BatchDetailView

urlpatterns = [
    path('create-pre-package/', PrePackageView.as_view(), name='create_pre_package'),
    path('create-package/', PackageView.as_view(), name='create_package'),
    path('receive-package/', ReceivePackageView.as_view(), name='receive_package'),
    path('dispatch-package/', DispatchPackageView.as_view(), name='dispatch_package'),
    path('request-payment/', RequestPaymentView.as_view(), name='request_payment'),
    path('check-payment/', CheckPaymentStatusView.as_view(), name='check_payment'),
    path('batches/', BatchListView.as_view(), name='batch_list'),
    path('batches/<int:batch_id>/', BatchDetailView.as_view(), name='batch_detail'),
]
