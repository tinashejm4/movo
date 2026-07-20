from rest_framework import serializers
from .models import City


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class TokenPairResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    username = serializers.CharField()


class StaffLoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class StaffProfileResponseSerializer(serializers.Serializer):
    staff_id = serializers.IntegerField()
    branch_id = serializers.IntegerField()
    branch_name = serializers.CharField()


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField()


class OTPCreateRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()


class OTPCreateResponseSerializer(serializers.Serializer):
    otp = serializers.CharField()


class CustomerRegisterLoginRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp_code = serializers.CharField()


class CustomerProfileResponseSerializer(serializers.Serializer):
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    phone_number = serializers.CharField(allow_blank=True, required=False)
    is_profile_complete = serializers.BooleanField()


class CustomerProfilePatchRequestSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["id", "name", "province", "country"]
        read_only_fields = [
            "id",
        ]
