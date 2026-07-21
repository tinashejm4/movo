from rest_framework import serializers

class InvoiceErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class InvoiceDetailsQuerySerializer(serializers.Serializer):
    package_id = serializers.IntegerField()


class InvoiceDetailsResponseSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    invoice_id = serializers.IntegerField(allow_null=True)
    is_paid = serializers.BooleanField(allow_null=True)
    is_pay_forward = serializers.BooleanField(allow_null=True)
    invoice_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    invoice_amount_zig = serializers.DecimalField(
        max_digits=20, decimal_places=2, allow_null=True
    )


# Backward-compatible aliases expected by imports in serializers package.
InvoiceAmountQuerySerializer = InvoiceDetailsQuerySerializer
InvoiceAmountResponseSerializer = InvoiceDetailsResponseSerializer