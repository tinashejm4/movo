import random

from paynow import Paynow
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from urllib.error import HTTPError, URLError
import os
import requests
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from django.urls import reverse
from ..models import Invoice, EcocashPayment, PaynowPayment
from apps.bookkeeping.models import IntracitySale, Account
from ..services.invoice_payment import invoice_user_can_pay, invoice_user_is_payer
from apps.users.models import Customer
from drf_spectacular.utils import OpenApiResponse, extend_schema, OpenApiParameter
from ..serializers.payment_serializer import (
    MobilePaymentRequestSerializer,
    MobilePaymentResponseSerializer,
    PaymentErrorResponseSerializer,
    PaymentProviderErrorResponseSerializer,
    EcocashPaymentRequestSerializer,
    EcocashPaymentResponseSerializer,
    PaynowPaymentProcessedResponseSerializer,
    PaynowPaymentRequestSerializer,
    PaynowPaymentResponseSerializer,
)
from apps.users.utils import is_valid_zimbabwean_number,normalize_zimbabwean_number
import logging

logger = logging.getLogger(__name__)

paynow = Paynow(
        os.environ.get("PAYNOW_INTEGRATION_ID", ""),
        os.environ.get("PAYNOW_INTEGRATION_KEY", ""),
        "http://google.com",
        "http://google.com",
        )

class PaymentViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if getattr(self, "action", None) == "ecocash_notify":
            return [AllowAny()]
        return [permission() for permission in self.permission_classes]
    
    @staticmethod
    def _is_econet_number(phone_number):
        return phone_number[1] == "7" or phone_number[1] == "8"

    @staticmethod
    def _to_json_safe(value):
        """Return a log-safe representation without letting logging break callbacks."""
        if isinstance(value, dict):
            return {str(key): PaymentViewSet._to_json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [PaymentViewSet._to_json_safe(item) for item in value]
        return str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value

    @extend_schema(
        tags=["intracity/Payments"],
        request=PaynowPaymentRequestSerializer,
        responses={
            200: PaynowPaymentResponseSerializer,
            400: OpenApiResponse(
                PaymentProviderErrorResponseSerializer,
                description="Incorrect request parameters or incomplete payment",
            ),
            500: OpenApiResponse(
                PaymentErrorResponseSerializer,
                description="Payment configuration is missing",
            ),
            502: OpenApiResponse(
                PaymentProviderErrorResponseSerializer,
                description="Payment provider error",
            ),
        },
    )

    @transaction.atomic
    def paynow_payment(self, request):
        serializer = PaynowPaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice_id = serializer.validated_data["invoice_id"]
        phone_number = serializer.validated_data["phone_number"]

        phone_number = normalize_zimbabwean_number(phone_number)

        if not is_valid_zimbabwean_number(phone_number) or not self._is_econet_number(phone_number):
            return Response(
                PaymentErrorResponseSerializer(
                    {
                        "error": "Invalid Zimbabwean or Econet phone number format",
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice = Invoice.objects.select_for_update().select_related(
            "package__sender__user", "package__receiver__user"
        ).filter(id=invoice_id).first()

        if not invoice:
            return Response(
                PaymentErrorResponseSerializer(
                    {
                        "error": "Invoice not found for the provided package",
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not invoice_user_is_payer(invoice, request.user.id):
            return Response(
                {"error": "Only the customer responsible for this invoice can pay it"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if invoice.is_paid:
            return Response(
                PaymentErrorResponseSerializer(
                    {
                        "error": "Invoice is already paid",
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not invoice_user_can_pay(invoice, request.user.id):
            return Response(
                PaymentErrorResponseSerializer(
                    {"error": "Payment cannot be started for this invoice"}
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        ref = f"REF-{invoice.package.slug}-{random.randint(100000, 999999)}"
        payment = paynow.create_payment(ref, "movo@example.com")
        payment.add("Online Payment", invoice.amount)
        try:
            response = paynow.send_mobile(payment, f"0{phone_number}", "ecocash")
        except (HTTPError, URLError) as e:
            return Response(
                PaymentProviderErrorResponseSerializer(
                    {
                        "error": "Payment provider error",
                        "details": str(e),
                    }
                ).data,
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.success:
            PaynowPayment.objects.create(
                customer=Customer.objects.get(user=request.user),
                invoice=invoice,
                phone_number=phone_number,
                reference=ref,
                poll_url=response.poll_url,
            )
            invoice.payment_method = "PaynowEcocash"
            invoice.save(update_fields=["payment_method"])
            return Response(
                {
                    "message": "Payment request successful",
                    "poll_url": response.poll_url,
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                PaymentProviderErrorResponseSerializer(
                    {
                        "error": "Payment request failed",
                        "details": "Paynow Error",
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        tags=["intracity/Payments"],
        parameters=[
            OpenApiParameter(
                name="invoice_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
        ],
        responses={
            200: PaynowPaymentResponseSerializer,
            400: OpenApiResponse(
                PaymentProviderErrorResponseSerializer,
                description="Incorrect request parameters or incomplete payment",
            ),
            500: OpenApiResponse(
                PaymentErrorResponseSerializer,
                description="Payment configuration is missing",
            ),
            502: OpenApiResponse(
                PaymentProviderErrorResponseSerializer,
                description="Payment provider error",
            ),
        },
    )
    @transaction.atomic
    def paynow_notify(self, request):
        invoice_id = request.query_params.get("invoice_id")
        invoice = Invoice.objects.filter(id=invoice_id).first()

        if not invoice:
            return Response(
                PaymentErrorResponseSerializer(
                    {"error": "invoice_id is required"},
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invoice.is_paid:
            return Response(
                {
                    "message": "Invoice is already paid",
                    "invoice_id": invoice.id,
                    "is_paid": invoice.is_paid,
                    "amount": invoice.amount,
                },
                status=status.HTTP_200_OK,
            )

        paynow_payment = PaynowPayment.objects.filter(invoice=invoice).order_by("-pk").first()

        if not paynow_payment:
            return Response(
                {"error": "Paynow payment not found for the provided invoice"},
                status=status.HTTP_404_NOT_FOUND,
            )

        poll_url = paynow_payment.poll_url
        if not poll_url:
            return Response(
                {"error": "Poll URL not found for the provided Paynow payment"},
                status=status.HTTP_404_NOT_FOUND,
            )

        poll_response = paynow.check_transaction_status(poll_url)

        if poll_response.status == "paid":
            paynow_payment.is_successful = True
            paynow_payment.paid_at = timezone.now()
            paynow_payment.save(update_fields=["is_successful", "paid_at"])
            invoice.is_paid = True
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=["is_paid", "paid_at"])

            IntracitySale.objects.create(
                account=Account.objects.get(name = "FBC", currency = "USD"),
                invoice=invoice,
                amount=invoice.amount,
            )

            return Response(
                PaynowPaymentProcessedResponseSerializer(
                    {
                        "message": "Payment notification processed successfully",
                        "invoice_id": invoice.id,
                        "is_paid": invoice.is_paid,
                        "paid_at": invoice.paid_at,
                        "amount": invoice.amount,

                    }
                ).data,
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                PaymentErrorResponseSerializer(
                {
                    "error": "Payment not successful",
                }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

    @transaction.atomic
    def ecocash_payment(self, request):
        serializer = EcocashPaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice_id = serializer.validated_data["invoice_id"]
        phone_number = serializer.validated_data["phone_number"]

        phone_number = f"263{normalize_zimbabwean_number(phone_number)}"

        if not is_valid_zimbabwean_number(phone_number) or not self._is_econet_number(phone_number):
            return Response(
                PaymentErrorResponseSerializer(
                    {
                        "error": "Invalid Zimbabwean or Econet phone number format",
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice = Invoice.objects.select_for_update().select_related(
            "package__sender__user", "package__receiver__user"
        ).filter(id=invoice_id).first()

        if not invoice:
            return Response(
                PaymentErrorResponseSerializer(
                    {
                        "error": "Invoice not found for the provided package",
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not invoice_user_is_payer(invoice, request.user.id):
            return Response(
                {"error": "Only the customer responsible for this invoice can pay it"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if invoice.is_paid:
            return Response(
                PaymentErrorResponseSerializer(
                    {"error": "Invoice is already paid"}
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not invoice_user_can_pay(invoice, request.user.id):
            return Response(
                PaymentErrorResponseSerializer(
                    {"error": "Payment cannot be started for this invoice"}
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers={
            "Content-Type": "application/json",
            "Authorization": os.environ.get("ECOCASH_AUTH_HEADER"),
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }  # Removed the trailing comma to make it a dictionary instead of a tuple
        
        url = os.environ.get("ECOCASH_API_URL", "https://developers.ecocash.co.zw/sandbox/payment/v1/") + "transactions/amount/"

        data = {
                "clientCorrelator": "REF-" + str(invoice.package.slug) + "-" + str(random.randint(100000, 999999)),
                "referenceCode": f"{invoice_id}",
                "tranType": "MER",
                "endUserId": phone_number,
                "paymentAmount": {
                    "charginginformation": {
                        "amount": f"{invoice.amount:.2f}",
                        "currency": "USD",
                        "description": "Online Payment"
                    },
                    "chargeMetaData": {
                        "channel": "WEB"
                    }
                },
                "merchantCode": "287164",
                "merchantPin": "1234",
                "merchantNumber": "778503033",
                "countryCode": "ZW",
                "terminalID": "TERM001",
                "location": "Harare",
                "superMerchantName": "EcoCash Sandbox",
                "merchantName": "Test Merchant",
                "transactionOperationStatus": "Charged",
                "remarks": "Online Payment",
                "notifyUrl": request.build_absolute_uri(
                    reverse("intracity_ecocash_notify")
                ),
            }

        response = requests.post(
            url,
            headers=headers,
            json=data
        )

        if response.status_code != 200:
            return Response(
                PaymentErrorResponseSerializer(
                    {
                        "error": "Payment request failed",
                        "details": response.text,
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        provider_data = response.json()

        ecocash_payment = EcocashPayment.objects.create(
            customer=Customer.objects.get(user=request.user),
            invoice=invoice,
            phone_number=phone_number,
            client_correlator=provider_data.get("clientCorrelator"),
            request_response=response.json(),
        )

        return Response(
            {
                "message": "Payment request successful",
                "details": provider_data,
            },
            status=status.HTTP_200_OK,
        )
    
    @transaction.atomic
    def ecocash_update_payment_status(self, request):

        return Response(
            {"message": "Use ecocash_notify endpoint for provider callbacks."},
            status=status.HTTP_200_OK,
        )

# Cannot be tested on localhost. Therefore, this endpoint is designed to be called by the EcoCash provider's callback mechanism.
#test when hosted on a public server with a valid SSL certificate. The endpoint should be configured in the EcoCash provider's settings to receive payment notifications.
    @transaction.atomic
    def ecocash_notify(self, request):
        payload = request.data if isinstance(request.data, dict) else {}

        response_code = str(payload.get("ecocashResponseCode", "")).strip().upper()
        merchant_reference = str(payload.get("orginalMerchantReference", "")).strip()

        if response_code != "SUCCEEDED":
            return Response(
                {
                    "message": "Notification failed",
                    "ecocashResponseCode": response_code,
                    "orginalMerchantReference": merchant_reference,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not merchant_reference.isdigit():
            return Response(
                {"error": "Invalid orginalMerchantReference"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice_id = int(merchant_reference)

        invoice = Invoice.objects.filter(id=invoice_id).first()
        if not invoice:
            return Response(
                {"error": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not invoice.is_paid:
            invoice.is_paid = True
            invoice.paid_at = timezone.now()
            invoice.payment_method = "Ecocash"
            invoice.save(update_fields=["is_paid", "paid_at", "payment_method"])

        ecocash_payment = EcocashPayment.objects.filter(invoice=invoice).order_by("-created_at").first()
        if ecocash_payment:
            ecocash_payment.is_successful = True
            ecocash_payment.paid_at = invoice.paid_at
            ecocash_payment.provider_response = payload
            ecocash_payment.save(update_fields=["is_successful", "paid_at", "provider_response"])


        return Response(
            {
                "message": "Notification processed",
                "invoice_id": invoice.id,
                "updated": True,
                "is_paid": True,
                "ecocashResponseCode": response_code,
                "orginalMerchantReference": merchant_reference,
            },
            status=status.HTTP_200_OK,
        )
