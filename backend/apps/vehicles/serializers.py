from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import (
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
    def validate(self, attrs):
        assignment = self.instance or VehicleAssignment()
        for field, value in attrs.items():
            setattr(assignment, field, value)
        if bool(assignment.released_at) != bool(assignment.release_mileage_record_id):
            raise serializers.ValidationError(
                "released_at and release_mileage_record must be provided together."
            )
        try:
            assignment.clean()
        except DjangoValidationError as error:
            detail = error.message_dict if hasattr(error, "message_dict") else error.messages
            raise serializers.ValidationError(detail) from error
        return attrs

    class Meta:
        model = VehicleAssignment
        fields = "__all__"
        read_only_fields = ("assigned_by", "released_by", "created_at")


class MileageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MileageRecord
        fields = "__all__"
        read_only_fields = ("recorded_by", "created_at")


class FuelRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelRecord
        fields = "__all__"
        read_only_fields = ("recorded_by", "created_at")


class ServiceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceRecord
        fields = "__all__"
        read_only_fields = ("recorded_by", "created_at")


class InsurancePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = InsurancePolicy
        fields = "__all__"
        read_only_fields = ("recorded_by", "created_at")


class LicensingRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicensingRecord
        fields = "__all__"
        read_only_fields = ("recorded_by", "created_at")
