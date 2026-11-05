from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.users.permissions import IsStaff
from ..models import VehicleAssignment
from ..serializers import VehicleAssignmentSerializer


class VehicleAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleAssignmentSerializer
    permission_classes = [IsAuthenticated, IsStaff]

    def get_queryset(self):
        return VehicleAssignment.objects.select_related(
            "vehicle",
            "driver__user",
            "start_mileage_record",
            "release_mileage_record",
            "assigned_by",
            "released_by",
        )

    def perform_create(self, serializer):
        serializer.save(assigned_by=self.request.user)

    def perform_update(self, serializer):
        is_being_released = (
            serializer.instance.released_at is None
            and serializer.validated_data.get("released_at") is not None
        )
        if is_being_released:
            serializer.save(released_by=self.request.user)
        else:
            serializer.save()
