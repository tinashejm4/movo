import math
import random
import string
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.users.models import City, Contact, Customer, Suburb
from apps.bookkeeping.models import ExchangeRate
from ..serializers.package_serializers import (
    ErrorResponseSerializer,
    PackageDetailQuerySerializer,
    PackageDetailSerializer,
    PackageListSerializer,
    PackageCreateSerializer,
    PackagePriceRequestSerializer,
    PackagePriceResponseSerializer,
    SuburbSearchQuerySerializer,
    SuburbSearchResponseSerializer,
)
from ..models import Package, PackageStatus, Invoice, Price, SuburbSearchLog
from drf_spectacular.utils import OpenApiResponse, extend_schema
from apps.users.utils import normalize_zimbabwean_number

# TODO list, $id


class PackageViewSet(ViewSet):
    ACTIVE_PACKAGE_STATUSES = {"Pending", "In Transit"}

    def get_permissions(self):
        if self.action in {"create_package", "list_packages", "package_detail"}:
            return [IsAuthenticated()]
        if self.action in {"calculate_price", "search_suburb"}:
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["intracity/Packages"],
        request=None,
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

        response_data = []
        for package in packages:
            package_status = package.current_status or "Pending"
            if package.sender.user_id == request.user.id:
                role = "sender"
            elif package.receiver.user_id == request.user.id:
                role = "receiver"
            else:
                role = "biker"
            response_data.append(
                {
                    "package_id": package.id,
                    "role": role,
                    "status": (
                        "active"
                        if package_status in self.ACTIVE_PACKAGE_STATUSES
                        else "inactive"
                    ),
                    "city": package.city.name,
                    "pickup_location": package.pickup_location,
                    "dropoff_location": package.dropoff_location,
                    "is_fast_delivery": package.is_fast_delivery,
                    "sender_name": f"{package.sender.user.first_name} {package.sender.user.last_name}".strip(),
                    "receiver_name": f"{package.receiver.user.first_name} {package.receiver.user.last_name}".strip(),
                    "assigned_at": package.assigned_at,
                    "delivered_at": package.delivered_at,
                    "added_at": package.added_at,
                }
            )

        serializer = PackageListSerializer(
            {"count": len(response_data), "results": response_data}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

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

        package = get_object_or_404(
            Package.objects.select_related(
                "sender__user",
                "receiver__user",
                "city",
                "biker__user",
            ),
            id=package_id,
        )

        invoice = Invoice.objects.filter(package=package).first()

        return Response(
            self.serialize_package(package, invoice), status=status.HTTP_200_OK
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
    @transaction.atomic
    def create_package(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = PackageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        data = serializer.initial_data
        counterpart_phone = data.get("phone")
        counterpart_name = data.get("name")
        pickup_address = data.get("pickup_location")
        dropoff_address = data.get("dropoff_location")
        pickup_area_id = data.get("pickup_area_id")
        dropoff_area_id = data.get("dropoff_area_id")
        comments = data.get("comments")
        amount = data.get("amount")
        is_fast_delivery = bool(data.get("is_fast_delivery", False))
        is_pay_forward = bool(data.get("is_pay_forward", False))
        is_sender_initiated = bool(data.get("is_sender_initiated", True))

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

        invoice_amount = amount
        counterpart = self.resolve_customer(counterpart_phone, counterpart_name)
        city = City.objects.first()  # Assuming a single city for now; adjust as needed

        if is_sender_initiated:
            sender = Customer.objects.get(user=request.user)
            receiver = counterpart
        else:
            sender = counterpart
            receiver = Customer.objects.get(user=request.user)
        
        pickup_area = get_object_or_404(Suburb, id=pickup_area_id)
        dropoff_area = get_object_or_404(Suburb, id=dropoff_area_id)

        package = Package.objects.create(
            sender=sender,
            receiver=receiver,
            is_sender_initiated=is_sender_initiated,
            city=city,
            is_fast_delivery=is_fast_delivery,
            pickup_area=pickup_area,
            pickup_address=pickup_address,
            dropoff_area=dropoff_area,
            dropoff_address=dropoff_address,
            receiver_code=self.generate_code(),
            sender_code=self.generate_code(),
            comments=comments,
        )

        PackageStatus.objects.create(package=package, status="Pending")
        invoice = Invoice.objects.create(
            package=package,
            amount=invoice_amount,
            is_pay_forward=is_pay_forward,
            is_paid=False,
            exchange_rate = ExchangeRate.objects.last()
        )

        return Response(
            self.serialize_package(package, invoice),
            status=status.HTTP_201_CREATED,
        )

    def resolve_customer(self, phone_number, full_name=None):
        customer_default_password = "Pass@123"
        phone_number = normalize_zimbabwean_number(phone_number)

        if User.objects.filter(username=phone_number).exists():
            user = User.objects.get(username=phone_number)
        else:
            first_name, last_name = self.split_name(full_name, phone_number)
            user = User.objects.create_user(
                username=phone_number,
                password=customer_default_password,
                first_name=first_name,
                last_name=last_name,
            )

        Contact.objects.get_or_create(
            user=user, defaults={"phone_number": phone_number}
        )
        customer, _ = Customer.objects.get_or_create(user=user)
        return customer

    def split_name(self, full_name, fallback_name):
        name = (full_name or fallback_name or "Unknown").strip()
        parts = name.split()
        first_name = parts[0] if parts else "Unknown"
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        return first_name, last_name

    def generate_code(self):
        while True:
            code = "".join(random.choices(string.digits, k=6))
            if not Package.objects.filter(receiver_code=code).exists():
                return code

    def serialize_package(self, package, invoice=None):
        serializer = PackageDetailSerializer(
            {
                "package_id": package.id,
                "slug": package.slug,
                "receiver_id": package.receiver.id,
                "receiver_name": f"{package.receiver.user.first_name} {package.receiver.user.last_name}".strip(),
                "sender_id": package.sender.id,
                "sender_name": f"{package.sender.user.first_name} {package.sender.user.last_name}".strip(),
                "pickup_address": package.pickup_address,
                "pickup_area": package.pickup_area,
                "dropoff_address": package.dropoff_address,
                "dropoff_area": package.dropoff_area,
                "status": PackageStatus.objects.filter(package=package).order_by("-updated_at").first().status,
                "city": package.city.name,
                "driver_name": (
                    f"{package.biker.user.first_name} {package.biker.user.last_name}".strip()
                    if package.biker
                    else None
                ),
                "receiver_code": package.receiver_code,
                "sender_code": package.sender_code,
                "comments": package.comments,
                "is_sender_initiated": package.is_sender_initiated,
                "driver_id": package.biker.id if package.biker else None,
                "assigned_at": package.assigned_at,
                "delivered_at": package.delivered_at,
                "invoice_amount": invoice.amount if invoice else None,
                "invoice_amount_zig": invoice.amount_in_zig() if invoice else None,
                "added_at": package.added_at,
            }
        )
        return serializer.data

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
    @transaction.atomic
    def calculate_price(self, request):
        serializer = PackagePriceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        data = serializer.initial_data

        from_suburb_id = data.get("from_suburb_id")
        to_suburb_id = data.get("to_suburb_id")

        from_suburb = get_object_or_404(Suburb, id=from_suburb_id)
        to_suburb = get_object_or_404(Suburb, id=to_suburb_id)

        distance_km = from_suburb.distance_to(to_suburb)

        is_fast_delivery_raw = data.get("is_fast_delivery", False)
        city_id = data.get("city_id")

        if distance_km is None:
            return Response(
                {"error": "distance_km is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        if distance_km < 0:
            return Response(
                {"error": "distance_km must be zero or positive"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(is_fast_delivery_raw, str):
            is_fast_delivery = is_fast_delivery_raw.strip().lower() == "true"
        else:
            is_fast_delivery = bool(is_fast_delivery_raw)

        if city_id:
            city = City.objects.filter(id=city_id).first()
            if not city:
                return Response(
                    {"error": "city not found"}, status=status.HTTP_404_NOT_FOUND
                )
        else:
            city = City.objects.first()

        if not city:
            return Response(
                {"error": "No city configured"}, status=status.HTTP_400_BAD_REQUEST
            )

        price = Price.objects.filter(city=city).last()
        if not price:
            return Response(
                {"error": "No pricing configured for this city"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = float(price.base_price) + (float(price.rate_per_km) * distance_km)
        if is_fast_delivery:
            amount *= float(price.fast_delivery_multiplier)
        
        decimal_part = amount - math.floor(amount)
        if decimal_part > 0.40:
            amount = math.ceil(amount)   # round up
        else:
            amount = math.floor(amount)

        serializer = PackagePriceResponseSerializer(
            {
                "city_id": city.id,
                "distance_km": distance_km,
                "is_fast_delivery": is_fast_delivery,
                "amount": amount,
            }
        )
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["intracity/Delivery"],
        request=SuburbSearchQuerySerializer,
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
        data = request.data
        query = data.get("query", "").strip()
        city_id = data.get("city")
        if not query:
            return Response(
                {"error": "query is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        normalized_query = query.lower()
        suburbs_qs = Suburb.objects.filter(
            Q(name__icontains=query),
            Q(city__id=city_id) if city_id else Q(),
        ).values_list("name", flat=True).distinct()
        suburbs = list(suburbs_qs)

        SuburbSearchLog.objects.create(
            query=query,
            normalized_query=normalized_query,
            result_count=len(suburbs),
            had_results=bool(suburbs),
            user=request.user if request.user.is_authenticated else None,
        )

        return Response({"suburbs": list(suburbs)}, status=status.HTTP_200_OK)
