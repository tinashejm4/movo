import math
import random
import string
from django.conf import settings
import requests, base64, logging
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from apps.users.models import City, Contact, Customer, Suburb
from apps.bookkeeping.models import ExchangeRate
from ..serializers.package_serializers import (
    CurrentPackageStatusSerializer,
    ErrorResponseSerializer,
    PackageContactsQuerySerializer,
    PackageContactsResponseSerializer,
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
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from apps.users.utils import normalize_zimbabwean_number, is_valid_zimbabwean_number

logger = logging.getLogger(__name__)


class PackageListPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PackageViewSet(ViewSet):
    ACTIVE_PACKAGE_STATUSES = {"Pending", "In Transit"}

    def get_permissions(self):
        if self.action in {
            "create_package",
            "list_packages",
            "package_detail",
            "current_status",
            "get_contacts",
        }:
            return [IsAuthenticated()]
        if self.action in {"package_price", "search_suburb"}:
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["intracity/Packages"],
        parameters=[PackageContactsQuerySerializer],
        responses={
            200: PackageContactsResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="is_sending is required"
            ),
        },
    )
    def get_contacts(self, request):
        is_sending_param = request.query_params.get("is_sending")
        if is_sending_param is None:
            return Response(
                {"error": "is_sending query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_sending = is_sending_param.lower() in ("true", "1")
        customer = getattr(request.user, "customer", None)
        if not customer:
            return Response({"contacts": []}, status=status.HTTP_200_OK)

        LIMIT = 15

        if is_sending:
            # User is sending — return 15 most recently contacted distinct receivers
            packages = (
                Package.objects.filter(sender=customer)
                .select_related("receiver__user")
                .order_by("-added_at")
            )
            seen = set()
            contacts = []
            for p in packages:
                uid = p.receiver_id
                if uid in seen:
                    continue
                seen.add(uid)
                contacts.append(
                    {
                        "id": p.receiver.user.id,
                        "name": f"{p.receiver.user.first_name} {p.receiver.user.last_name}".strip(),
                        "phone": f"0{p.receiver.user.username}",
                    }
                )
                if len(contacts) == LIMIT:
                    break
        else:
            # User is receiving — return 15 most recently sent-from distinct senders
            packages = (
                Package.objects.filter(receiver=customer)
                .select_related("sender__user")
                .order_by("-added_at")
            )
            seen = set()
            contacts = []
            for p in packages:
                uid = p.sender_id
                if uid in seen:
                    continue
                seen.add(uid)
                contacts.append(
                    {
                        "id": p.sender.user.id,
                        "name": f"{p.sender.user.first_name} {p.sender.user.last_name}".strip(),
                        "phone": f"0{p.sender.user.username}",
                    }
                )
                if len(contacts) == LIMIT:
                    break

        return Response({"contacts": contacts}, status=status.HTTP_200_OK)

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
        if not package_id:
            return Response(
                {"error": "package_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        package = (
            Package.objects.select_related("sender__user", "receiver__user", "biker__user")
            .filter(id=package_id)
            .filter(
                Q(sender__user=request.user)
                | Q(receiver__user=request.user)
                | Q(biker__user=request.user)
            )
            .first()
        )
        if not package:
            return Response(
                {"error": f"Package not found for id {package_id}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        status_records = list(
            PackageStatus.objects.filter(package=package).order_by("updated_at")
        )
        latest_status = status_records[-1] if status_records else None

        status_map = {}
        for status_record in status_records:
            status_map.setdefault(status_record.status, status_record.updated_at)

        delivered_at = package.delivered_at or status_map.get("Delivered")
        collected_at = status_map.get("In Transit")
        cancelled_at = status_map.get("Cancelled")

        payload = {
            "package_id": package.id,
            "slug": package.slug,
            "status": latest_status.status if latest_status else "Pending",
            "status_updated_at": latest_status.updated_at if latest_status else None,
            "is_active": (latest_status.status if latest_status else "Pending")
            in self.ACTIVE_PACKAGE_STATUSES,
            "is_collected": collected_at is not None or delivered_at is not None,
            "collected_at": collected_at,
            "is_cancelled": cancelled_at is not None,
            "cancelled_at": cancelled_at,
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
        invoices_by_package_id = {
            invoice.package_id: invoice
            for invoice in Invoice.objects.filter(package_id__in=package_ids)
        }
        status_records_by_package_id = {}
        for status_record in PackageStatus.objects.filter(
            package_id__in=package_ids
        ).order_by("updated_at"):
            status_records_by_package_id.setdefault(status_record.package_id, []).append(
                status_record
            )

        response_data = [
            self.build_package_payload(
                package=package,
                invoice=invoices_by_package_id.get(package.id),
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

        package = Package.objects.filter(id=package_id).first()
        if not package:
            return Response(
                {"error": f"Package not found for id {package_id}"}, status=status.HTTP_404_NOT_FOUND
            )

        invoice = Invoice.objects.filter(package=package).first()
        status_records = list(
            PackageStatus.objects.filter(package=package).order_by("updated_at")
        )

        return Response(
            self.build_package_payload(package, invoice, status_records),
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

        if not is_valid_zimbabwean_number:
            return Response(
                {"error": f"Phone number format is incorrect: {counterpart_phone}"},
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
            exchange_rate=ExchangeRate.objects.last(),
        )

        self.send_receiver_sms(counterpart_phone, package, invoice)
        status_records = list(
            PackageStatus.objects.filter(package=package).order_by("updated_at")
        )

        return Response(
            self.build_package_payload(package, invoice, status_records),
            status=status.HTTP_201_CREATED,
        )

    def send_receiver_sms(self, phone_number, package, invoice):
        if not settings.TXTCONSOLE_SYSTEM_ID or not settings.TXTCONSOLE_PASSWORD:
            return Response(
                {"error": "SMS provider credentials are missing"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        address_char_len = 25

        # message to receiver
        if package.is_sender_initiated:
            address = package.dropoff_address
            if len(address) > address_char_len:
                address = address[:address_char_len] + "..."
            sender = package.sender.user
            sender_name = sender.first_name + " " + sender.last_name
            message = f"""Incoming package from {sender_name} to you @{address}. Collection OTP: {package.receiver_code}. Tracking No: {package.slug}."""
            if invoice.is_pay_forward:
                message = " ".join([message, f"Amount Due on Delivery: ${invoice.amount:.2f}"])
            else:
                message = " ".join([message, "Please be ready to receive your delivery."])
        else:
            address = package.pickup_address
            if len(address) > address_char_len:
                address = address[:address_char_len] + "..."
            receiver = package.receiver.user
            receiver_name = receiver.first_name + " " + receiver.last_name
            message = f"""A package for {receiver_name} has been booked from you @{address}. Collection OTP: {package.sender_code}. Tracking No: {package.slug}."""
            if not invoice.is_pay_forward:
                message = " ".join([message, f"Amount Due on Collection: ${invoice.amount:.2f}"])
            else:
                message = " ".join([message, "Please prepare the package for collection."])

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": "Basic "
            + base64.b64encode(
                f"{settings.TXTCONSOLE_SYSTEM_ID}:{settings.TXTCONSOLE_PASSWORD}".encode()
            ).decode(),
        }

        payload = {
            "destination": f"263{normalize_zimbabwean_number(phone_number)}",
            "text": message,
            "source": settings.TXTCONSOLE_SOURCE,
        }

        if settings.TXTCONSOLE_RECEIPT_URL:
            payload["receiptURL"] = settings.TXTCONSOLE_RECEIPT_URL

        try:
            provider_response = requests.post(
                settings.TXTCONSOLE_SMS_URL + "/sms",
                json=payload,
                headers=headers,
                timeout=20,
            )

            if provider_response.status_code >= 400:
                try:
                    error_details = provider_response.json()
                except ValueError:
                    error_details = {"message": provider_response.text}
                    logger.warning(
                        "txtConsole OTP send failed for package %s: %s",
                        package.slug,
                        error_details,
                    )
                    return Response(
                        {"error": "Failed to send OTP SMS"},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
        except requests.RequestException as exc:
            logger.exception(
                "txtConsole OTP send exception for package %s", package.slug
            )
            return Response(
                {"error": "SMS provider request failed"},
                status=status.HTTP_502_BAD_GATEWAY,
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
                first_name=first_name.capitalize(),
                last_name=last_name.capitalize(),
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

    def build_package_payload(self, package, invoice=None, status_records=None):
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

        serializer = PackageDetailSerializer(
            {
                "package_id": package.id,
                "slug": package.slug,
                "receiver_id": package.receiver.id,
                "receiver_name": f"{package.receiver.user.first_name} {package.receiver.user.last_name}".strip(),
                "sender_id": package.sender.id,
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
                "receiver_code": package.receiver_code,
                "sender_code": package.sender_code,
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
    @transaction.atomic
    def package_price(self, request):
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
            amount = math.ceil(amount)  # round up
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
                description=(
                    "Search by suburb name."
                ),
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
        city_id = request.query_params.get("city_id") or request.query_params.get("city")
        if not query:
            return Response(
                {"error": "query is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        normalized_query = query.lower()

        suburbs_qs = Suburb.objects.filter(name__icontains=query)
        if city_id:
            suburbs_qs = suburbs_qs.filter(city__id=city_id)

        suburbs = list(
            suburbs_qs.order_by("name").values("id", "name").distinct()
        )

        if len(query) > 2:
            SuburbSearchLog.objects.create(
                query=query,
                normalized_query=normalized_query,
                result_count=len(suburbs),
                had_results=bool(suburbs),
                user=request.user if request.user.is_authenticated else None,
            )

        return Response({"suburbs": suburbs}, status=status.HTTP_200_OK)
