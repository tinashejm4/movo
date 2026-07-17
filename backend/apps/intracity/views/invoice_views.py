from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.users.models import City
from drf_spectacular.utils import OpenApiResponse, extend_schema
from ..models import Package, Invoice, Price
from ..serializers.invoice_serializer import (
    InvoiceDetailsQuerySerializer,
    InvoiceDetailsResponseSerializer,
    InvoiceErrorResponseSerializer,
)

class InvoiceViewSet(ViewSet):
    permission_classes = [AllowAny]

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
        package = Package.objects.filter(id=package_id).first()
        if not package:
            return Response(
                {"error": "package not found"}, status=status.HTTP_404_NOT_FOUND
            )
        invoice = Invoice.objects.filter(package=package).first()
        serializer = InvoiceDetailsResponseSerializer(
            {
                "package_id": package.id,
                "invoice_id": invoice.id if invoice else None,
                "is_paid": invoice.is_paid if invoice else None,
                "is_pay_forward": invoice.is_pay_forward if invoice else None,
                "invoice_amount": invoice.amount if invoice else None,
                "invoice_amount_zig": invoice.amount_in_zig() if invoice else None,
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )