from django.db import transaction
from django.db.models import OuterRef, Subquery, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.bookkeeping.models import Account, IntracitySale
from apps.users.models import City, Suburb
from drf_spectacular.utils import OpenApiResponse, extend_schema
from ..models import Biker, Package, PackageStatus, Invoice, SuburbSearchLog
import logging
from ..serializers.delivery_serializers import (
    AssignPendingPackagesResponseSerializer,
    DeliveryErrorResponseSerializer,
    CancelOrderRequestSerializer,
    CancelOrderResponseSerializer,
    IsBikerAssignedRequestSerializer,
    IsBikerAssignedResponseSerializer,
    IsBikerAssignedErrorResponseSerializer,
)

logger = logging.getLogger(__name__)

class DeliveryViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["intracity/Delivery"],
        request=None,
        responses={
            200: AssignPendingPackagesResponseSerializer,
            400: OpenApiResponse(
                DeliveryErrorResponseSerializer,
                description="No pending packages or no available bikers",
            ),
        },
    )
    @transaction.atomic
    def assign_pending_packages(self, request):



        
        latest_status = (
            PackageStatus.objects.filter(package=OuterRef("pk"))
            .order_by("-updated_at")
            .values("status")[:1]
        )
        today = timezone.now().date()
        pending_packages = list(
            Package.objects.filter(biker__isnull=True, added_at__date=today)
            .annotate(current_status=Subquery(latest_status))
            .filter(current_status="Pending")
            .order_by("-is_fast_delivery", "added_at")
        )

        if not pending_packages:
            logger.info("assign_pending_packages: no pending packages found")
            return Response(
                {"message": "No pending packages available for assignment"},
                status=status.HTTP_200_OK,
            )

        free_bikers = []
        for biker in Biker.objects.select_related("user").order_by("id"):
            has_active_package = (
                Package.objects.filter(biker=biker)
                .annotate(current_status=Subquery(latest_status))
                .filter(current_status__in=["Pending", "In Transit"])
                .exists()
            )
            if not has_active_package:
                free_bikers.append(biker)

        if not free_bikers:
            logger.info("assign_pending_packages: no available bikers")
            return Response(
                {"message": "No available bikers for assignment"},
                status=status.HTTP_200_OK,
            )

        assignments = []
        channel_layer = get_channel_layer()

        for package, biker in zip(pending_packages, free_bikers):
            package.biker = biker
            package.assigned_at = timezone.now()
            package.save(update_fields=["biker", "assigned_at"])

            assignment_payload = {
                "package_id": package.id,
                "slug": package.slug,
                "is_fast_delivery": package.is_fast_delivery,
                "biker_id": biker.id,
                "biker_name": f"{biker.user.first_name} {biker.user.last_name}".strip(),
                "biker_phone": f"0{biker.user.username}",
                "assigned_at": package.assigned_at.isoformat()
                if package.assigned_at
                else None,
                "added_at": package.added_at.isoformat() if package.added_at else None,
            }
            assignments.append(assignment_payload)

            if channel_layer:
                try:
                    logger.info(
                        "assign_pending_packages: publishing package_id=%s biker_id=%s",
                        package.id,
                        biker.id,
                    )
                    async_to_sync(channel_layer.group_send)(
                        "package_assignments",
                        {"type": "package.assigned", "payload": assignment_payload},
                    )
                    async_to_sync(channel_layer.group_send)(
                        f"package_{package.id}",
                        {"type": "package.assigned", "payload": assignment_payload},
                    )
                except Exception as exc:
                    logger.warning("WebSocket publish skipped: %s", exc)

        logger.info(
            "assign_pending_packages: assigned_count=%s unassigned_count=%s",
            len(assignments),
            max(len(pending_packages) - len(assignments), 0),
        )

        response_payload = {
            "message": "Pending packages assigned successfully",
            "assigned_count": len(assignments),
            "unassigned_count": max(len(pending_packages) - len(assignments), 0),
            "assigned_packages": assignments,
        }
        return Response(response_payload, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["intracity/Delivery"],
        request=CancelOrderRequestSerializer,
        responses={
            200: CancelOrderResponseSerializer,
            400: OpenApiResponse(
                DeliveryErrorResponseSerializer,
                description="Incorrect request parameters",
            ),
            403: OpenApiResponse(
                DeliveryErrorResponseSerializer,
                description="User is not assigned to this package",
            ),
        },
    )
    @transaction.atomic
    def cancel_order(self, request):
        serializer = CancelOrderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        data = serializer.initial_data
        package_id = data.get("package_id")
        reason = (data.get("reason") or "").strip()
        if not package_id:
            return Response(
                {"error": "package_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        package = get_object_or_404(
            Package.objects.select_related("sender__user", "receiver__user"),
            id=package_id,
        )

        if request.user.id not in {package.sender.user_id, package.receiver.user_id}:
            return Response(
                {"error": "Only the sender or receiver can cancel this order"},
                status=status.HTTP_403_FORBIDDEN,
            )

        latest_status = (
            PackageStatus.objects.filter(package=package)
            .order_by("-updated_at")
            .first()
        )
        if not latest_status or latest_status.status != "Pending":
            return Response(
                {"error": "Order can only be cancelled when status is Pending"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PackageStatus.objects.create(package=package, status="Cancelled", comments=reason)

        serializer = CancelOrderResponseSerializer(
            {
                "message": f"Order cancelled successfully because: {reason}",
                "package_id": package.id,
                "status": "Cancelled",
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["intracity/Delivery"],
        parameters = [IsBikerAssignedRequestSerializer],
        responses={
            200: IsBikerAssignedResponseSerializer,
            400: OpenApiResponse(
                IsBikerAssignedErrorResponseSerializer,
                description="Incorrect request parameters",
            ),
            403: OpenApiResponse(
                IsBikerAssignedErrorResponseSerializer,
                description="User is not assigned to this package",
            ),
        },
    )
    def is_biker_assigned(self, request):
        serializer = IsBikerAssignedRequestSerializer(data=request.data)
        data = serializer.initial_data
        serializer.is_valid(raise_exception=False)
        package_id = data.get("package_id")
        logger.warning(f"Checking if biker is assigned for package_id: {package_id}")
        if not package_id:
            return Response(
                IsBikerAssignedErrorResponseSerializer(
                    {"error": "package_id query parameter is required"}
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )
        package = Package.objects.filter(id=package_id).first()
        if not package:
            return Response(
                IsBikerAssignedErrorResponseSerializer(
                    {"error": "Package not found"}
                ).data,
                status=status.HTTP_404_NOT_FOUND,
            )

        if package and package.biker:
            biker = package.biker
            return Response(
                IsBikerAssignedResponseSerializer(
                {
                    "is_assigned": True,
                    "package_id": package.id,
                    "biker_id": biker.id,
                    "biker_name": f"{biker.user.first_name} {biker.user.last_name}".strip(),
                    "biker_phone": f"0{biker.user.username}",
                },
            ).data,
            status=status.HTTP_200_OK,
        )
        else:
            return Response(
                IsBikerAssignedResponseSerializer(
                    {
                        "is_assigned": False,
                        "package_id": package.id,
                        "biker_id": None,
                        "biker_name": None,
                        "biker_phone": None,
                    }
                ).data,
                status=status.HTTP_200_OK,
            )
