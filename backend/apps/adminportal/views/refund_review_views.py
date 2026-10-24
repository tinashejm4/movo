from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.intracity.models import RefundReview
from apps.users.permissions import IsStaff


def review_payload(review):
    return {
        "id": review.id,
        "package_id": review.invoice.package_id,
        "invoice_id": review.invoice_id,
        "recipient_id": review.recipient_id,
        "amount": str(review.amount),
        "payment_method": review.payment_method,
        "status": review.status,
        "reference": review.reference,
        "note": review.note,
        "created_at": review.created_at,
        "resolved_at": review.resolved_at,
        "resolved_by": review.resolved_by_id,
    }


class RefundReviewListView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        reviews = RefundReview.objects.select_related("invoice", "recipient").order_by("-created_at", "-pk")
        if request.query_params.get("status"):
            reviews = reviews.filter(status=request.query_params["status"])
        return Response({"results": [review_payload(review) for review in reviews[:100]]})


class RefundReviewResolveView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @transaction.atomic
    def post(self, request, review_id):
        review = get_object_or_404(RefundReview.objects.select_for_update().select_related("invoice"), pk=review_id)
        outcome = request.data.get("status")
        reference = str(request.data.get("reference") or "").strip()
        note = str(request.data.get("note") or "").strip()
        if review.status != "pending_review":
            return Response({"error": "Refund review is already resolved"}, status=status.HTTP_409_CONFLICT)
        if outcome not in {"refunded", "rejected"} or (outcome == "refunded" and not reference) or (outcome == "rejected" and not note):
            return Response({"error": "Valid status and a refund reference or rejection note are required"}, status=status.HTTP_400_BAD_REQUEST)
        review.status = outcome
        review.reference = reference
        review.note = note
        review.resolved_at = timezone.now()
        review.resolved_by = request.user
        review.save(update_fields=["status", "reference", "note", "resolved_at", "resolved_by"])
        return Response(review_payload(review))
