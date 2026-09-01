from enum import Enum

from rest_framework import serializers


class DateRangeQuerySerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )
        return attrs


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


class DailySaleSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_method = serializers.CharField()
    collected_at = serializers.DateField()


class DailySalesResponseSerializer(serializers.Serializer):
    total_sales = serializers.DecimalField(max_digits=10, decimal_places=2)
    sales = DailySaleSerializer(many=True)

class CancelPackageResponseSerializer(serializers.Serializer):
    status = serializers.CharField()


class DriverPaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"


class DriverPackageStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderSummaryItemSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    slug = serializers.SlugField()
    collected_from = serializers.CharField(allow_blank=True)
    delivered_to = serializers.CharField(allow_blank=True)
    pickup_area = serializers.CharField(allow_null=True)
    pickup_address = serializers.CharField()
    dropoff_area = serializers.CharField(allow_null=True)
    dropoff_address = serializers.CharField(allow_null=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_method = serializers.ChoiceField(
        choices=[method.value for method in DriverPaymentMethod]
    )
    cash_collected = serializers.DecimalField(max_digits=10, decimal_places=2)
    is_sender_initiated = serializers.BooleanField()
    assigned_at = serializers.DateTimeField(allow_null=True)
    collected_at = serializers.DateTimeField(allow_null=True)
    delivered_at = serializers.DateTimeField(allow_null=True)
    latest_status = serializers.ChoiceField(
        choices=[package_status.value for package_status in DriverPackageStatus],
        allow_null=True,
    )
    added_at = serializers.DateTimeField()


class OrderSummaryResponseSerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    cash_collected = serializers.DecimalField(max_digits=10, decimal_places=2)
    orders = OrderSummaryItemSerializer(many=True)
