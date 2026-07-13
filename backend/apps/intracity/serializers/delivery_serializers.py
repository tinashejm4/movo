from rest_framework import serializers


class DeliveryErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class AssignedPackageSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    is_fast_delivery = serializers.BooleanField()
    assigned_biker_id = serializers.IntegerField()
    assigned_biker_name = serializers.CharField(allow_blank=True)
    assigned_at = serializers.DateTimeField()
    added_at = serializers.DateTimeField()


class AssignPendingPackagesResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    assigned_count = serializers.IntegerField()
    unassigned_count = serializers.IntegerField()
    assigned_packages = AssignedPackageSerializer(many=True)


class PickupVerificationRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    sender_code = serializers.CharField()


class PickupVerificationResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    package_id = serializers.IntegerField()
    status = serializers.CharField()


class DropoffVerificationRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    receiver_code = serializers.CharField()


class DropoffVerificationResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    package_id = serializers.IntegerField()
    status = serializers.CharField()
    delivered_at = serializers.DateTimeField()


class CancelOrderRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()


class CancelOrderResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    package_id = serializers.IntegerField()
    status = serializers.CharField()
