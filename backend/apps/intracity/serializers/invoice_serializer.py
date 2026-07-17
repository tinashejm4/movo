from rest_framework import serializers

class InvoiceErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class InvoiceAmountQuerySerializer(serializers.Serializer):
    package_id = serializers.IntegerField()


class InvoiceAmountResponseSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    invoice_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    invoice_amount_zig = serializers.DecimalField(
        max_digits=20, decimal_places=2, allow_null=True
    )