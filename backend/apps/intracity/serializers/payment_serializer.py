from rest_framework import serializers


class PaymentErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class PaymentProviderErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()
    details = serializers.JSONField(required=False)
    provider_response = serializers.JSONField(required=False)


class EcocashPaymentRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    phone_number = serializers.CharField()


class EcocashPaymentResponseSerializer(serializers.Serializer):
    pass


class EcocashPaymentProcessedResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    invoice_id = serializers.IntegerField()
    amount = serializers.FloatField()
    provider_response = serializers.JSONField()
    paid_at = serializers.DateTimeField()
