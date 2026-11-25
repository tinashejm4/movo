from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.users.models import City
from drf_spectacular.utils import OpenApiResponse, extend_schema
from ..models import Package, Invoice, PaynowPayment, Price, RoundTripOrder
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
from ..services.invoice_owner import invoice_order, order_participant_user_ids

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
        round_trip_id = request.query_params.get("round_trip_id")
        invoice_id = request.query_params.get("invoice_id")
        if not package_id and not round_trip_id and not invoice_id:
            return Response(
                {"error": "package_id, round_trip_id or invoice_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice = None
        if invoice_id:
            invoice = Invoice.objects.select_related(
                "package__sender__user", "package__receiver__user", "package__biker__user",
                "round_trip__sender__user", "round_trip__recipient__user", "round_trip__biker__user",
            ).filter(id=invoice_id).first()
            if not invoice:
                return Response(
                    {"error": "invoice not found"}, status=status.HTTP_404_NOT_FOUND
                )
            order = invoice_order(invoice)
        elif round_trip_id:
            order = RoundTripOrder.objects.select_related(
                "sender__user", "recipient__user", "biker__user"
            ).filter(id=round_trip_id).first()
            if order:
                invoice = Invoice.objects.filter(round_trip=order).first()
        else:
            order = Package.objects.select_related(
                "sender__user", "receiver__user", "biker__user"
            ).filter(id=package_id).first()
            if order:
                invoice = Invoice.objects.filter(package=order).first()

        if not order:
            return Response(
                {"error": "order not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if request.user.id not in order_participant_user_ids(order):
            return Response(
                {
                    "error": "You do not have access to this invoice",
                    "is_payer": False,
                    "can_pay": False,
                    "payment_pending": False,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        payment_pending = invoice_has_pending_payment(invoice)
        last_saved_payment = PaynowPayment.objects.filter(invoice=invoice, is_successful=False).order_by('created_at')

        if invoice and not invoice.is_paid and last_saved_payment.exists():
            # try polling again
            if last_saved_payment.exists():
                last_saved_payment = last_saved_payment.last()
            poll_url = last_saved_payment.poll_url if last_saved_payment else None
            poll_response = paynow.check_transaction_status(poll_url) if poll_url else None

            if poll_response and poll_response.status == "paid":
                last_saved_payment.is_successful = True
                last_saved_payment.paid_at = timezone.now()
                last_saved_payment.save(update_fields=["is_successful", "paid_at"])
                invoice.is_paid = True
                invoice.paid_at = timezone.now()
                invoice.save(update_fields=["is_paid", "paid_at"])

        payment_method = None
        if invoice and invoice.is_paid:
            payment_method = "cash" if invoice.payment_method == "Cash" else "card"

        serializer = InvoiceDetailsResponseSerializer(
            {
                "package_id": order.id if isinstance(order, Package) else None,
                **({"round_trip_id": order.id} if isinstance(order, RoundTripOrder) else {}),
                "invoice_id": invoice.id if invoice else None,
                "is_paid": invoice.is_paid if invoice else None,
                "payment_method": payment_method,
                "paid_at": invoice.paid_at if invoice and invoice.is_paid else None,
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
