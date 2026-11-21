from django.db.models import OuterRef, Q, Subquery
import requests
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.permissions import IsStaff
from ..models import (
    FuelRecord,
    FuelPrice,
    InsurancePolicy,
    LicensingRecord,
    MileageRecord,
    ServiceRecord,
)
from ..serializers import (
    FuelRecordSerializer,
    FuelPriceSerializer,
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

    def get_permissions(self):
        if self.action in ("create",):
            return [IsAuthenticated()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        if IsStaff().has_permission(request, self):
            return super().create(request, *args, **kwargs)
        from apps.users.models import Biker
        from ..models import VehicleAssignment
        driver = Biker.objects.filter(user=request.user).first()
        if driver is None:
            raise PermissionDenied("Only staff or a driver can create fuel records.")
        assignment = VehicleAssignment.objects.filter(driver=driver, released_at__isnull=True).first()
        if assignment is None:
            raise PermissionDenied("You need an active vehicle assignment to record fuel.")
        data = request.data.copy()
        if str(data.get("vehicle", "")) != str(assignment.vehicle_id):
            raise PermissionDenied("Fuel can only be recorded for your currently assigned vehicle.")
        data["driver"] = driver.pk
        data.pop("account_id", None)
        request._full_data = data
        return super().create(request, *args, **kwargs)

    @extend_schema(parameters=[
        OpenApiParameter(
            name="vehicle_id",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Filter fuel records to a vehicle ID.",
        ),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        vehicle_id = self.request.query_params.get("vehicle_id")
        queryset = FuelRecord.objects.select_related("vehicle", "driver__user", "recorded_by", "expense")
        if vehicle_id is not None:
            if not vehicle_id.isdecimal() or int(vehicle_id) < 1:
                raise serializers.ValidationError({"vehicle_id": "Enter a positive vehicle ID."})
            queryset = queryset.filter(vehicle_id=int(vehicle_id))
        return queryset


class FuelPriceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FuelPriceSerializer
    permission_classes = [IsAuthenticated]
    queryset = FuelPrice.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        fuel_type = self.request.query_params.get("fuel_type")
        currency = self.request.query_params.get("currency")
        if fuel_type:
            queryset = queryset.filter(fuel_type=fuel_type)
        if currency:
            queryset = queryset.filter(currency=currency.upper())
        return queryset

    @action(detail=False, methods=["get"])
    def latest(self, request):
        latest_ids = []
        for fuel_type in FuelRecord.FuelType.values:
            for currency in FuelPrice.Currency.values:
                item = self.get_queryset().filter(fuel_type=fuel_type, currency=currency).order_by(
                    "-effective_date", "-fetched_at", "-pk"
                ).first()
                if item:
                    latest_ids.append(item.pk)
        return Response(self.get_serializer(FuelPrice.objects.filter(pk__in=latest_ids), many=True).data)

    @action(detail=False, methods=["post"])
    def refresh(self, request):
        if not IsStaff().has_permission(request, self):
            raise PermissionDenied("Only staff can refresh fuel prices.")
        from ..fuel_prices import refresh_fuel_prices
        try:
            created = refresh_fuel_prices()
        except (ValueError, requests.RequestException) as error:
            return Response({"detail": str(error)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"created": self.get_serializer(created, many=True).data}, status=status.HTTP_200_OK)


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
