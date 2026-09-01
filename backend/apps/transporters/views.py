from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from decimal import Decimal
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from apps.intracity.models import Package, PackageStatus, Invoice
from apps.intracity.services.package_assignment import assign_pending_packages
from apps.bookkeeping.models import Account, IntracitySale, FundsTransfer
from .models import BikerDailySession
from .services import free_drivers_and_close_packages


from .serializers import (
    DateRangeQuerySerializer,
    DriverPackageStatus,
    DriverPaymentMethod,
    PickupPackageRequestSerializer,
    PickupPackageResponseSerializer,
    DropoffPackageRequestSerializer,
    DropoffPackageResponseSerializer,
    ErrorResponseSerializer,
    ActivateDeactivateRequestSerializer,
    ActivateDeactivateResponseSerializer,
    CancelPackageRequestSerializer,
    CancelPackageResponseSerializer,
    DailySalesResponseSerializer,
    OrderSummaryResponseSerializer,
)
import logging

logger = logging.getLogger(__name__)

DRIVER_PACKAGE_STATUS_BY_VALUE = {
    "Pending": DriverPackageStatus.PENDING.value,
    "Assigned": DriverPackageStatus.ASSIGNED.value,
    "In Transit": DriverPackageStatus.IN_TRANSIT.value,
    "Delivered": DriverPackageStatus.DELIVERED.value,
    "Cancelled": DriverPackageStatus.CANCELLED.value,
}


