from django.db.models import OuterRef, Q, Subquery
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.users.models import Suburb
from ..serializers.package_serializers import (
    CurrentPackageStatusSerializer,
    ErrorResponseSerializer,
    PackageDetailQuerySerializer,
    PackageDetailSerializer,
    PackageListSerializer,
    PackageCreateSerializer,
    PackagePriceRequestSerializer,
    PackagePriceResponseSerializer,
    SuburbSearchResponseSerializer,
    PackageListRequestSerializer,
)
from ..models import Package, PackageStatus, Invoice, SuburbSearchLog
from ..services.create_package import (
    PackageCreationNotFound,
    create_package as create_package_service,
)
from ..services.package_pricing import (
    PackagePricingError,
    PackagePricingNotFound,
    calculate_package_price,
)
from ..services.package_cancellation import can_cancel_package
from ..services.package_access import (
    package_confirmation_code_for_user,
    package_initiator_user_id,
    package_is_incoming_for_user,
)
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from apps.users.utils import is_valid_zimbabwean_number


class PackageListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 10

class PackageViewSet(ViewSet):
    ACTIVE_PACKAGE_STATUSES = {"Pending", "In Transit"}

    def get_permissions(self):
        if self.action in {
            "create_package",
            "list_packages",
            "package_detail",
        }:
            return [IsAuthenticated()]
        if self.action in {"package_price", "search_suburb", "current_status"}:
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["intracity/Packages"],
        parameters=[PackageDetailQuerySerializer],
        responses={
            200: CurrentPackageStatusSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="package_id is required"
            ),
            404: OpenApiResponse(
                ErrorResponseSerializer, description="Package not found"
            ),
        },
    )
    def current_status(self, request):
        package_id = request.query_params.get("package_id")
        package_slug = request.query_params.get("package_slug")
        if not package_id and not package_slug:
            return Response(
                {"error": "package_id or package_slug is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        package_query = Package.objects.select_related(
            "sender__user", "receiver__user", "biker__user", "invoice"
        ).filter(Q(id=package_id) | Q(slug=package_slug))

        if request.user.is_authenticated:
            package_query = package_query.filter(
                Q(sender__user=request.user)
                | Q(receiver__user=request.user)
                | Q(biker__user=request.user)
            )

        package = package_query.first()
        if not package:
            return Response(
                {"error": f"Package not found. Please check the package code and try again."},
                status=status.HTTP_404_NOT_FOUND,
            )

        status_records = list(
            PackageStatus.objects.filter(package=package).order_by("updated_at")
        )
        latest_status = status_records[-1] if status_records else None
        current_status = latest_status.status if latest_status else "Pending"
        invoice = getattr(package, "invoice", None)

        status_map = {}
        for status_record in status_records:
            status_map.setdefault(status_record.status, status_record.updated_at)

        delivered_at = package.delivered_at or status_map.get("Delivered")
        collected_at = status_map.get("In Transit")
        cancelled_at = status_map.get("Cancelled")

        payload = {
            "package_id": package.id,
            "slug": package.slug,
            "driver_number": (
                self.get_phone_number(package.biker.user) if package.biker else None
            ),
            "status": current_status,
            "status_updated_at": latest_status.updated_at if latest_status else None,
            "is_active": (latest_status.status if latest_status else "Pending")
            in self.ACTIVE_PACKAGE_STATUSES,
            "is_collected": collected_at is not None or delivered_at is not None,
            "collected_at": collected_at,
            "is_cancelled": cancelled_at is not None,
            "cancelled_at": cancelled_at,
            "can_cancel": can_cancel_package(
                invoice=invoice,
                current_status=current_status,
            ),
            "is_delivered": delivered_at is not None,
            "delivered_at": delivered_at,
        }
        return Response(payload, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["intracity/Packages"],
        request=None,
        parameters=[
            OpenApiParameter(
                name="search",
                description=(
                    "Search by tracking slug, address, city, package status, or "
                    "sender, receiver, or driver details."
                ),
                required=False,
                type=str,
            ),
            OpenApiParameter(name="page", required=False, type=int),
            OpenApiParameter(name="page_size", required=False, type=int),
        ],
        responses={
            200: PackageListSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Incorrect request parameters"
            ),
        },
    )
    def list_packages(self, request):
        latest_status = (
            PackageStatus.objects.filter(package=OuterRef("pk"))
            .order_by("-updated_at")
            .values("status")[:1]
        )

        packages = (
            Package.objects.select_related(
                "sender__user", "receiver__user", "city", "biker__user"
            )
            .annotate(current_status=Subquery(latest_status))
            .filter(
                Q(sender__user=request.user)
                | Q(receiver__user=request.user)
                | Q(biker__user=request.user)
            )
            .distinct()
            .order_by("-added_at")
        )

        search_query = request.query_params.get("search", "").strip()
        if search_query:
            packages = packages.filter(
                Q(slug__icontains=search_query)
                | Q(pickup_address__icontains=search_query)
                | Q(dropoff_address__icontains=search_query)
                | Q(city__name__icontains=search_query)
                | Q(current_status__icontains=search_query)
                | Q(sender__user__first_name__icontains=search_query)
                | Q(sender__user__last_name__icontains=search_query)
                | Q(sender__user__username__icontains=search_query)
                | Q(receiver__user__first_name__icontains=search_query)
                | Q(receiver__user__last_name__icontains=search_query)
                | Q(receiver__user__username__icontains=search_query)
                | Q(biker__user__first_name__icontains=search_query)
                | Q(biker__user__last_name__icontains=search_query)
                | Q(biker__user__username__icontains=search_query)
            )

        paginator = PackageListPagination()
        page = paginator.paginate_queryset(packages, request, view=self)

        page_packages = list(page)
        package_ids = [package.id for package in page_packages]
        status_records_by_package_id = {}
        for status_record in PackageStatus.objects.filter(
            package_id__in=package_ids
        ).order_by("updated_at"):
            status_records_by_package_id.setdefault(
                status_record.package_id, []
            ).append(status_record)

        response_data = [
            self.build_package_list_payload(
                package=package,
                requester_user_id=request.user.id,
                status_records=status_records_by_package_id.get(package.id, []),
            )
            for package in page_packages
        ]

        return paginator.get_paginated_response(response_data)

    @extend_schema(
        tags=["intracity/Packages"],
        parameters=[PackageDetailQuerySerializer],
        responses={
            200: PackageDetailSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Incorrect request parameters"
            ),
        },
    )
    def package_detail(self, request):
        package_id = request.query_params.get("package_id")
        if not package_id:
            return Response(
                {"error": "package_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        package = Package.objects.select_related(
            "sender__user", "receiver__user"
        ).filter(id=package_id).first()
        if not package:
            return Response(
                {"error": f"Package not found for id {package_id}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.id not in {
            package.sender.user_id,
            package.receiver.user_id,
        }:
            return Response(
                {"error": "You do not have access to this package"},
                status=status.HTTP_403_FORBIDDEN,
            )

        invoice = Invoice.objects.filter(package=package).first()
        status_records = list(
            PackageStatus.objects.filter(package=package).order_by("updated_at")
        )

        return Response(
            self.build_package_payload(
                package,
                requester_user_id=request.user.id,
                invoice=invoice,
                status_records=status_records,
            ),
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["intracity/Packages"],
        request=PackageCreateSerializer,
        responses={
            200: PackageDetailSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Incorrect request parameters"
            ),
        },
    )
    def create_package(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = PackageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        counterpart_phone = data.get("phone")
        counterpart_name = data.get("name")
        pickup_address = data.get("pickup_location")
        dropoff_address = data.get("dropoff_location")

        required_fields = {
            "phone": counterpart_phone,
            "name": counterpart_name,
            "pickup_location": pickup_address,
            "dropoff_location": dropoff_address,
        }
        missing_fields = [
            field for field, value in required_fields.items() if not value
        ]
        if missing_fields:
            return Response(
                {"error": f"Missing required fields: {', '.join(missing_fields)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not is_valid_zimbabwean_number(counterpart_phone):
            return Response(
                {"error": f"Phone number format is incorrect: {counterpart_phone}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            package, invoice = create_package_service(user=request.user, data=data)
        except PackageCreationNotFound as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        status_records = list(
            PackageStatus.objects.filter(package=package).order_by("updated_at")
        )

        return Response(
            self.build_package_payload(
                package,
                requester_user_id=request.user.id,
                invoice=invoice,
                status_records=status_records,
            ),
            status=status.HTTP_201_CREATED,
        )

    def build_package_list_payload(
        self, package, requester_user_id, status_records=None
    ):
        if status_records is None:
            status_records = list(
                PackageStatus.objects.filter(package=package).order_by("updated_at")
            )

        status_map = {}
        for status_record in status_records:
            status_map.setdefault(status_record.status, status_record.updated_at)

        delivered_at = package.delivered_at or status_map.get("Delivered")
        collected_at = status_map.get("In Transit")

        serializer = PackageListRequestSerializer(
            {
                "package_id": package.id,
                "initiator_id": package_initiator_user_id(package),
                "pickup_address": package.pickup_address,
                "dropoff_address": package.dropoff_address,
                "collected_at": collected_at,
                "delivered_at": delivered_at,
                "slug": package.slug,
                "is_incoming": package_is_incoming_for_user(
                    package, requester_user_id
                ),
                "package_created_at": package.added_at,
            }
        )
        return serializer.data

    def build_package_payload(
        self, package, requester_user_id, invoice=None, status_records=None
    ):
        if status_records is None:
            status_records = list(
                PackageStatus.objects.filter(package=package).order_by("updated_at")
            )

        status_map = {}
        for status_record in status_records:
            status_map.setdefault(status_record.status, status_record.updated_at)

        delivered_at = package.delivered_at or status_map.get("Delivered")
        collected_at = status_map.get("In Transit")
        cancelled_at = status_map.get("Cancelled")
        current_status = (
            status_records[-1].status if status_records else "Pending"
        )

        receiver_id = package.receiver.id
        sender_id = package.sender.id
        initiator_id = package_initiator_user_id(package)

        serializer = PackageDetailSerializer(
            {
                "package_id": package.id,
                "slug": package.slug,
                "initiator_id": initiator_id,
                "receiver_id": receiver_id,
                "receiver_name": f"{package.receiver.user.first_name} {package.receiver.user.last_name}".strip(),
                "sender_id": sender_id,
                "sender_name": f"{package.sender.user.first_name} {package.sender.user.last_name}".strip(),
                "sender_phone": self.get_phone_number(package.sender.user),
                "receiver_phone": self.get_phone_number(package.receiver.user),
                "pickup_address": package.pickup_address,
                "pickup_area": package.pickup_area_id,
                "dropoff_address": package.dropoff_address,
                "dropoff_area": package.dropoff_area_id,
                "city": package.city.name,
                "is_fast_delivery": package.is_fast_delivery,
                "driver_name": (
                    f"{package.biker.user.first_name} {package.biker.user.last_name}".strip()
                    if package.biker
                    else None
                ),
                "driver_number": (
                    self.get_phone_number(package.biker.user) if package.biker else None
                ),
                "confirmation_code": package_confirmation_code_for_user(
                    package,
                    requester_user_id,
                    current_status=current_status,
                ),
                "comments": package.comments,
                "is_sender_initiated": package.is_sender_initiated,
                "package_created_at": package.added_at,
                "driver_id": package.biker.id if package.biker else None,
                "driver_assigned_at": package.assigned_at,
                "invoice_id": invoice.id if invoice else None,
                "is_collected": collected_at is not None or delivered_at is not None,
                "collected_at": collected_at,
                "is_cancelled": cancelled_at is not None,
                "cancelled_at": cancelled_at,
                "can_cancel": can_cancel_package(
                    invoice=invoice,
                    current_status=current_status,
                ),
                "is_delivered": delivered_at is not None,
                "delivered_at": delivered_at,
                "invoice_amount": invoice.amount if invoice else None,
                "invoice_amount_zig": invoice.amount_in_zig() if invoice else None,
            }
        )
        return serializer.data

    def get_phone_number(self, user):
        contact = getattr(user, "contact", None)
        if contact and contact.phone_number:
            return contact.phone_number
        return ""

    @extend_schema(
        tags=["intracity/Packages"],
        request=PackagePriceRequestSerializer,
        responses={
            200: PackagePriceResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Incorrect request parameters"
            ),
        },
    )
    def package_price(self, request):
        serializer = PackagePriceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        data = serializer.initial_data

        from_suburb_id = data.get("from_suburb_id")
        to_suburb_id = data.get("to_suburb_id")

        is_fast_delivery_raw = data.get("is_fast_delivery", False)
        city_id = data.get("city_id")

        try:
            price_result = calculate_package_price(
                from_suburb_id=from_suburb_id,
                to_suburb_id=to_suburb_id,
                city_id=city_id,
                is_fast_delivery=is_fast_delivery_raw,
            )
        except PackagePricingNotFound as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except PackagePricingError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PackagePriceResponseSerializer(price_result)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["intracity/Packages"],
        request=None,
        parameters=[
            OpenApiParameter(
                name="search",
                description=(
                    "Search by tracking slug, address, city, package status, or "
                    "sender, receiver, or driver details."
                ),
                required=False,
                type=str,
            ),
            OpenApiParameter(name="page", required=False, type=int),
            OpenApiParameter(name="page_size", required=False, type=int),
        ],
        responses={
            200: SuburbSearchResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Incorrect request parameters"
            ),
        },
    )
    @extend_schema(
        tags=["intracity/Packages"],
        parameters=[
            OpenApiParameter(
                name="query",
                description=("Search by suburb name."),
                required=False,
                type=str,
            ),
            OpenApiParameter(name="city_id", required=True, type=int),
            OpenApiParameter(name="page", required=False, type=int),
            OpenApiParameter(name="page_size", required=False, type=int),
        ],
        responses={
            200: SuburbSearchResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Incorrect request parameters"
            ),
            403: OpenApiResponse(
                ErrorResponseSerializer,
                description="User cannot get this suburb",
            ),
        },
    )
    def search_suburb(self, request):
        query = request.query_params.get("query", "").strip()
        city_id = request.query_params.get("city_id") or request.query_params.get(
            "city"
        )
        if not query:
            return Response(
                {"error": "query is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        normalized_query = query.lower()

        suburbs_qs = Suburb.objects.filter(name__icontains=query)
        if city_id:
            suburbs_qs = suburbs_qs.filter(city__id=city_id)

        suburbs = list(suburbs_qs.order_by("name").values("id", "name").distinct())

        if len(query) > 2:
            SuburbSearchLog.objects.create(
                query=query,
                normalized_query=normalized_query,
                result_count=len(suburbs),
                had_results=bool(suburbs),
                user=request.user if request.user.is_authenticated else None,
            )

        return Response({"suburbs": suburbs}, status=status.HTTP_200_OK)
