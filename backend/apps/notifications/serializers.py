from rest_framework import serializers

from .models import DeviceToken


class DeviceTokenRegistrationSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True, max_length=4096)
    app = serializers.ChoiceField(choices=DeviceToken.App.choices)
    platform = serializers.ChoiceField(choices=DeviceToken.Platform.choices)


class DeviceTokenDeactivationSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True, max_length=4096)
