from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Prefetch
from apps.bookkeeping.models import Asset
from ..models import (
    Vehicle,
    VehicleAssignment,
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
        active_assignments = VehicleAssignment.objects.filter(
            released_at__isnull=True,
        ).only("vehicle_id", "driver_id")
        return Vehicle.objects.prefetch_related(
            Prefetch(
                "assignments",
                queryset=active_assignments,
                to_attr="active_assignments",
            )
        )

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=["get"], url_path="available-assets")
    def available_assets(self, request):
        assets = Asset.objects.filter(asset_type="vehicle", fleet_vehicles__isnull=True).order_by("name", "id")
        return Response(list(assets.values("id", "name", "unique_identifier")))
