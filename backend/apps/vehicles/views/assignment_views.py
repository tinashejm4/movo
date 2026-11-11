from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.permissions import IsStaff
from apps.users.models import Biker
from ..models import MileageRecord, VehicleAssignment
from ..serializers import (
    ReassignVehicleInputSerializer,
    UnassignVehicleInputSerializer,
    VehicleAssignmentSerializer,
)


class VehicleAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleAssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return VehicleAssignment.objects.select_related(
            "vehicle",
            "driver__user",
            "start_mileage_record",
            "release_mileage_record",
            "assigned_by",
            "released_by",
        )

    @action(detail=False, methods=["get"], url_path=r"by-vehicle/(?P<vehicle_id>\d+)")
    def by_vehicle(self, request, vehicle_id=None):
        """Return the current assignment for a vehicle, if it has one."""
        assignment = self.get_queryset().filter(
            vehicle_id=vehicle_id,
            released_at__isnull=True,
        ).first()
        if assignment is None:
            raise NotFound("No active assignment exists for this vehicle.")
        return Response(self.get_serializer(assignment).data)

    @action(detail=False, methods=["get"], url_path="my-assignment")
    def my_assignment(self, request):
        """Return whether the requesting user has an active vehicle assignment."""
        assignment = self.get_queryset().filter(
            driver__user=request.user,
            released_at__isnull=True,
        ).first()
        return Response({
            "assigned": assignment is not None,
            "assignment_id": assignment.pk if assignment is not None else None,
        })

    @action(detail=True, methods=["post"], url_path="reassign")
    def reassign(self, request, pk=None):
        input_serializer = ReassignVehicleInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        with transaction.atomic():
            try:
                current = VehicleAssignment.objects.select_for_update().get(pk=pk)
            except VehicleAssignment.DoesNotExist as error:
                raise NotFound("Assignment not found.") from error
            if current.released_at is not None:
                raise ValidationError({"assignment": "Only an active assignment can be replaced."})

            next_driver_id = data["driver"].pk
            if next_driver_id == current.driver_id:
                raise ValidationError({"driver": "Choose a different driver for this handover."})

            # Lock both driver rows in a stable order so concurrent assignments cannot
            # assign either driver to another vehicle while this handover is committing.
            locked_drivers = list(
                Biker.objects.select_for_update()
                .filter(pk__in=sorted({current.driver_id, next_driver_id}))
                .order_by("pk")
            )
            next_driver = next(driver for driver in locked_drivers if driver.pk == next_driver_id)
            if VehicleAssignment.objects.filter(driver=next_driver, released_at__isnull=True).exists():
                raise ValidationError({"driver": "This driver already has an active vehicle assignment."})

            handover_at = data["handover_at"]
            if data["start_mileage_km"] < data["release_mileage_km"]:
                raise ValidationError({
                    "start_mileage_km": "Starting mileage cannot be lower than the outgoing driver's return mileage."
                })

            release_record = MileageRecord.objects.create(
                vehicle=current.vehicle,
                odometer_km=data["release_mileage_km"],
                recorded_at=handover_at,
                source=MileageRecord.Source.ASSIGNMENT_RELEASE,
                recorded_by=request.user,
            )
            current.released_at = handover_at
            current.release_mileage_record = release_record
            current.released_by = request.user
            try:
                current.clean()
            except DjangoValidationError as error:
                detail = error.message_dict if hasattr(error, "message_dict") else error.messages
                raise ValidationError(detail) from error
            current.save(update_fields=("released_at", "release_mileage_record", "released_by"))

            start_record = MileageRecord.objects.create(
                vehicle=current.vehicle,
                odometer_km=data["start_mileage_km"],
                recorded_at=handover_at,
                source=MileageRecord.Source.ASSIGNMENT_START,
                recorded_by=request.user,
            )
            next_assignment = VehicleAssignment(
                vehicle=current.vehicle,
                driver=next_driver,
                assigned_at=handover_at,
                start_mileage_record=start_record,
                assigned_by=request.user,
                handover_notes=data.get("handover_notes", ""),
            )
            try:
                next_assignment.clean()
            except DjangoValidationError as error:
                detail = error.message_dict if hasattr(error, "message_dict") else error.messages
                raise ValidationError(detail) from error
            next_assignment.save()

        return Response({
            "released_assignment": self.get_serializer(current).data,
            "assignment": self.get_serializer(next_assignment).data,
        }, status=200)

    @action(detail=True, methods=["post"], url_path="unassign")
    def unassign(self, request, pk=None):
        input_serializer = UnassignVehicleInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        with transaction.atomic():
            try:
                assignment = VehicleAssignment.objects.select_for_update().get(pk=pk)
            except VehicleAssignment.DoesNotExist as error:
                raise NotFound("Assignment not found.") from error
            if assignment.released_at is not None:
                raise ValidationError({"assignment": "Only an active assignment can be released."})

            release_record = MileageRecord.objects.create(
                vehicle=assignment.vehicle,
                odometer_km=data["release_mileage_km"],
                recorded_at=data["released_at"],
                source=MileageRecord.Source.ASSIGNMENT_RELEASE,
                recorded_by=request.user,
            )
            assignment.released_at = data["released_at"]
            assignment.release_mileage_record = release_record
            assignment.released_by = request.user
            try:
                assignment.clean()
            except DjangoValidationError as error:
                detail = error.message_dict if hasattr(error, "message_dict") else error.messages
                raise ValidationError(detail) from error
            assignment.save(update_fields=("released_at", "release_mileage_record", "released_by"))

        return Response(self.get_serializer(assignment).data, status=200)

    def perform_create(self, serializer):
        serializer.save(assigned_by=self.request.user)

    def create(self, request, *args, **kwargs):
        is_staff = IsStaff().has_permission(request, self)
        driver = Biker.objects.filter(user=request.user).first()
        if not is_staff and driver is None:
            raise PermissionDenied("Only staff or a driver can create a vehicle assignment.")

        if driver is not None and not is_staff:
            data = request.data.copy()
            data["driver"] = driver.pk
            data["assigned_at"] = timezone.now()
            data["released_at"] = None
            data["release_mileage_record"] = None
            data["released_by"] = None
            request._full_data = data

        return super().create(request, *args, **kwargs)

    def perform_update(self, serializer):
        is_being_released = (
            serializer.instance.released_at is None
            and serializer.validated_data.get("released_at") is not None
        )
        if is_being_released:
            serializer.save(released_by=self.request.user)
        else:
            serializer.save()
