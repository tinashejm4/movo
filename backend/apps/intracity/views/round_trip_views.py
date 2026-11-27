import mimetypes

from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from drf_spectacular.types import OpenApiTypes
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ..models import RoundTripOrder, RoundTripPOD
from ..serializers.round_trip_serializers import (
    RoundTripCancelSerializer, RoundTripCreateSerializer, RoundTripDetailSerializer,
    RoundTripFailureSerializer, RoundTripListSerializer, RoundTripPODUploadSerializer,
    RoundTripErrorSerializer, RoundTripPODResponseSerializer,
    RoundTripPriceInputSerializer, RoundTripPriceOutputSerializer,
    RoundTripResolveSerializer, RoundTripVerifySerializer,
    RoundTripRenewResponseSerializer,
)
from ..services.round_trip_access import is_round_trip_staff, visible_round_trips
from ..services.round_trip_creation import create_round_trip
from ..services.round_trip_pod import upload_round_trip_pod
from ..services.round_trip_presenter import order_payload
from ..services.round_trip_pricing import calculate_round_trip_price
from ..services.round_trip_resolution import cancel_round_trip, fail_round_trip_stop, resolve_round_trip
from ..services.round_trip_expiration import pickup_date
from ..services.round_trip_renewal import renew_round_trip
from ..services.round_trip_stop import verify_round_trip_stop


class RoundTripPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 10


def _order_queryset():
    return RoundTripOrder.objects.select_related(
        "sender__user", "recipient__user", "biker__user", "parcel", "invoice",
    ).prefetch_related("stops__contact__user", "stops__actions", "stops__pod", "cash_events")


class RoundTripViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["intracity/Round Trips"], request=RoundTripPriceInputSerializer,
                   responses={200: RoundTripPriceOutputSerializer,
                              400: OpenApiResponse(RoundTripErrorSerializer, description="Invalid route or pricing")})
    def calculate_price(self, request):
        serializer = RoundTripPriceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(RoundTripPriceOutputSerializer(calculate_round_trip_price(**serializer.validated_data)).data)

    @extend_schema(tags=["intracity/Round Trips"], request=RoundTripCreateSerializer,
                   responses={201: RoundTripDetailSerializer,
                              400: OpenApiResponse(RoundTripErrorSerializer, description="Invalid order")})
    def create(self, request):
        serializer = RoundTripCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_round_trip(user=request.user, data=serializer.validated_data)
        order = get_object_or_404(_order_queryset(), pk=order.pk)
        return Response(RoundTripDetailSerializer(order_payload(order, user=request.user, detail=True)).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(tags=["intracity/Round Trips"],
                   parameters=[OpenApiParameter("search", str, required=False),
                               OpenApiParameter("page", int, required=False),
                               OpenApiParameter("page_size", int, required=False)],
                   responses={200: RoundTripListSerializer})
    def list(self, request):
        queryset = _order_queryset().filter(pk__in=visible_round_trips(request.user).values("pk"))
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(slug__icontains=search) | Q(stops__address__icontains=search)
                | Q(parcel__description__icontains=search) | Q(status__icontains=search)
                | Q(sender__user__first_name__icontains=search)
                | Q(recipient__user__first_name__icontains=search)
                | Q(biker__user__first_name__icontains=search)
            ).distinct()
        paginator = RoundTripPagination()
        page = paginator.paginate_queryset(queryset.order_by("-created_at", "-pk"), request, view=self)
        return paginator.get_paginated_response([order_payload(order, user=request.user) for order in page])

    @extend_schema(tags=["intracity/Round Trips"], responses={200: RoundTripDetailSerializer,
                   404: RoundTripErrorSerializer})
    def retrieve(self, request, pk):
        order = get_object_or_404(_order_queryset().filter(
            pk__in=visible_round_trips(request.user).values("pk")), pk=pk)
        return Response(RoundTripDetailSerializer(order_payload(order, user=request.user, detail=True)).data)

    @extend_schema(tags=["intracity/Round Trips"], request=RoundTripVerifySerializer,
                   responses={200: RoundTripDetailSerializer, 400: RoundTripErrorSerializer,
                              403: RoundTripErrorSerializer, 404: RoundTripErrorSerializer,
                              409: RoundTripErrorSerializer})
    def verify_stop(self, request, pk, stop_id):
        serializer = RoundTripVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, error, code = verify_round_trip_stop(
            order_id=pk, stop_id=stop_id, user=request.user, data=serializer.validated_data,
        )
        if error:
            return Response({"error": error}, status=code)
        order = _order_queryset().get(pk=order.pk)
        return Response(RoundTripDetailSerializer(order_payload(order, user=request.user, detail=True)).data)

    @extend_schema(tags=["intracity/Round Trips"], request=RoundTripFailureSerializer,
                   responses={200: RoundTripDetailSerializer, 403: RoundTripErrorSerializer,
                              404: RoundTripErrorSerializer, 409: RoundTripErrorSerializer})
    def fail_stop(self, request, pk, stop_id):
        serializer = RoundTripFailureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, error, code = fail_round_trip_stop(
            order_id=pk, stop_id=int(stop_id), user=request.user, data=serializer.validated_data,
        )
        if error:
            return Response({"error": error}, status=code)
        return Response(RoundTripDetailSerializer(order_payload(_order_queryset().get(pk=order.pk), user=request.user, detail=True)).data)

    @extend_schema(tags=["intracity/Round Trips"], request={"multipart/form-data": RoundTripPODUploadSerializer},
                   responses={200: RoundTripPODResponseSerializer,
                              201: RoundTripPODResponseSerializer, 400: RoundTripErrorSerializer,
                              403: RoundTripErrorSerializer, 404: RoundTripErrorSerializer,
                              409: RoundTripErrorSerializer})
    def upload_pod(self, request, pk, stop_id):
        serializer = RoundTripPODUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pod, error, code = upload_round_trip_pod(
            order_id=pk, stop_id=stop_id, user=request.user, data=serializer.validated_data,
        )
        if error:
            return Response({"error": error}, status=code)
        return Response({"id": pod.pk, "stop_id": pod.stop_id, "uploaded_at": pod.uploaded_at}, status=code)

    @extend_schema(tags=["intracity/Round Trips"], responses={
        (200, "image/png"): OpenApiTypes.BINARY, (200, "image/jpeg"): OpenApiTypes.BINARY,
        403: RoundTripErrorSerializer, 404: RoundTripErrorSerializer,
        409: RoundTripErrorSerializer,
    })
    def download_pod(self, request, pk, stop_id):
        order = get_object_or_404(RoundTripOrder, pk=pk)
        if request.user.id != order.sender.user_id and not is_round_trip_staff(request.user):
            return Response({"error": "Access denied"}, status=403)
        pod = get_object_or_404(RoundTripPOD.objects.select_related("stop"), stop_id=stop_id,
                                stop__order=order, stop__kind="recipient")
        if pod.stop.completed_at is None:
            return Response({"error": "POD is available after verified handoff"}, status=409)
        content_type = mimetypes.guess_type(pod.image.name)[0] or "application/octet-stream"
        return FileResponse(pod.image.open("rb"), content_type=content_type)

    @extend_schema(tags=["intracity/Round Trips"], request=RoundTripCancelSerializer,
                   responses={200: RoundTripDetailSerializer, 404: RoundTripErrorSerializer,
                              409: RoundTripErrorSerializer})
    def cancel(self, request, pk):
        serializer = RoundTripCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, error, code = cancel_round_trip(
            order_id=pk, user=request.user, reason=serializer.validated_data.get("reason", ""),
        )
        if error:
            return Response({"error": error}, status=code)
        return Response(RoundTripDetailSerializer(order_payload(_order_queryset().get(pk=order.pk), user=request.user, detail=True)).data)

    @extend_schema(tags=["intracity/Round Trips"], responses={
        200: RoundTripRenewResponseSerializer, 403: RoundTripErrorSerializer,
        404: RoundTripErrorSerializer, 409: RoundTripErrorSerializer,
    })
    def renew(self, request, pk):
        order, error, code = renew_round_trip(order_id=pk, user=request.user)
        if error:
            return Response({"error": error}, status=code)
        return Response({
            "round_trip_id": order.pk, "status": order.status,
            "is_renewed": order.is_renewed, "pickup_date": pickup_date(order),
        }, status=200)

    @extend_schema(tags=["intracity/Round Trips"], request=RoundTripResolveSerializer,
                   responses={200: RoundTripDetailSerializer, 400: RoundTripErrorSerializer,
                              403: RoundTripErrorSerializer, 404: RoundTripErrorSerializer,
                              409: RoundTripErrorSerializer})
    def resolve(self, request, pk):
        if not is_round_trip_staff(request.user):
            return Response({"error": "Staff access required"}, status=403)
        serializer = RoundTripResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, error, code = resolve_round_trip(
            order_id=pk, user=request.user, data=serializer.validated_data,
        )
        if error:
            return Response({"error": error}, status=code)
        return Response(RoundTripDetailSerializer(order_payload(_order_queryset().get(pk=order.pk), user=request.user, detail=True)).data)

