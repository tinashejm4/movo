from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.users.models import City
from drf_spectacular.utils import OpenApiResponse, extend_schema
from ..models import Package, Invoice, Price
from ..serializers import (
    InvoiceAmountQuerySerializer,
    InvoiceAmountResponseSerializer,
    InvoiceErrorResponseSerializer,
    InvoiceQuoteResponseSerializer,
)

class InvoiceViewSet(ViewSet):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["intracity/Invoices"],
        parameters=[InvoiceAmountQuerySerializer],
        responses={
            200: InvoiceAmountResponseSerializer,
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

    def amount(self, request):
        package_id = request.query_params.get("package_id")
        if not package_id:
            return Response(
                {"error": "package_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        package = Package.objects.filter(id=package_id).first()
        if not package:
            return Response(
                {"error": "package not found"}, status=status.HTTP_404_NOT_FOUND
            )
        invoice = Invoice.objects.filter(package=package).first()
        serializer = InvoiceAmountResponseSerializer(
            {
                "package_id": package.id,
                "invoice_amount": invoice.amount if invoice else None,
                "invoice_amount_zig": invoice.amount_in_zig() if invoice else None,
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
