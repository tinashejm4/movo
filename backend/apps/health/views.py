from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        auth=[],
        responses={200: dict},
        description="Check whether the Movo API server is running.",
    )
    def get(self, request):
        return Response({"status": "ok", "service": "movo-api"})

