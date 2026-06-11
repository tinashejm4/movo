from django.urls import path
from .views import PackageView, PrePackageView

urlpatterns = [
    path('create-pre-package/', PrePackageView.as_view(), name='create_pre_package'),
    path('create-package/', PackageView.as_view(), name='create_package'),
]
