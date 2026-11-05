from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.users.models import Biker

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
    start_mileage_km = serializers.IntegerField(write_only=True, min_value=0, required=False)

    def validate(self, attrs):
        mileage_km = attrs.get("start_mileage_km")
        if self.instance is None:
            has_mileage_record = attrs.get("start_mileage_record") is not None
            if mileage_km is None and not has_mileage_record:
                raise serializers.ValidationError({
                    "start_mileage_km": "Provide a starting odometer reading or an existing mileage record."
                })
            if mileage_km is not None and has_mileage_record:
                raise serializers.ValidationError({
                    "start_mileage_km": "Provide an odometer reading or a mileage record, not both."
                })

        assignment = self.instance or VehicleAssignment()
        for field, value in attrs.items():
            if field == "start_mileage_km":
                continue
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

    def create(self, validated_data):
        mileage_km = validated_data.pop("start_mileage_km", None)
        with transaction.atomic():
            driver_id = validated_data["driver"].pk
            driver = Biker.objects.select_for_update().get(pk=driver_id)
            if VehicleAssignment.objects.filter(driver=driver, released_at__isnull=True).exists():
                raise serializers.ValidationError({
                    "driver": "This driver already has an active vehicle assignment."
                })
            validated_data["driver"] = driver

            if mileage_km is not None:
                assignment_time = validated_data["assigned_at"]
                mileage = MileageRecord.objects.create(
                    vehicle=validated_data["vehicle"],
                    odometer_km=mileage_km,
                    recorded_at=assignment_time,
                    source=MileageRecord.Source.ASSIGNMENT_START,
                    recorded_by=validated_data.get("assigned_by"),
                )
                validated_data["start_mileage_record"] = mileage

            assignment = VehicleAssignment(**validated_data)
            try:
                assignment.clean()
            except DjangoValidationError as error:
                detail = error.message_dict if hasattr(error, "message_dict") else error.messages
                raise serializers.ValidationError(detail) from error
            assignment.save()
            return assignment

    class Meta:
        model = VehicleAssignment
        fields = "__all__"
        read_only_fields = ("assigned_by", "released_by", "created_at")
        extra_kwargs = {"start_mileage_record": {"required": False}}


class ReassignVehicleInputSerializer(serializers.Serializer):
    driver = serializers.PrimaryKeyRelatedField(queryset=Biker.objects.all())
    handover_at = serializers.DateTimeField()
    release_mileage_km = serializers.IntegerField(min_value=0)
    start_mileage_km = serializers.IntegerField(min_value=0)
    handover_notes = serializers.CharField(required=False, allow_blank=True)


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
