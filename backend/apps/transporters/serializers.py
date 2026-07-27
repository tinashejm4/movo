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

