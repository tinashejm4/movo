from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.bookkeeping.models import Asset
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
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.filter(asset_type="vehicle"), required=False)

    class Meta:
        model = Vehicle
        fields = "__all__"

    def validate(self, attrs):
        if self.instance is None and "asset" not in attrs:
            raise serializers.ValidationError({"asset": "Select an existing vehicle asset."})
        if self.instance is not None and "asset" in attrs and attrs["asset"].pk != self.instance.asset_id:
            raise serializers.ValidationError({"asset": "The linked asset cannot be changed here."})
        return attrs

    def create(self, validated_data):
        asset = validated_data["asset"]
        try:
            with transaction.atomic():
                asset = Asset.objects.select_for_update().get(pk=asset.pk, asset_type="vehicle")
                if Vehicle.objects.filter(asset=asset).exists():
                    raise serializers.ValidationError({"asset": "This asset is already linked to a vehicle."})
                validated_data["asset"] = asset
                return super().create(validated_data)
        except Asset.DoesNotExist:
            raise serializers.ValidationError({"asset": "The selected vehicle asset is no longer available."})
        except IntegrityError:
            if Vehicle.objects.filter(asset_id=asset.pk).exists():
                raise serializers.ValidationError({"asset": "This asset is already linked to a vehicle."})
            raise


class VehicleAssignmentSerializer(serializers.ModelSerializer):
    start_mileage_km = serializers.IntegerField(write_only=True, min_value=0, required=False)

    def validate(self, attrs):
        mileage_km = attrs.get("start_mileage_km")
        if self.instance is None:
            has_mileage_record = attrs.get("start_mileage_record") is not None
            vehicle = attrs.get("vehicle")
            has_previous_release = (
                vehicle is not None
                and VehicleAssignment.objects.filter(
                    vehicle=vehicle,
                    release_mileage_record__isnull=False,
                ).exists()
            )
            if mileage_km is None and not has_mileage_record and not has_previous_release:
                raise serializers.ValidationError({
                    "start_mileage_km": "Provide a starting odometer reading or an existing mileage record when this vehicle has no previous release mileage."
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

            assignment_time = validated_data["assigned_at"]
            mileage_recorded_by = validated_data.get("assigned_by")
            if mileage_km is None and "start_mileage_record" not in validated_data:
                previous_release = VehicleAssignment.objects.filter(
                    vehicle=validated_data["vehicle"],
                    release_mileage_record__isnull=False,
                ).select_related("release_mileage_record", "released_by").order_by(
                    "-released_at", "-pk"
                ).first()
                if previous_release is not None:
                    mileage_km = previous_release.release_mileage_record.odometer_km
                    mileage_recorded_by = previous_release.released_by

            if mileage_km is not None:
                mileage = MileageRecord.objects.create(
                    vehicle=validated_data["vehicle"],
                    odometer_km=mileage_km,
                    recorded_at=assignment_time,
                    source=MileageRecord.Source.ASSIGNMENT_START,
                    recorded_by=mileage_recorded_by,
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


class UnassignVehicleInputSerializer(serializers.Serializer):
    released_at = serializers.DateTimeField()
    release_mileage_km = serializers.IntegerField(min_value=0)


class MileageRecordSerializer(serializers.ModelSerializer):
    previous_odometer_km = serializers.IntegerField(read_only=True, allow_null=True)
    distance_travelled_km = serializers.SerializerMethodField()
    vehicle_name = serializers.SerializerMethodField()
    vehicle_registration_number = serializers.CharField(source="vehicle.registration_number", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    def get_distance_travelled_km(self, obj) -> int | None:
        previous = getattr(obj, "previous_odometer_km", None)
        return None if previous is None else obj.odometer_km - previous

    def get_vehicle_name(self, obj) -> str:
        return f"{obj.vehicle.make} {obj.vehicle.model}".strip()

    def get_recorded_by_name(self, obj) -> str | None:
        if obj.recorded_by is None:
            return None
        return obj.recorded_by.get_full_name().strip() or obj.recorded_by.get_username()

    class Meta:
        model = MileageRecord
        fields = (
            "id",
            "odometer_km",
            "recorded_at",
            "source",
            "notes",
            "created_at",
            "vehicle",
            "recorded_by",
            "previous_odometer_km",
            "distance_travelled_km",
            "vehicle_name",
            "vehicle_registration_number",
            "recorded_by_name",
        )
        read_only_fields = ("recorded_by", "created_at")


class FuelRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelRecord
        fields = "__all__"
        read_only_fields = ("recorded_by", "created_at")


class ServiceRecordSerializer(serializers.ModelSerializer):
    vehicle_name = serializers.SerializerMethodField()
    vehicle_registration_number = serializers.CharField(source="vehicle.registration_number", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    def get_vehicle_name(self, obj) -> str:
        return f"{obj.vehicle.make} {obj.vehicle.model}".strip()

    def get_recorded_by_name(self, obj) -> str | None:
        if obj.recorded_by is None:
            return None
        return obj.recorded_by.get_full_name().strip() or obj.recorded_by.get_username()

    class Meta:
        model = ServiceRecord
        fields = (
            "id",
            "service_date",
            "description",
            "service_provider",
            "odometer_km",
            "cost",
            "currency",
            "next_service_date",
            "next_service_odometer_km",
            "notes",
            "created_at",
            "vehicle",
            "recorded_by",
            "vehicle_name",
            "vehicle_registration_number",
            "recorded_by_name",
        )
        read_only_fields = ("recorded_by", "created_at")


class InsurancePolicySerializer(serializers.ModelSerializer):
    vehicle_name = serializers.SerializerMethodField()
    vehicle_registration_number = serializers.CharField(source="vehicle.registration_number", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    def get_vehicle_name(self, obj) -> str:
        return f"{obj.vehicle.make} {obj.vehicle.model}".strip()

    def get_recorded_by_name(self, obj) -> str | None:
        if obj.recorded_by is None:
            return None
        return obj.recorded_by.get_full_name().strip() or obj.recorded_by.get_username()

    class Meta:
        model = InsurancePolicy
        fields = (
            "id",
            "insurer",
            "policy_number",
            "coverage_description",
            "start_date",
            "expiry_date",
            "premium",
            "currency",
            "recorded_by",
            "notes",
            "created_at",
            "vehicle",
            "vehicle_name",
            "vehicle_registration_number",
            "recorded_by_name",
        )
        read_only_fields = ("recorded_by", "created_at")


class LicensingRecordSerializer(serializers.ModelSerializer):
    vehicle_name = serializers.SerializerMethodField()
    vehicle_registration_number = serializers.CharField(source="vehicle.registration_number", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    def get_vehicle_name(self, obj) -> str:
        return f"{obj.vehicle.make} {obj.vehicle.model}".strip()

    def get_recorded_by_name(self, obj) -> str | None:
        if obj.recorded_by is None:
            return None
        return obj.recorded_by.get_full_name().strip() or obj.recorded_by.get_username()

    class Meta:
        model = LicensingRecord
        fields = (
            "id",
            "licence_type",
            "reference_number",
            "issuing_authority",
            "issue_date",
            "expiry_date",
            "cost",
            "currency",
            "recorded_by",
            "notes",
            "created_at",
            "vehicle",
            "vehicle_name",
            "vehicle_registration_number",
            "recorded_by_name",
        )
        read_only_fields = ("recorded_by", "created_at")
