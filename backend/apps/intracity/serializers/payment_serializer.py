from rest_framework import serializers


class PaymentErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()

class PaymentProviderErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()
    details = serializers.JSONField(required=False)
    provider_response = serializers.JSONField(required=False)

class EcocashPaymentRequestSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField()
    phone_number = serializers.CharField()

class EcocashPaymentResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    invoice_id = serializers.IntegerField()
    amount = serializers.FloatField()
    is_request_successful = serializers.BooleanField()
    paid_at = serializers.DateTimeField()


class EcocashPaymentProcessedResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    invoice_id = serializers.IntegerField()
    amount = serializers.FloatField()
    provider_response = serializers.JSONField()
    paid_at = serializers.DateTimeField()


# Backward-compatible aliases for older imports.
MobilePaymentRequestSerializer = EcocashPaymentRequestSerializer
MobilePaymentResponseSerializer = EcocashPaymentResponseSerializer
