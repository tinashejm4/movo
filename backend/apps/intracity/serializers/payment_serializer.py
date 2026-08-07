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

class PaynowPaymentRequestSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField(required=True)
    phone_number = serializers.CharField(required=True, max_length=20)

class PaynowPaymentResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    invoice_id = serializers.IntegerField()
    amount = serializers.FloatField()
    is_request_successful = serializers.BooleanField()
    poll_url = serializers.URLField()
    reference = serializers.CharField()
    paid_at = serializers.DateTimeField(required=False, allow_null=True)

class PaynowPaymentProcessedResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    invoice_id = serializers.IntegerField()
    amount = serializers.FloatField()
    is_paid = serializers.BooleanField()
    paid_at = serializers.DateTimeField(required=False, allow_null=True)

# Backward-compatible aliases for older imports.
MobilePaymentRequestSerializer = EcocashPaymentRequestSerializer
MobilePaymentResponseSerializer = EcocashPaymentResponseSerializer
