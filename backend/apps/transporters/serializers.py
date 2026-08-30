from rest_framework import serializers

class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()

class PickupPackageRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    sender_code = serializers.CharField()


class PickupPackageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    package_id = serializers.IntegerField()
    status = serializers.CharField()

class DropoffPackageRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    receiver_code = serializers.CharField()


class DropoffPackageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    package_id = serializers.IntegerField()
    status = serializers.CharField()
    delivered_at = serializers.DateTimeField()

class ActivateDeactivateRequestSerializer(serializers.Serializer):
    is_biker_activated = serializers.BooleanField()

class ActivateDeactivateResponseSerializer(serializers.Serializer):
    is_biker_activated = serializers.BooleanField()

class CancelPackageRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    reason = serializers.CharField(required=False)

class DailySalesResponseSerializer(serializers.Serializer):
    total_sales = serializers.DecimalField(max_digits=10, decimal_places=2)

class CancelPackageResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
class OrderSummaryResponseSerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    cash_collected = serializers.DecimalField(max_digits=10, decimal_places=2)
    orders = serializers.ListField(child=serializers.DictField())