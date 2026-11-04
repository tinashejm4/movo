from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from backend.apps.vehicles.models import (
    Vehicle,
)
from backend.apps.vehicles.serializers import (
    VehicleSerializer,
)


class VehicleViewSet(viewsets.ModelViewSet):
    
    serializer_class = VehicleSerializer

    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Vehicle.objects.all()
    
    def perform_create(self, serializer):
        serializer.save()