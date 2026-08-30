from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from apps.intracity.models import Package, PackageStatus, Invoice
from apps.users.models import Suburb
from apps.intracity.services.package_assignment import assign_pending_packages
from apps.bookkeeping.models import Account, IntracitySale, FundsTransfer
from .models import BikerDailySession


from .serializers import (
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
    OrderSummaryResponseSerializer
)
import logging

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([AllowAny])
def test_assign_pending_packages(request):
    """Test-only endpoint for triggering automatic biker assignment."""
    return Response(assign_pending_packages(), status=status.HTTP_200_OK)


class TransporterView(ViewSet):
    permission_classes = [IsAuthenticated]

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
    def record_cash_sale(self, package, invoice):
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
    def daily_sales(self, request):
        account = Account.objects.filter(owner=request.user).first()

        sales = IntracitySale.objects.filter(account=account, created_at__date=timezone.now().date())
        
        sales_data = []
        total_sales = 0
        for sale in sales:
            data = {
                "invoice_id": sale.invoice.id,
                "amount": float(sale.amount),
                "created_at": sale.created_at,
            }
            sales_data.append(data)
            total_sales += float(sale.amount)

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
                    created_at__date=timezone.now().date(),
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

        packages = Package.objects.filter(driver=request.user, created_at__date=timezone.now().date())
        
        orders_data = []
        total_sales = 0
        for package in packages:
            pickup_surbub = Suburb.objects.get(id=package.pickup_area.id)
            dropoff_surbub = Suburb.objects.get(id=package.dropoff_area.id)
            invoice = Invoice.objects.get(package_id=package.id)
            latest_status = PackageStatus.objects.filter(package_id=package.id).order_by("-created_at").first()
            data = {
                "pickup_area": pickup_surbub.name,
                "pickup_address": package.pickup_address,
                "dropoff_area": dropoff_surbub.name,
                "dropoff_address": package.dropoff_address if package.dropoff_address else None,
                "amount": float(invoice.amount),
                "is_sender_initiated": package.is_sender_initiated,
                "assigned_at": package.assigned_at,
                "delivered_at": package.delivered_at,
                "latest_status": latest_status.status if latest_status else None,
                "added_at": package.added_at,
                "created_at": package.created_at,
            }
            orders_data.append(data)
            if invoice.payment_method == "Cash" and package.delivered_at:
                total_sales += float(invoice.amount)

        return Response(
            {
                "total_orders": len(orders_data),
                "cash_collected": total_sales,
                "orders": orders_data,
            },
            status=status.HTTP_200_OK,
        )