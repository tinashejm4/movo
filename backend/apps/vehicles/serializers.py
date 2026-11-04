from rest_framework import serializers

from backend.apps.vehicles.models import (
    Vehicle,
    VehicleAssignment,
    MileageRecord,
    FuelRecord,
    ServiceRecord,
    InsurancePolicy,
    LicensingRecord,
)


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = "__all__"


class VehicleAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleAssignment
        fields = "__all__"


class MileageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MileageRecord
        fields = "__all__"


class FuelRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelRecord
        fields = "__all__"


class ServiceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceRecord
        fields = "__all__"


class InsurancePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = InsurancePolicy
        fields = "__all__"


class LicensingRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicensingRecord
        fields = "__all__"
