from django.urls import path
from .views import CreatePrePackage


urlpatterns = [
    path('create-pre-package/', CreatePrePackage.as_view(), name='create_pre_package'),
]
