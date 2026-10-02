from django.urls import path

from apps.adminportal.views.surbubs_views import (
    SuburbsImportView, 
    SuburbView, 
    CityView, 
    SuburbAliasiew,)

from apps.adminportal.views.live_dashboard import (
    BikerMetricsView, 
    MainMetricsView, 
    PackageListView,
    PackageDetailsView
)

from apps.adminportal.views.bikers_views import (
    BikersListView,
    BikerDetailView,
    BikerStatisticsView,
    BikerCreateView
)

from apps.adminportal.views.customer_views import (
    CustomersListView,
    CustomersDetailView,        
    CustomersMetricsView
)

from apps.adminportal.views.accounts import (
    AccountsListView,
    AccountTransactionsView,
    CreateFundsTransferView,
    ReceiptImageView,
    ExpenseReversalView,
    ChargeReversalView,
    FundsTransferReversalView,
    CreateExpenseView,
    ExpenseClassView,
    CreateChargeView
)

from .views.delivery_order_views import DeliveryPageView

delivery_metrics = DeliveryPageView.as_view({"get": "delivery_metrics"})
delivery_order_list = DeliveryPageView.as_view({"get": "delivery_order_list"})
today_delivery_metrics = DeliveryPageView.as_view({"get": "today_delivery_metrics"})

urlpatterns = [
    path("delivery_metrics/", delivery_metrics, name="admin_delivery_metrics"),
    path("deliveries/", delivery_order_list, name="admin_delivery_order_list"),
    path("deliveries/today/", today_delivery_metrics, name="admin_today_delivery_metrics"),
    path("cities/", CityView.as_view(), name="city_view"),
    path("suburbs/import-areas/", SuburbsImportView.as_view(), name="import_suburbs"),
    path("suburbs/<int:city_id>/", SuburbView.as_view(), name="suburb_view"),
    path("suburbs/alias/", SuburbAliasiew.as_view(), name="suburb_alias_view"),
    path("bikers/", BikersListView.as_view(), name="biker_list_view"),
    path("bikers/<int:biker_user_id>/", BikerDetailView.as_view(), name="biker_view"),
    path("bikers/create/", BikerCreateView.as_view(), name="biker_create_view"),
    path("bikers/statistics/", BikerStatisticsView.as_view(), name="biker_statistics_view"),
    path("bikers-metrics/", BikerMetricsView.as_view(), name="biker_live_metrics_view"),
    path("main-metrics/", MainMetricsView.as_view(), name="main_live_metrics_view"),
    path("packages-list/", PackageListView.as_view(), name="packages_live_metrics_view"),
    path("packages-details/", PackageDetailsView.as_view(), name="packages_details_view"),
    path("customers-metrics/", CustomersMetricsView.as_view(), name="customers_metrics_view"),
    path("customers/", CustomersListView.as_view(), name="customers_list_view"),
    path("customers/<int:pk>/", CustomersDetailView.as_view(), name="customers_detail_view"),
    path("accounts/", AccountsListView.as_view(), name="accounts_list_view"),
    path("accounts/expense-classes/", ExpenseClassView.as_view(), name="expense_class_view"),
    path("accounts/create-expense/", CreateExpenseView.as_view(), name="create_expense_view"),
    path("accounts/create-charge/", CreateChargeView.as_view(), name="create_charge_view"),
    path("accounts/create-funds-transfer/", CreateFundsTransferView.as_view(), name="create_funds_transfer_view"),
    path("accounts/<int:account_id>/transactions/", AccountTransactionsView.as_view(), name="account_transactions_view"),
    path("accounts/<int:account_id>/receipt-image/", ReceiptImageView.as_view(), name="receipt_image_view"),
    path("accounts/<int:account_id>/expense-reversal/", ExpenseReversalView.as_view(), name="expense_reversal_view"),
    path("accounts/<int:account_id>/charge-reversal/", ChargeReversalView.as_view(), name="charge_reversal_view"),
    path("accounts/<int:account_id>/funds-transfer-reversal/", FundsTransferReversalView.as_view(), name="funds_transfer_reversal_view"),
]