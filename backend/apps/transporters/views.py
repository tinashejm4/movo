from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from apps.intracity.models import Package, PackageStatus, Invoice
from apps.bookkeeping.models import Account, IntracitySale
from apps.intracity.views.delivery_views import DeliveryViewSet



from .serializers import (
    PickupPackageRequestSerializer,
    PickupPackageResponseSerializer,
    DropoffPackageRequestSerializer,
    DropoffPackageResponseSerializer,
    ErrorResponseSerializer,
)

class TransporterView(ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["transporters/Delivery"],
        request=PickupPackageRequestSerializer,
        responses={
            200: PickupPackageResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer,
                description="Incorrect request parameters",
            ),
            403: OpenApiResponse(
                ErrorResponseSerializer,
                description="User is not assigned to this package",
            ),
        },
    )

    @transaction.atomic
    def pickup_package(self, request):
        serializer = PickupPackageRequestSerializer(data=request.data)
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
            Package, id=package_id
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
        if latest_status and latest_status.status != "Pending":
            return Response(
                {"error": "Package should be Pending. Current status: " + latest_status.status.lower()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.sender_code != sender_code:
            return Response(
                {"error": "Invalid sender code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not package.is_pay_forward:
            invoice = Invoice.objects.filter(package=package).first()
            if not invoice:
                return Response(
                    {"error": "Package cannot be collected because the invoice is missing"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not invoice.is_paid:
                self.record_cash_sale(package, invoice)

        PackageStatus.objects.create(package=package, status="In Transit")

        DeliveryViewSet.assign_pending_packages(self, request)

        serializer = PickupPackageResponseSerializer(
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

    @extend_schema(
        tags=["transporters/Delivery"],
        request=DropoffPackageRequestSerializer,
        responses={
            200: DropoffPackageResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer,
                description="Incorrect request parameters",
            ),
            403: OpenApiResponse(
                ErrorResponseSerializer,
                description="User is not assigned to this package",
            ),
        },
    )

    @transaction.atomic
    def dropoff_package(self, request):
        serializer = DropoffPackageRequestSerializer(data=request.data)
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
                {"error": "Package must be in transit before it can be delivered. Current status: " + (latest_status.status.lower() if latest_status else "none")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.receiver_code != receiver_code:
            return Response(
                {"error": "Invalid receiver code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.is_pay_forward:
            invoice = Invoice.objects.filter(package=package).first()
            if not invoice:
                return Response(
                    {"error": "Package cannot be delivered because the invoice is missing"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not invoice.is_paid:
                self.record_cash_sale(package, invoice)

        PackageStatus.objects.create(package=package, status="Delivered")
        package.delivered_at = timezone.now()
        package.save(update_fields=["delivered_at"])

        DeliveryViewSet.assign_pending_packages(self, request)

        serializer = DropoffPackageResponseSerializer(
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

    @staticmethod
    def record_cash_sale(package, invoice):
        if not invoice:
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
        invoice.payment_method = "Cash"
        invoice.exchange_rate = None
        invoice.is_pay_forward = False

        invoice.is_paid = True
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["is_paid", "paid_at"])
        return None
