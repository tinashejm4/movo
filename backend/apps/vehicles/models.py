from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, router, transaction
from django.db.models import Q

from apps.bookkeeping.models import Asset


class Vehicle(models.Model):
    class Type(models.TextChoices):
        MOTORCYCLE = "motorcycle", "Motorcycle"
        CAR = "car", "Car"
        VAN = "van", "Van"
        TRUCK = "truck", "Truck"
        BUS = "bus", "Bus"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MAINTENANCE = "maintenance", "In maintenance"
        RETIRED = "retired", "Retired"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="fleet_vehicles")
    vehicle_type = models.CharField(max_length=20, choices=Type.choices)
    registration_number = models.CharField(max_length=20, unique=True)
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    vin = models.CharField(max_length=50, null=True, blank=True, unique=True)
    engine_number = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["registration_number"]
        constraints = [
            models.UniqueConstraint(fields=["asset"], name="vehicles_unique_asset"),
        ]

    def __str__(self):
        return f"{self.registration_number} - {self.make} {self.model}"

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            if self._state.adding and not self.asset_id:
                self.asset = Asset.objects.using(using).create(
                    asset_type="vehicle",
                    name=f"{self.make} {self.model}"[:100],
                    unique_identifier=self.registration_number,
                )
            super().save(*args, **kwargs)


class MileageRecord(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual entry"
        ASSIGNMENT_START = "assignment_start", "Assignment start"
        ASSIGNMENT_RELEASE = "assignment_release", "Assignment release"
        HANDOVER = "handover", "Driver handover"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="mileage_records")
    odometer_km = models.PositiveBigIntegerField()
    recorded_at = models.DateTimeField()
    source = models.CharField(max_length=24, choices=Source.choices, default=Source.MANUAL)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_mileage_records",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [models.Index(fields=["vehicle", "recorded_at"])]

    def __str__(self):
        return f"{self.vehicle.registration_number}: {self.odometer_km} km"


class VehicleAssignment(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="assignments")
    driver = models.ForeignKey(
        "users.Biker", on_delete=models.PROTECT, related_name="vehicle_assignments"
    )
    assigned_at = models.DateTimeField()
    start_mileage_record = models.ForeignKey(
        MileageRecord,
        on_delete=models.PROTECT,
        related_name="assignment_starts",
    )
    released_at = models.DateTimeField(null=True, blank=True)
    release_mileage_record = models.ForeignKey(
        MileageRecord,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignment_releases",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_assignments_created",
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_assignments_released",
    )
    finish_mileage_required = models.BooleanField(default=False)
    handover_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assigned_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle"],
                condition=Q(released_at__isnull=True),
                name="one_active_assignment_per_vehicle",
            ),
            models.CheckConstraint(
                condition=(
                    Q(released_at__isnull=True, release_mileage_record__isnull=True)
                    | Q(released_at__isnull=False, release_mileage_record__isnull=False)
                ),
                name="assignment_release_fields_together",
            ),
        ]

    def clean(self):
        errors = {}
        if self.start_mileage_record_id:
            if self.start_mileage_record.vehicle_id != self.vehicle_id:
                errors["start_mileage_record"] = "Start mileage must belong to this vehicle."
            if self.start_mileage_record.source not in (
                MileageRecord.Source.ASSIGNMENT_START,
                MileageRecord.Source.HANDOVER,
            ):
                errors["start_mileage_record"] = "Start mileage must be marked as an assignment start or handover."
            if self.assigned_at and self.start_mileage_record.recorded_at > self.assigned_at:
                errors["start_mileage_record"] = "Start mileage cannot be recorded after assignment."

        if self.release_mileage_record_id:
            if self.release_mileage_record.vehicle_id != self.vehicle_id:
                errors["release_mileage_record"] = "Release mileage must belong to this vehicle."
            if self.release_mileage_record.source not in (
                MileageRecord.Source.ASSIGNMENT_RELEASE,
                MileageRecord.Source.HANDOVER,
            ):
                errors["release_mileage_record"] = "Release mileage must be marked as an assignment release or handover."
            if self.released_at and self.release_mileage_record.recorded_at > self.released_at:
                errors["release_mileage_record"] = "Release mileage cannot be recorded after release."
            if (
                self.start_mileage_record_id
                and self.release_mileage_record.odometer_km < self.start_mileage_record.odometer_km
            ):
                errors["release_mileage_record"] = "Release mileage cannot be lower than start mileage."

        if self.assigned_at and self.released_at and self.released_at < self.assigned_at:
            errors["released_at"] = "Release time cannot be before assignment time."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.vehicle.registration_number} assigned to {self.driver}"


class FuelRecord(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="fuel_records")
    driver = models.ForeignKey(
        "users.Biker",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_fuel_records",
    )
    recorded_at = models.DateTimeField()
    quantity_litres = models.DecimalField(max_digits=9, decimal_places=3)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    odometer_km = models.PositiveBigIntegerField(null=True, blank=True)
    station = models.CharField(max_length=150, blank=True)
    receipt_reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_fuel_records_created",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]

    def __str__(self):
        return f"{self.vehicle.registration_number}: {self.quantity_litres} L"


class ServiceRecord(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="service_records")
    service_date = models.DateField()
    description = models.TextField()
    service_provider = models.CharField(max_length=150, blank=True)
    odometer_km = models.PositiveBigIntegerField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    next_service_date = models.DateField(null=True, blank=True)
    next_service_odometer_km = models.PositiveBigIntegerField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_service_records",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-service_date", "-id"]

    def __str__(self):
        return f"{self.vehicle.registration_number}: {self.service_date}"

class InsurancePolicy(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="insurance_policies")
    insurer = models.CharField(max_length=150)
    policy_number = models.CharField(max_length=100)
    coverage_description = models.TextField(blank=True)
    start_date = models.DateField()
    expiry_date = models.DateField()
    premium = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_insurance_policies",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-id"]

    def __str__(self):
        return f"{self.vehicle.registration_number}: {self.policy_number}"


class LicensingRecord(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="licensing_records")
    licence_type = models.CharField(max_length=100, default="Vehicle licence")
    reference_number = models.CharField(max_length=100, blank=True)
    issuing_authority = models.CharField(max_length=150, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField()
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_licensing_records",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expiry_date", "-id"]

    def __str__(self):
        return f"{self.vehicle.registration_number}: {self.licence_type}"
