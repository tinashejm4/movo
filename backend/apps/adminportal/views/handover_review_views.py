from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.intracity.models import HandoverAttempt
from apps.transporters.handover_service import resolve_handover_attempt
from apps.users.permissions import IsStaff


class ResolveHandoverSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "reject"])
    reason = serializers.CharField(allow_blank=False)


class HandoverReviewListView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        attempts = HandoverAttempt.objects.filter(outcome="conflict").select_related(
            "package", "biker__user", "image"
        ).order_by("received_at", "pk")
        return Response({
            "results": [
                {
                    "id": str(attempt.pk),
                    "package_id": attempt.package_id,
                    "driver_id": attempt.biker.user_id,
                    "stage": attempt.stage,
                    "cash_received": attempt.cash_received,
                    "conflict_reason": attempt.conflict_reason,
                    "image_id": attempt.image_id,
                    "image_url": attempt.image.image.url,
                    "captured_at": attempt.captured_at,
                    "received_at": attempt.received_at,
                }
                for attempt in attempts
            ]
        })


class HandoverReviewResolveView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request, attempt_id):
        serializer = ResolveHandoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result_status, data = resolve_handover_attempt(
            attempt_id=attempt_id,
            reviewer=request.user,
            action=serializer.validated_data["action"],
            reason=serializer.validated_data["reason"],
        )
        return Response(data, status=result_status)
