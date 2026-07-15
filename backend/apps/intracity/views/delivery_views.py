from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.bookkeeping.models import Account, IntracitySale
from drf_spectacular.utils import OpenApiResponse, extend_schema
from ..models import Biker, Package, PackageStatus, Invoice

from ..serializers.invoice_serializer import (
    InvoiceAmountQuerySerializer,
    InvoiceAmountResponseSerializer,
    InvoiceErrorResponseSerializer,
)

from ..serializers.delivery_serializers import (
    AssignPendingPackagesResponseSerializer,
    DeliveryErrorResponseSerializer,
    PickupVerificationRequestSerializer,
    PickupVerificationResponseSerializer,
    DropoffVerificationRequestSerializer,
    DropoffVerificationResponseSerializer,
    CancelOrderRequestSerializer,
    CancelOrderResponseSerializer,
)

class DeliveryViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["intracity/Delivery"],
        request=None,
        responses={
            200: AssignPendingPackagesResponseSerializer,
            400: OpenApiResponse(
                DeliveryErrorResponseSerializer,
                description="Incorrect request parameters",
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

        pending_packages = list(
            Package.objects.filter(biker__isnull=True)
            .annotate(current_status=Subquery(latest_status))
            .filter(current_status="Pending")
            .order_by("-is_fast_delivery", "added_at")
        )

        if not pending_packages:
            serializer = AssignPendingPackagesResponseSerializer(
                {
                    "message": "No pending packages available for assignment",
                    "assigned_count": 0,
                    "unassigned_count": 0,
                    "assigned_packages": [],
                }
            )
            return Response(
                serializer.data,
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
            serializer = AssignPendingPackagesResponseSerializer(
                {
                    "message": "No free riders available",
                    "assigned_count": 0,
                    "unassigned_count": len(pending_packages),
                    "assigned_packages": [],
                }
            )
            return Response(
                serializer.data,
                status=status.HTTP_200_OK,
            )

        assignments = []
        for package, biker in zip(pending_packages, free_bikers):
            package.biker = biker
            package.assigned_at = timezone.now()
            package.save(update_fields=["biker", "assigned_at"])
            assignments.append(
                {
                    "package_id": package.id,
                    "is_fast_delivery": package.is_fast_delivery,
                    "assigned_biker_id": biker.id,
                    "assigned_biker_name": f"{biker.user.first_name} {biker.user.last_name}".strip(),
                    "assigned_at": package.assigned_at,
                    "added_at": package.added_at,
                }
            )

        serializer = AssignPendingPackagesResponseSerializer(
            {
                "message": "Pending packages assigned successfully",
                "assigned_count": len(assignments),
                "unassigned_count": len(pending_packages) - len(assignments),
                "assigned_packages": assignments,
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["intracity/Delivery"],
        request=PickupVerificationRequestSerializer,
        responses={
            200: PickupVerificationResponseSerializer,
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
    def pickup_verify(self, request):
        serializer = PickupVerificationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        data = serializer.initial_data
        package_id = data.get("package_id")
        sender_code = (data.get("sender_code") or "").strip()

        if not package_id or not sender_code:
            return Response(
                {"error": "package_id and sender_code are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        package = get_object_or_404(
            Package.objects.select_related("biker__user"), id=package_id
        )
        if not package.biker:
            return Response(
                {"error": "Package has not been assigned to a biker yet"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.biker.user_id != request.user.id:
            return Response(
                {"error": "You are not assigned to this package"},
                status=status.HTTP_403_FORBIDDEN,
            )

        latest_status = (
            PackageStatus.objects.filter(package=package)
            .order_by("-updated_at")
            .first()
        )
        if latest_status and latest_status.status == "Delivered":
            return Response(
                {"error": "Package is already delivered"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.sender_code != sender_code:
            return Response(
                {"error": "Invalid sender code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sale_error = self.record_cash_sale(package, stage="pickup")
        if sale_error:
            return sale_error
        PackageStatus.objects.create(package=package, status="In Transit")

        serializer = PickupVerificationResponseSerializer(
            {
                "message": "Package collected successfully",
                "package_id": package.id,
                "status": "In Transit",
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def record_cash_sale(package, stage):
        invoice = Invoice.objects.filter(package=package).first()
        if not invoice:
            return None

        if invoice.is_paid:
            return None

        # Pay-forward means payment is expected at dropoff; otherwise at pickup.
        if stage == "pickup" and invoice.is_pay_forward:
            return None
        if stage == "dropoff" and not invoice.is_pay_forward:
            return None

        account = Account.objects.filter(owner=package.biker.user).first()
        if not account:
            return Response(
                {"error": "Account not found"}, status=status.HTTP_404_NOT_FOUND
            )

        IntracitySale.objects.get_or_create(
            invoice=invoice,
            defaults={
                "account": account,
                "amount": float(invoice.amount),
            },
        )

        invoice.is_paid = True
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["is_paid", "paid_at"])
        return None

    @extend_schema(
        tags=["intracity/Delivery"],
        request=DropoffVerificationRequestSerializer,
        responses={
            200: DropoffVerificationResponseSerializer,
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
    def dropoff_verify(self, request):
        serializer = DropoffVerificationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        data = serializer.initial_data
        package_id = data.get("package_id")
        receiver_code = (data.get("receiver_code") or "").strip()

        if not package_id or not receiver_code:
            return Response(
                {"error": "package_id and receiver_code are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        package = get_object_or_404(
            Package.objects.select_related("biker__user"), id=package_id
        )
        if not package.biker:
            return Response(
                {"error": "Package has not been assigned to a biker yet"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.biker.user_id != request.user.id:
            return Response(
                {"error": "You are not assigned to this package"},
                status=status.HTTP_403_FORBIDDEN,
            )

        latest_status = (
            PackageStatus.objects.filter(package=package)
            .order_by("-updated_at")
            .first()
        )
        if not latest_status or latest_status.status != "In Transit":
            return Response(
                {"error": "Package must be in transit before it can be delivered"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if latest_status.status == "Delivered":
            return Response(
                {"error": "Package is already delivered"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.receiver_code != receiver_code:
            return Response(
                {"error": "Invalid receiver code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sale_error = self.record_cash_sale(package, stage="dropoff")
        if sale_error:
            return sale_error

        package.delivered_at = timezone.now()
        package.save(update_fields=["delivered_at"])
        PackageStatus.objects.create(package=package, status="Delivered")

        serializer = DropoffVerificationResponseSerializer(
            {
                "message": "Package delivered successfully",
                "package_id": package.id,
                "status": "Delivered",
                "delivered_at": package.delivered_at,
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

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
                description="User cannot cancel this package",
            ),
        },
    )
    @transaction.atomic
    def cancel_order(self, request):
        serializer = CancelOrderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        data = serializer.initial_data
        package_id = data.get("package_id")
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

        PackageStatus.objects.create(package=package, status="Cancelled")

        serializer = CancelOrderResponseSerializer(
            {
                "message": "Order cancelled successfully",
                "package_id": package.id,
                "status": "Cancelled",
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
