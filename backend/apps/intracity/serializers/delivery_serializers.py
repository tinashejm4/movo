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
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CancelOrderResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    package_id = serializers.IntegerField()
    status = serializers.CharField()

class IsBikerAssignedRequestSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()

class IsBikerAssignedResponseSerializer(serializers.Serializer):
    is_assigned = serializers.BooleanField()
    package_id = serializers.IntegerField()
    biker_id = serializers.IntegerField(allow_null=True)
    biker_name = serializers.CharField(allow_null=True, allow_blank=True)
    biker_phone = serializers.CharField(allow_null=True, allow_blank=True)
    
class IsBikerAssignedErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()