from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from ..models import (
    Vehicle,
)
from ..serializers import (
    VehicleSerializer,
)


class VehicleViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter]
    search_fields = ["registration_number"]

    def get_queryset(self):
        return Vehicle.objects.all()

    def perform_create(self, serializer):
        serializer.save()
