from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.users.models import City
from drf_spectacular.utils import OpenApiResponse, extend_schema
from ..models import Package, Invoice, PaynowPayment, Price
from ..serializers.invoice_serializer import (
    InvoiceDetailsQuerySerializer,
    InvoiceDetailsResponseSerializer,
    InvoiceErrorResponseSerializer,
)
from paynow import Paynow
import os
from ..services.invoice_payment import (
    invoice_has_pending_payment,
    invoice_user_can_pay,
    invoice_user_is_payer,
)

paynow = Paynow(
        os.environ.get("PAYNOW_INTEGRATION_ID", ""),
        os.environ.get("PAYNOW_INTEGRATION_KEY", ""),
        "http://google.com",
        "http://google.com",
        )

class InvoiceViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["intracity/Invoices"],
        parameters=[InvoiceDetailsQuerySerializer],
        responses={
            200: InvoiceDetailsResponseSerializer,
            400: OpenApiResponse(
                InvoiceErrorResponseSerializer,
                description="Incorrect request parameters",
            ),
            404: OpenApiResponse(
                InvoiceErrorResponseSerializer,
                description="Package not found",
            ),
        },
    )

    def invoice_details(self, request):
        package_id = request.query_params.get("package_id")
        if not package_id:
            return Response(
                {"error": "package_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        package = Package.objects.select_related(
            "sender__user", "receiver__user"
        ).filter(id=package_id).first()
        if not package:
            return Response(
                {"error": "package not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if request.user.id not in {
            package.sender.user_id,
            package.receiver.user_id,
        }:
            return Response(
                {
                    "error": "You do not have access to this invoice",
                    "is_payer": False,
                    "can_pay": False,
                    "payment_pending": False,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        invoice = Invoice.objects.filter(package=package).first()

        payment_pending = invoice_has_pending_payment(invoice)

        if invoice and not invoice.is_paid:
            last_saved_payment = PaynowPayment.objects.filter(invoice=invoice, is_successful=False).order_by('added_at').last()
            # try polling again
            poll_url = last_saved_payment.poll_url if last_saved_payment else None
            if not poll_url:
                return Response(
                    {"error": "Poll URL not found for the provided Paynow payment"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            poll_response = paynow.check_transaction_status(poll_url)

            if poll_response.status == "paid":
                last_saved_payment.is_successful = True
                last_saved_payment.paid_at = timezone.now()
                last_saved_payment.save(update_fields=["is_successful", "paid_at"])
                invoice.is_paid = True
                invoice.paid_at = timezone.now()
                invoice.save(update_fields=["is_paid", "paid_at"])

        serializer = InvoiceDetailsResponseSerializer(
            {
                "package_id": package.id,
                "invoice_id": invoice.id if invoice else None,
                "is_paid": invoice.is_paid if invoice else None,
                "is_pay_forward": invoice.is_pay_forward if invoice else None,
                "is_payer": invoice_user_is_payer(invoice, request.user.id),
                "can_pay": invoice_user_can_pay(invoice, request.user.id),
                "payment_pending": payment_pending,
                "invoice_amount": invoice.amount if invoice else None,
                "invoice_amount_zig": invoice.amount_in_zig() if invoice else None,
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
