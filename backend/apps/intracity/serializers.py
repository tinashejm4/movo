from rest_framework import serializers


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()

class PackageListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sender_name = serializers.CharField()
    sender_phone_number = serializers.CharField()
    receiver_name = serializers.CharField()
    receiver_phone_number = serializers.CharField()
    pickup_address = serializers.CharField()
    delivery_address = serializers.CharField()
    status = serializers.CharField()

class PackageDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sender_name = serializers.CharField()
    sender_phone_number = serializers.CharField()
    receiver_name = serializers.CharField()
    receiver_phone_number = serializers.CharField()
    pickup_address = serializers.CharField()
    delivery_address = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

class PackageCreateSerializer(serializers.Serializer):
    sender_name = serializers.CharField()
    sender_phone_number = serializers.CharField()
    receiver_name = serializers.CharField()
    receiver_phone_number = serializers.CharField()
    pickup_address = serializers.CharField()
    delivery_address = serializers.CharField()