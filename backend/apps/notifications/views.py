from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DeviceToken
from .serializers import DeviceTokenDeactivationSerializer, DeviceTokenRegistrationSerializer


class DeviceTokenView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Notifications"], request=DeviceTokenRegistrationSerializer)
    def post(self, request):
        serializer = DeviceTokenRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        DeviceToken.objects.update_or_create(
            token=values["token"],
            defaults={
                "user": request.user,
                "app": values["app"],
                "platform": values["platform"],
                "is_active": True,
                "last_seen_at": timezone.now(),
            },
        )
        return Response({"message": "Device registered"})

    @extend_schema(tags=["Notifications"], request=DeviceTokenDeactivationSerializer)
    def delete(self, request):
        serializer = DeviceTokenDeactivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        DeviceToken.objects.filter(
            user=request.user, token=serializer.validated_data["token"]
        ).update(is_active=False, last_seen_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)
