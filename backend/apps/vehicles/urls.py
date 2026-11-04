from rest_framework.routers import DefaultRouter

from .views.assignment_views import VehicleAssignmentViewSet
from .views.record_views import (
    FuelRecordViewSet,
    InsurancePolicyViewSet,
    LicensingRecordViewSet,
    MileageRecordViewSet,
    ServiceRecordViewSet,
)
from .views.vehicle_views import VehicleViewSet


router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("assignments", VehicleAssignmentViewSet, basename="vehicle-assignment")
router.register("mileage-records", MileageRecordViewSet, basename="mileage-record")
router.register("fuel-records", FuelRecordViewSet, basename="fuel-record")
router.register("service-records", ServiceRecordViewSet, basename="service-record")
router.register("insurance-policies", InsurancePolicyViewSet, basename="insurance-policy")
router.register("licensing-records", LicensingRecordViewSet, basename="licensing-record")

urlpatterns = router.urls
