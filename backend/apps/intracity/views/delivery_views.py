from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.bookkeeping.models import Account, IntracitySale
from apps.users.models import City, Suburb
from drf_spectacular.utils import OpenApiResponse, extend_schema
from ..models import Package, PackageStatus, Invoice, SuburbSearchLog
from ..services.package_assignment import assign_pending_packages
from ..services.package_cancellation import can_cancel_package
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
        return Response(assign_pending_packages(), status=status.HTTP_200_OK)

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
            Package.objects.select_related(
                "sender__user", "receiver__user", "invoice"
            ),
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
        invoice = getattr(package, "invoice", None)
        current_status = latest_status.status if latest_status else None
        if not can_cancel_package(
            invoice=invoice,
            current_status=current_status,
        ):
            if invoice and invoice.is_paid:
                return Response(
                    {"error": "Paid orders cannot be cancelled"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
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
