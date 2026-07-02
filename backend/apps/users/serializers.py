from rest_framework import serializers


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