@api_view(["POST"])
@permission_classes([AllowAny])
def test_assign_pending_packages(request):
    """Test-only endpoint for triggering automatic biker assignment."""
    return Response(assign_pending_packages(), status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def test_free_drivers(request):
    """Test-only endpoint that closes assigned packages and frees bikers."""
    return Response(
        free_drivers_and_close_packages(),
        status=status.HTTP_200_OK,
    )


class TransporterView(ViewSet):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def get_date_range(request):
        serializer = DateRangeQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        today = timezone.localdate()
        start_date = serializer.validated_data.get("start_date")
        end_date = serializer.validated_data.get("end_date")
        if start_date is None and end_date is None:
            return today, today
        start_date = start_date or end_date
        end_date = end_date or start_date
        return start_date, end_date

    @extend_schema(
        tags=["Biker Stuff"],
        responses={
            200: ActivateDeactivateResponseSerializer,
        },
    )
    def get_daily_session(self, request):
        session = BikerDailySession.objects.filter(
            biker__user=request.user,
            date=timezone.now().date(),
        ).first()

        return Response(
            {"is_biker_activated": bool(session and session.is_active)},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Biker Stuff"],
        request=ActivateDeactivateRequestSerializer,
        responses={
            200: ActivateDeactivateResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer,
                description="Incorrect request parameters",
            ),
            403: OpenApiResponse(
                ErrorResponseSerializer,
                description="Failed to activate/deactivate biker",
            ),
        },
    )

    @transaction.atomic
    def activate_deactivate(self, request):
        serializer = ActivateDeactivateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_biker_activated = serializer.validated_data.get("is_biker_activated")
        # Update the biker's daily session status
        session = BikerDailySession.objects.filter(biker__user=request.user, date=timezone.now().date()).first()
        if session:
            session.is_active = is_biker_activated
            session.save()
        else:
            BikerDailySession.objects.create(
                biker=request.user.biker,
                date=timezone.now().date(),
                start_time=timezone.now(),
                is_active=is_biker_activated,
            )
        logger.log(logging.INFO, f"Biker {'activated' if is_biker_activated else 'deactivated'} on {timezone.now().date()}")
        return Response(
            {"is_biker_activated": is_biker_activated},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Biker Stuff"],
        request=CancelPackageRequestSerializer,
        responses={
            200: CancelPackageResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer,
                description="Incorrect request parameters",
            ),
            403: OpenApiResponse(
                ErrorResponseSerializer,
                description="Biker is not assigned to this package",
            ),
        },
    )

    @transaction.atomic
    def cancel_package(self, request):
        serializer = CancelPackageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        package_id = serializer.validated_data.get("package_id")
        reason = serializer.validated_data.get("reason")

        package = get_object_or_404(Package, id=package_id)

        if not package.biker:
            return Response(
                {"error": "Package has not been assigned to a biker yet"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.biker.user_id != request.user.id:
            return Response(
                {"error": "Biker is not assigned to this package"},
                status=status.HTTP_403_FORBIDDEN,
            )

        latest_status = (
            PackageStatus.objects.filter(package=package)
            .order_by("-updated_at")
            .first()
        )
        if latest_status and latest_status.status not in ["Pending", "Assigned"]:
            return Response(
                {"error": "Package cannot be cancelled at this stage"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PackageStatus.objects.create(
            package=package,
            status="Cancelled",
            comments=reason,
            updated_at=timezone.now()
        )
        logger.log(logging.INFO, f"Package {package_id} cancelled by biker {request.user.id} for reason: {reason}. Date: {timezone.now()}")

        return Response(
            {"status": "Package cancelled successfully", "reason": reason},
            status=status.HTTP_200_OK,
        )


    @extend_schema(
        tags=["Biker Stuff"],
        request=PickupPackageRequestSerializer,
        responses={
            200: PickupPackageResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer,
                description="Incorrect request parameters",
            ),
            403: OpenApiResponse(
                ErrorResponseSerializer,
                description="Biker is not assigned to this package",
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
        tags=["Biker Stuff"],
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

        assign_pending_packages()

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
        invoice.save(
            update_fields=[
                "payment_method",
                "exchange_rate",
                "is_pay_forward",
                "is_paid",
                "paid_at",
            ]
        )
        return None

    @extend_schema(
        tags=["Biker Stuff"],
        parameters=[DateRangeQuerySerializer],
        responses={
            200: DailySalesResponseSerializer,
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
    def daily_sales(self, request):
        start_date, end_date = self.get_date_range(request)
        account = Account.objects.filter(owner=request.user).first()

        sales = (
            IntracitySale.objects.filter(
                account=account,
                added_at__range=(start_date, end_date),
                invoice__payment_method="Cash",
            )
            .select_related("invoice")
            .order_by("id")
        )
        
        sales_data = []
        total_sales = Decimal("0.00")
        for sale in sales:
            data = {
                "invoice_id": sale.invoice.id,
                "amount": Decimal(str(sale.amount)),
                "payment_method": sale.invoice.payment_method,
                "collected_at": sale.added_at,
            }
            sales_data.append(data)
            total_sales += Decimal(str(sale.amount))

        return Response(
            {"total_sales": total_sales,
             "sales": sales_data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
    tags=["Biker Stuff"],
    responses={
        200: DailySalesResponseSerializer,
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
    def end_day(self, request):
        biker_account = Account.objects.filter(owner=request.user).first()
        cash_account = Account.objects.get(name = "Cash", currency="USD")

        FundsTransfer.objects.create(
            from_account=biker_account,
            to_account=cash_account,
            amount=sum(
                float(sale.amount)
                for sale in IntracitySale.objects.filter(
                    account=biker_account,
                    added_at=timezone.localdate(),
                    invoice__payment_method="Cash",
                )
            ),
            comment=f"End of day cash transfer. Date {timezone.now().date()}",
            accepted_by=request.user,
        )

        return Response(
            {"message": "End of day cash transfer completed successfully."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Biker Stuff"],
        parameters=[DateRangeQuerySerializer],
        responses={
            200: OrderSummaryResponseSerializer,
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
    def order_summary(self, request):
        start_date, end_date = self.get_date_range(request)
        package_statuses = PackageStatus.objects.filter(package=OuterRef("pk"))
        latest_status = (
            package_statuses.order_by("-updated_at", "-pk")
            .values("status")[:1]
        )
        first_collection = (
            package_statuses.filter(status="In Transit")
            .order_by("updated_at", "pk")
            .values("updated_at")[:1]
        )
        packages = list(
            Package.objects.filter(
                biker__user=request.user,
                added_at__date__range=(start_date, end_date),
            )
            .select_related("pickup_area", "dropoff_area", "invoice")
            .annotate(
                current_status=Subquery(latest_status),
                collected_at=Subquery(first_collection),
            )
        )

        # cash_collected is based on cash collection records, not inferred from
        # an order merely being delivered with Cash selected as its method.
        cash_sales = {
            sale.invoice_id: Decimal(str(sale.amount))
            for sale in IntracitySale.objects.filter(
                account__owner=request.user,
                invoice__package__in=packages,
                invoice__payment_method="Cash",
                added_at__range=(start_date, end_date),
            )
        }

        orders_data = []
        cash_collected = Decimal("0.00")
        for package in packages:
            invoice = package.invoice
            order_cash_collected = cash_sales.get(invoice.id, Decimal("0.00"))
            data = {
                "package_id": package.id,
                "slug": package.slug,
                "pickup_area": package.pickup_area.name if package.pickup_area else None,
                "pickup_address": package.pickup_address,
                "dropoff_area": package.dropoff_area.name if package.dropoff_area else None,
                "dropoff_address": package.dropoff_address if package.dropoff_address else None,
                "amount": invoice.amount,
                "payment_method": (
                    DriverPaymentMethod.CASH.value
                    if invoice.payment_method == "Cash"
                    else DriverPaymentMethod.CARD.value
                ),
                "cash_collected": order_cash_collected,
                "is_sender_initiated": package.is_sender_initiated,
                "assigned_at": package.assigned_at,
                "collected_at": package.collected_at,
                "delivered_at": package.delivered_at,
                "latest_status": DRIVER_PACKAGE_STATUS_BY_VALUE.get(
                    package.current_status
                ),
                "added_at": package.added_at,
            }
            orders_data.append(data)
            cash_collected += order_cash_collected

        return Response(
            {
                "total_orders": len(orders_data),
                "cash_collected": cash_collected,
                "orders": orders_data,
            },
            status=status.HTTP_200_OK,
        )
