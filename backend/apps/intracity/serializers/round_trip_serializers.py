from decimal import Decimal

from rest_framework import serializers


class RoundTripLocationInputSerializer(serializers.Serializer):
    area_id = serializers.IntegerField(min_value=1)
    address = serializers.CharField(max_length=255)


class RoundTripContactInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30)


class RoundTripRecipientInputSerializer(RoundTripLocationInputSerializer):
    contact = RoundTripContactInputSerializer()
    actions = serializers.ListField(
        child=serializers.ChoiceField(choices=("DROP_OFF_ITEM", "COLLECT_CASH", "VERIFY_HANDOFF")),
        required=False,
    )


class RoundTripParcelInputSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=500)


class RoundTripCollectionInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.ChoiceField(choices=("USD", "ZIG"))


class RoundTripPriceInputSerializer(serializers.Serializer):
    pickup_area_id = serializers.IntegerField(min_value=1)
    recipient_area_id = serializers.IntegerField(min_value=1)
    is_fast_delivery = serializers.BooleanField(default=False, required=False)


class RoundTripPriceOutputSerializer(serializers.Serializer):
    city_id = serializers.IntegerField()
    distance_km = serializers.FloatField()
    is_fast_delivery = serializers.BooleanField()
    one_way_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class RoundTripCreateSerializer(serializers.Serializer):
    pickup = RoundTripLocationInputSerializer()
    stops = RoundTripRecipientInputSerializer(many=True)
    parcels = RoundTripParcelInputSerializer(many=True)
    collection = RoundTripCollectionInputSerializer()
    return_to_sender = serializers.BooleanField()
    is_fast_delivery = serializers.BooleanField(default=False, required=False)
    comments = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, data):
        if len(data["stops"]) != 1:
            raise serializers.ValidationError({"stops": "Exactly one recipient stop is supported."})
        if len(data["parcels"]) != 1:
            raise serializers.ValidationError({"parcels": "Exactly one parcel is supported."})
        if data["return_to_sender"] is not True:
            raise serializers.ValidationError({"return_to_sender": "Must be true."})
        actions = data["stops"][0].get("actions")
        if actions is not None and (len(actions) != 3 or set(actions) != {"DROP_OFF_ITEM", "COLLECT_CASH", "VERIFY_HANDOFF"}):
            raise serializers.ValidationError({"stops": "Recipient actions must include dropoff, cash collection, and verification."})
        return data


class RoundTripVerifySerializer(serializers.Serializer):
    otp = serializers.RegexField(regex=r"^\d{6}$")
    cash_amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.00"), required=False)
    cash_currency = serializers.ChoiceField(choices=("USD", "ZIG"), required=False)


class RoundTripPODUploadSerializer(serializers.Serializer):
    upload_id = serializers.UUIDField()
    image = serializers.ImageField()


class RoundTripCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class RoundTripFailureSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=120)


class RoundTripResolveSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=("resume", "cancelled"))
    reason = serializers.CharField()
    actual_collected = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.00"), required=False, allow_null=True)
    actual_returned = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.00"), required=False, allow_null=True)
    item_returned_to_sender = serializers.BooleanField(required=False, default=False)


class RoundTripActionOutputSerializer(serializers.Serializer):
    type = serializers.CharField()
    completed_at = serializers.DateTimeField(allow_null=True)


class RoundTripStopOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sequence = serializers.IntegerField()
    kind = serializers.CharField()
    area_id = serializers.IntegerField()
    address = serializers.CharField()
    contact_name = serializers.CharField()
    completed_at = serializers.DateTimeField(allow_null=True)
    otp = serializers.CharField(allow_null=True)
    actions = RoundTripActionOutputSerializer(many=True)
    has_pod = serializers.BooleanField()
    pod_url = serializers.CharField(allow_null=True)


class RoundTripErrorSerializer(serializers.Serializer):
    error = serializers.CharField()


class RoundTripPODResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    stop_id = serializers.IntegerField()
    uploaded_at = serializers.DateTimeField()


class RoundTripListItemSerializer(serializers.Serializer):
    round_trip_id = serializers.IntegerField()
    slug = serializers.CharField()
    status = serializers.CharField()
    parcel_description = serializers.CharField()
    created_at = serializers.DateTimeField()
    driver_id = serializers.IntegerField(allow_null=True)
    active_stop = RoundTripStopOutputSerializer(allow_null=True)


class RoundTripDetailSerializer(RoundTripListItemSerializer):
    sender_id = serializers.IntegerField()
    recipient_id = serializers.IntegerField()
    city_id = serializers.IntegerField()
    cash_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    cash_currency = serializers.CharField()
    cash_collected = serializers.DecimalField(max_digits=10, decimal_places=2)
    cash_returned = serializers.DecimalField(max_digits=10, decimal_places=2)
    invoice_id = serializers.IntegerField()
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2)
    assigned_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    exception_reason = serializers.CharField()
    stops = RoundTripStopOutputSerializer(many=True)


class RoundTripListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = RoundTripListItemSerializer(many=True)
