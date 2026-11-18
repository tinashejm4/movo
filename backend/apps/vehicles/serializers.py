from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import serializers

from apps.bookkeeping.models import Account, Asset, Expense, ExpenseAccount, GeneralExpense
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
    available = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()

    def _active_assignment(self, obj):
        assignment = getattr(obj, "_active_assignment_for_response", serializers.empty)
        if assignment is serializers.empty:
            prefetched = getattr(obj, "active_assignments", None)
            if prefetched is None:
                assignment = obj.assignments.filter(released_at__isnull=True).only("driver_id").first()
            else:
                assignment = prefetched[0] if prefetched else None
            obj._active_assignment_for_response = assignment
        return obj._active_assignment_for_response

    def get_available(self, obj) -> bool:
        return self._active_assignment(obj) is None

    def get_assigned_to(self, obj) -> int | None:
        assignment = self._active_assignment(obj)
        return assignment.driver_id if assignment is not None else None

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
                    "start_mileage_km": "This vehicle has no previous release mileage. Ask fleet staff to record its initial odometer reading."
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
        read_only_fields = (
            "assigned_by",
            "released_by",
            "created_at",
            "finish_mileage_required",
        )
        extra_kwargs = {"start_mileage_record": {"required": False}}


class ReassignVehicleInputSerializer(serializers.Serializer):
    driver = serializers.PrimaryKeyRelatedField(queryset=Biker.objects.all())
    handover_at = serializers.DateTimeField()
    release_mileage_km = serializers.IntegerField(min_value=0)
    start_mileage_km = serializers.IntegerField(min_value=0, required=False)
    handover_notes = serializers.CharField(required=False, allow_blank=True)


class UnassignVehicleInputSerializer(serializers.Serializer):
    released_at = serializers.DateTimeField()
    release_mileage_km = serializers.IntegerField(min_value=0)


class FinishVehicleAssignmentInputSerializer(serializers.Serializer):
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

    def validate(self, attrs):
        vehicle = attrs.get("vehicle", getattr(self.instance, "vehicle", None))
        recorded_at = attrs.get("recorded_at", getattr(self.instance, "recorded_at", None))
        odometer_km = attrs.get("odometer_km", getattr(self.instance, "odometer_km", None))

        if vehicle is not None and recorded_at is not None and odometer_km is not None:
            if self.instance is None:
                previous_records = MileageRecord.objects.filter(
                    vehicle=vehicle,
                    recorded_at__lte=recorded_at,
                )
            else:
                previous_records = MileageRecord.objects.filter(vehicle=vehicle).filter(
                    Q(recorded_at__lt=recorded_at)
                    | Q(recorded_at=recorded_at, pk__lt=self.instance.pk)
                )
            previous = previous_records.order_by("-recorded_at", "-pk").first()
            if previous is not None and odometer_km < previous.odometer_km:
                raise serializers.ValidationError({
                    "odometer_km": f"Mileage cannot be lower than the previous reading ({previous.odometer_km} km)."
                })

        return attrs

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
    account_id = serializers.PrimaryKeyRelatedField(
        source="account", queryset=Account.objects.all(), write_only=True
    )
    expense_type_id = serializers.PrimaryKeyRelatedField(
        source="expense_type", queryset=ExpenseAccount.objects.all(), write_only=True
    )
    total_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"), write_only=True
    )
    station = serializers.CharField(max_length=100, allow_blank=True, required=False, write_only=True)
    actual_date = serializers.DateTimeField(required=False, allow_null=True, write_only=True)
    expense = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)

    def validate(self, attrs):
        if self.instance is None:
            missing = [field for field in ("account", "expense_type", "total_cost") if field not in attrs]
            if missing:
                raise serializers.ValidationError({
                    {"account": "account_id", "expense_type": "expense_type_id", "total_cost": "total_cost"}[field]: "This field is required."
                    for field in missing
                })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        account = validated_data.pop("account")
        expense_type = validated_data.pop("expense_type")
        amount = validated_data.pop("total_cost")
        supplier = validated_data.pop("station", "")
        expense_date = validated_data.pop("actual_date", None)
        recorded_by = validated_data.get("recorded_by")

        fuel_record = FuelRecord.objects.create(**validated_data)
        vehicle = fuel_record.vehicle
        driver_name = (
            fuel_record.driver.user.get_full_name().strip()
            if fuel_record.driver_id else "Unknown driver"
        ) or (fuel_record.driver.user.get_username() if fuel_record.driver_id else "Unknown driver")
        litres = format(fuel_record.quantity_litres.normalize(), "f")
        description = f"Fuel {litres} litres in {vehicle.registration_number} by {driver_name}"
        expense_fields = {
            "account": account,
            "expense_type": expense_type,
            "amount": amount,
            "supplier": supplier,
            "description": description,
            "added_by": recorded_by,
        }
        if expense_date is not None:
            expense_fields["actual_date"] = expense_date
        expense = Expense.objects.create(**expense_fields)
        GeneralExpense.objects.create(expense=expense, added_by=recorded_by)
        fuel_record.expense = expense
        fuel_record.save(update_fields=("expense",))
        return fuel_record

    def update(self, instance, validated_data):
        # Financial fields are immutable through fuel-record updates; changes
        # to the ledger-backed expense belong in the bookkeeping workflow.
        for field in ("account", "expense_type", "total_cost", "station", "actual_date"):
            validated_data.pop(field, None)
        return super().update(instance, validated_data)

    class Meta:
        model = FuelRecord
        fields = (
            "id", "expense", "vehicle", "driver", "recorded_at", "quantity_litres",
            "odometer_km", "notes", "recorded_by", "created_at", "account_id",
            "expense_type_id", "total_cost", "station", "actual_date",
        )
        read_only_fields = ("recorded_by", "created_at", "expense")


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
