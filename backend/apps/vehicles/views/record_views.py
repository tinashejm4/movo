from rest_framework import viewsets
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
        return MileageRecord.objects.select_related("vehicle", "recorded_by")


class FuelRecordViewSet(RecordedByViewSet):
    serializer_class = FuelRecordSerializer

    def get_queryset(self):
        return FuelRecord.objects.select_related("vehicle", "driver__user", "recorded_by")


class ServiceRecordViewSet(RecordedByViewSet):
    serializer_class = ServiceRecordSerializer

    def get_queryset(self):
        return ServiceRecord.objects.select_related("vehicle", "recorded_by")


class InsurancePolicyViewSet(RecordedByViewSet):
    serializer_class = InsurancePolicySerializer

    def get_queryset(self):
        return InsurancePolicy.objects.select_related("vehicle", "recorded_by")


class LicensingRecordViewSet(RecordedByViewSet):
    serializer_class = LicensingRecordSerializer

    def get_queryset(self):
        return LicensingRecord.objects.select_related("vehicle", "recorded_by")
