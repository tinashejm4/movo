from django.urls import path
from .views import (CustomerProfileView, OTPCreateView, StaffProfileView, StaffLoginView, 
                    TokenRefreshView, CustomerRegisterLoginView)


urlpatterns = [
    path('staff/login/', StaffLoginView.as_view(), name='staff_token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='staff_token_refresh'),
    path('staff/profile/', StaffProfileView.as_view(), name='staff_profile'),
    path('customer/profile/', CustomerProfileView.as_view({'get': 'retrieve', 'patch': 'partial_update'}), name='customer_profile'),

    path('register-login/', CustomerRegisterLoginView.as_view(), name='customer_register_login'),
    path('otp/', OTPCreateView.as_view(), name='customer_otp'),
]  
