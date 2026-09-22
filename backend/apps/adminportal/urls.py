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

]