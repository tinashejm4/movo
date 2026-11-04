from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from ..models import (
    Vehicle,
)
from ..serializers import (
    VehicleSerializer,
)
from apps.users.permissions import IsStaff


class VehicleViewSet(viewsets.ModelViewSet):
    
    serializer_class = VehicleSerializer

    permission_classes = [IsAuthenticated, IsStaff]
    
    def get_queryset(self):
        return Vehicle.objects.all()
    
    def perform_create(self, serializer):
        serializer.save()
