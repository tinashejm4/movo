from django.db.models import OuterRef, Q, Subquery
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.users.permissions import IsStaff
from ..models import (
    FuelRecord,
    InsurancePolicy,
    LicensingRecord,
    MileageRecord,
    ServiceRecord,
)
from ..serializers import (
    FuelRecordSerializer,
    InsurancePolicySerializer,
    LicensingRecordSerializer,
    MileageRecordSerializer,
    ServiceRecordSerializer,
)


class RecordedByViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStaff]

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


class MileageRecordViewSet(RecordedByViewSet):
    serializer_class = MileageRecordSerializer

    def get_queryset(self):
        vehicle_id = self.request.query_params.get("vehicle_id")
        queryset = MileageRecord.objects.select_related("vehicle", "recorded_by")
        if vehicle_id is not None:
            if not vehicle_id.isdecimal() or int(vehicle_id) < 1:
                raise serializers.ValidationError({"vehicle_id": "Enter a positive vehicle ID."})
            queryset = queryset.filter(vehicle_id=int(vehicle_id))

        previous = MileageRecord.objects.filter(vehicle_id=OuterRef("vehicle_id")).filter(
            Q(recorded_at__lt=OuterRef("recorded_at"))
            | Q(recorded_at=OuterRef("recorded_at"), pk__lt=OuterRef("pk"))
        ).order_by("-recorded_at", "-pk")
        return queryset.annotate(
            previous_odometer_km=Subquery(previous.values("odometer_km")[:1]),
        )


class FuelRecordViewSet(RecordedByViewSet):
    serializer_class = FuelRecordSerializer

    def get_queryset(self):
        return FuelRecord.objects.select_related("vehicle", "driver__user", "recorded_by")


class ServiceRecordViewSet(RecordedByViewSet):
    serializer_class = ServiceRecordSerializer

    @extend_schema(parameters=[
        OpenApiParameter(
            name="vehicle_id",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Filter service records to a vehicle ID.",
        ),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        vehicle_id = self.request.query_params.get("vehicle_id")
        queryset = ServiceRecord.objects.select_related("vehicle", "recorded_by")
        if vehicle_id is not None:
            if not vehicle_id.isdecimal() or int(vehicle_id) < 1:
                raise serializers.ValidationError({"vehicle_id": "Enter a positive vehicle ID."})
            queryset = queryset.filter(vehicle_id=int(vehicle_id))
        return queryset


class InsurancePolicyViewSet(RecordedByViewSet):
    serializer_class = InsurancePolicySerializer

    @extend_schema(parameters=[
        OpenApiParameter(
            name="vehicle_id",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Filter insurance policies to a vehicle ID.",
        ),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        vehicle_id = self.request.query_params.get("vehicle_id")
        queryset = InsurancePolicy.objects.select_related("vehicle", "recorded_by")
        if vehicle_id is not None:
            if not vehicle_id.isdecimal() or int(vehicle_id) < 1:
                raise serializers.ValidationError({"vehicle_id": "Enter a positive vehicle ID."})
            queryset = queryset.filter(vehicle_id=int(vehicle_id))
        return queryset


class LicensingRecordViewSet(RecordedByViewSet):
    serializer_class = LicensingRecordSerializer

    @extend_schema(parameters=[
        OpenApiParameter(
            name="vehicle_id",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Filter licensing records to a vehicle ID.",
        ),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        vehicle_id = self.request.query_params.get("vehicle_id")
        queryset = LicensingRecord.objects.select_related("vehicle", "recorded_by")
        if vehicle_id is not None:
            if not vehicle_id.isdecimal() or int(vehicle_id) < 1:
                raise serializers.ValidationError({"vehicle_id": "Enter a positive vehicle ID."})
            queryset = queryset.filter(vehicle_id=int(vehicle_id))
        return queryset
