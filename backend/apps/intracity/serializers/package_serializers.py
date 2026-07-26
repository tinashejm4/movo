from rest_framework import serializers


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class PackageDetailRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    slug = serializers.CharField()
    receiver_id = serializers.IntegerField()
    receiver_name = serializers.CharField(allow_blank=True)
    sender_id = serializers.IntegerField()
    sender_name = serializers.CharField(allow_blank=True)
    sender_phone = serializers.CharField(allow_blank=True, required=False)
    receiver_phone = serializers.CharField(allow_blank=True, required=False)
    pickup_address = serializers.CharField()
    dropoff_address = serializers.CharField()
    pickup_area = serializers.IntegerField(allow_null=True, required=False)
    dropoff_area = serializers.IntegerField(allow_null=True, required=False)
    city = serializers.CharField()
    receiver_code = serializers.CharField()
    sender_code = serializers.CharField()
    comments = serializers.CharField(allow_null=True, allow_blank=True)
    is_fast_delivery = serializers.BooleanField()
    is_sender_initiated = serializers.BooleanField()
    package_created_at = serializers.DateTimeField()
    driver_name = serializers.CharField(allow_null=True, allow_blank=True)
    driver_id = serializers.IntegerField(allow_null=True, required=False)
    driver_assigned_at = serializers.DateTimeField(allow_null=True)
    invoice_id = serializers.IntegerField(allow_null=True, required=False)
    invoice_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    invoice_amount_zig = serializers.DecimalField(
        max_digits=20, decimal_places=2, allow_null=True
    )
    is_collected = serializers.BooleanField()
    collected_at = serializers.DateTimeField(allow_null=True)
    is_cancelled = serializers.BooleanField()
    cancelled_at = serializers.DateTimeField(allow_null=True)
    is_delivered = serializers.BooleanField()
    delivered_at = serializers.DateTimeField(allow_null=True)


PackageRequestSerializer = PackageDetailRequestSerializer
PackageDetailSerializer = PackageDetailRequestSerializer


class PackageListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PackageDetailRequestSerializer(many=True)


class PackageDetailQuerySerializer(serializers.Serializer):
    package_id = serializers.IntegerField()


class CurrentPackageStatusSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    slug = serializers.CharField()
    status = serializers.CharField()
    status_updated_at = serializers.DateTimeField(allow_null=True)
    is_active = serializers.BooleanField()
    is_collected = serializers.BooleanField()
    collected_at = serializers.DateTimeField(allow_null=True)
    is_cancelled = serializers.BooleanField()
    cancelled_at = serializers.DateTimeField(allow_null=True)
    is_delivered = serializers.BooleanField()
    delivered_at = serializers.DateTimeField(allow_null=True)


class PackageCreateSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    pickup_location = serializers.CharField(required=False)
    dropoff_location = serializers.CharField(required=False)
    pickup_area_id = serializers.IntegerField(required=True)
    dropoff_area_id = serializers.IntegerField(required=True)
    comments = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    is_fast_delivery = serializers.BooleanField(required=False, default=False)
    is_pay_forward = serializers.BooleanField(required=False, default=False)
    is_sender_initiated = serializers.BooleanField(required=False, default=True)


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
    city_id = serializers.IntegerField(required=False)


class SuburbSearchItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class SuburbSearchResponseSerializer(serializers.Serializer):
    suburbs = SuburbSearchItemSerializer(many=True)
