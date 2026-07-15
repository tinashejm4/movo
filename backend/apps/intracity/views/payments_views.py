import base64
import random
import string
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.bookkeeping.models import Account, IntracitySale
from drf_spectacular.utils import OpenApiResponse, extend_schema
from ..serializers.payment_serializer import (
    EcocashPaymentProcessedResponseSerializer,
    EcocashPaymentRequestSerializer,
    EcocashPaymentResponseSerializer,
    PaymentErrorResponseSerializer,
    PaymentProviderErrorResponseSerializer,
)


class PaymentViewSet(ViewSet):
    # permission_classes = [IsAuthenticated]

    @staticmethod
    def _normalize_basic_auth_header(raw_header: str) -> str:
        if not raw_header:
            return ""
        header = str(raw_header).strip()
        if header.lower().startswith("basic "):
            return f"Basic {header[6:].strip()}"
        return f"Basic {header}"

    @extend_schema(
        tags=["intracity/Payments"],
        request=EcocashPaymentRequestSerializer,
        responses={
            200: EcocashPaymentResponseSerializer,
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
    def ecocash_payment(self, request):
        serializer = EcocashPaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        data = serializer.initial_data
        package_id = data.get("package_id")
        phone_number = data.get("phone_number")
        if not package_id:
            return Response(
                {"error": "package_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # package = get_object_or_404(Package.objects.select_related("sender__user", "receiver__user"), id=package_id)
        # invoice = get_object_or_404(Invoice, package=package)

        # if invoice.is_paid:
        #     return Response({"error": "This invoice has already been paid"}, status=status.HTTP_400_BAD_REQUEST)

        if not phone_number:
            return Response(
                {"error": "phone_number is required for EcoCash payments"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_auth_header = settings.ECOCASH_AUTH_HEADER
        if not raw_auth_header and not (
            settings.ECOCASH_CLIENT_ID and settings.ECOCASH_SECRET
        ):
            return Response(
                {"error": "EcoCash configuration is missing"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        def normalize_phone(phone):
            # Normalize the phone number to the format required by EcoCash
            if phone.startswith("0"):
                return f"263{phone[1:]}"
            elif phone.startswith("+263"):
                return f"263{phone[4:]}"
            elif phone.startswith("263"):
                return phone
            else:
                return f"263{phone}"

        normalized_phone = normalize_phone(phone_number)
        external_id = "".join(random.choices(string.digits, k=6))
        client_correlator = f"REF-{external_id}"
        reference_code = f"INV-{external_id}"

        payload = {
            "clientCorrelator": client_correlator,
            "referenceCode": reference_code,
            "tranType": "MER",
            "endUserId": normalized_phone,
            "paymentAmount": {
                "charginginformation": {
                    "amount": "1.00",
                    # "amount": f"{float(invoice.amount):.2f}",
                    "currency": "USD",
                    "description": "Intracity Payment",
                },
                "chargeMetaData": {"channel": "WEB"},
            },
            "merchantCode": settings.ECOCASH_MERCHANT_CODE,
            "merchantPin": settings.ECOCASH_MERCHANT_PIN,
            "merchantNumber": settings.ECOCASH_MERCHANT_NUMBER,
            "countryCode": "ZW",
            "terminalID": settings.ECOCASH_TERMINAL_ID,
            "location": settings.ECOCASH_LOCATION,
            "superMerchantName": settings.ECOCASH_SUPER_MERCHANT_NAME,
            "merchantName": settings.ECOCASH_MERCHANT_NAME,
            "transactionOperationStatus": "Charged",
            "remarks": "Intracity Payment",
            "notifyUrl": settings.ECOCASH_NOTIFY_URL,
        }

        if not raw_auth_header:
            raw_auth_header = base64.b64encode(
                f"{settings.ECOCASH_CLIENT_ID}:{settings.ECOCASH_SECRET}".encode()
            ).decode()

        headers = {
            "Content-Type": "application/json",
            "Authorization": self._normalize_basic_auth_header(raw_auth_header),
        }

        provider_response = None
        print(headers)
        print(settings.ECOCASH_PAYMENT_URL)
        print()
        req = Request(
            settings.ECOCASH_PAYMENT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(req, timeout=30) as response:
            provider_response = json.loads(response.read().decode("utf-8"))
        try:
            req = Request(
                settings.ECOCASH_PAYMENT_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urlopen(req, timeout=30) as response:
                provider_response = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
                provider_response = json.loads(error_body)
            except Exception:
                provider_response = {"error": str(exc), "reason": str(exc.reason)}
            return Response(
                {"error": "EcoCash request failed", "details": provider_response},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except URLError as exc:
            return Response(
                {"error": "EcoCash service unreachable", "details": str(exc.reason)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        operation_status = provider_response.get(
            "transactionOperationStatus"
        ) or provider_response.get("transactionStatus")
        if not operation_status or operation_status.lower() != "charged":
            return Response(
                {
                    "error": "EcoCash payment not completed",
                    "provider_response": provider_response,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = EcocashPaymentResponseSerializer({})
        return Response(serializer.data)

        if not invoice.is_pay_forward:
            if not account_id:
                return Response(
                    {
                        "error": "account_id is required to record sale for non-pay-forward invoices"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            account = Account.objects.filter(id=account_id).first()
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

        serializer = EcocashPaymentProcessedResponseSerializer(
            {
                "message": "EcoCash payment processed successfully",
                "invoice_id": invoice.id,
                "amount": float(invoice.amount),
                "provider_response": provider_response,
                "paid_at": invoice.paid_at,
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
