from rest_framework import serializers


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class PackageListItemSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    role = serializers.CharField()
    status = serializers.CharField()
    city = serializers.CharField()
    pickup_location = serializers.CharField()
    dropoff_location = serializers.CharField()
    is_fast_delivery = serializers.BooleanField()
    sender_name = serializers.CharField(allow_blank=True)
    receiver_name = serializers.CharField(allow_blank=True)
    assigned_at = serializers.DateTimeField(allow_null=True)
    delivered_at = serializers.DateTimeField(allow_null=True)
    added_at = serializers.DateTimeField()


class PackageListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = PackageListItemSerializer(many=True)


class PackageDetailQuerySerializer(serializers.Serializer):
    package_id = serializers.IntegerField()


class PackageDetailSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    slug = serializers.CharField()
    receiver_id = serializers.IntegerField()
    receiver_name = serializers.CharField(allow_blank=True)
    sender_id = serializers.IntegerField()
    sender_name = serializers.CharField(allow_blank=True)
    pickup_address = serializers.CharField()
    dropoff_address = serializers.CharField()
    status = serializers.CharField()
    city = serializers.CharField()
    driver_name = serializers.CharField(allow_null=True, allow_blank=True)
    receiver_code = serializers.CharField()
    sender_code = serializers.CharField()
    comments = serializers.CharField(allow_null=True, allow_blank=True)
    is_sender_initiated = serializers.BooleanField()
    driver_id = serializers.IntegerField(allow_null=True)
    driver_assigned_at = serializers.DateTimeField(allow_null=True)
    delivered_at = serializers.DateTimeField(allow_null=True)
    added_at = serializers.DateTimeField()
    invoice_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    invoice_amount_zig = serializers.DecimalField(
        max_digits=20, decimal_places=2, allow_null=True
    )


class PackageCreateSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    pickup_location = serializers.CharField(required=False)
    dropoff_location = serializers.CharField(required=False)
    comments = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    is_fast_delivery = serializers.BooleanField(required=False, default=False)
    is_pay_forward = serializers.BooleanField(required=False, default=False)
    initiated_by = serializers.ChoiceField(
        choices=["sender", "receiver"], required=False, default="sender"
    )

class PackagePriceRequestSerializer(serializers.Serializer):
    city_id = serializers.IntegerField(required=True)
    from_suburb_id = serializers.IntegerField()
    to_suburb_id = serializers.IntegerField()
    is_fast_delivery = serializers.BooleanField(required=False, default=False)

class PackagePriceResponseSerializer(serializers.Serializer):
    city_id = serializers.IntegerField()
    distance_km = serializers.FloatField()
    is_fast_delivery = serializers.BooleanField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

class SuburbSearchQuerySerializer(serializers.Serializer):
    query = serializers.CharField(required=True)
    city = serializers.CharField(required=False)

class SuburbSearchResponseSerializer(serializers.Serializer):
    surburb_id = serializers.CharField()