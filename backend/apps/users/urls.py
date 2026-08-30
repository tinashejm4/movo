from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    CustomerProfileView,
    OTPCreateView,
    StaffProfileView,
    StaffLoginView,
    LogoutView,
    TokenRefreshView,
    CustomerRegisterLoginView,
    ImportAreasView,
    CityViewSet,SuburbViewSet,
    DriverLoginView,
    DriverProfileView,
)

router = DefaultRouter()
router.register(r"cities", CityViewSet, basename="city")
router.register(r"suburbs", SuburbViewSet, basename="suburb")

urlpatterns = [
    path("staff/login/", StaffLoginView.as_view(), name="staff_token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="staff_token_refresh"),
    path("logout/", LogoutView.as_view(), name="token_logout"),
    path("staff/profile/", StaffProfileView.as_view(), name="staff_profile"),
    path(
        "customer/profile/",
        CustomerProfileView.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="customer_profile",
    ),
    path(
        "register-login/",
        CustomerRegisterLoginView.as_view(),
        name="customer_register_login",
    ),
    path("otp/", OTPCreateView.as_view(), name="customer_otp"),
    path("driver/login/", DriverLoginView.as_view(), name="driver_token_obtain_pair"),
    path("driver/refresh/", TokenRefreshView.as_view(), name="driver_token_refresh"),
    path("driver/logout/", LogoutView.as_view(), name="driver_token_logout"),
    path("driver/profile/", DriverProfileView.as_view(), name="driver_profile"),
    path("suburbs/import-areas/", ImportAreasView.as_view(), name="import_areas"),
] + router.urls
