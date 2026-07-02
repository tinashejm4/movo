import random
import string
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.users.models import City, Contact, Customer
from apps.bookkeeping.models import Account, IntracitySale
from .models import Biker, Package, PackageStatus, Invoice


def normalize_ecocash_phone(phone: str) -> str:
    return phone[:9]


class LocalPackageView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        package_id = request.query_params.get("package_id")
        if not package_id:
            return Response({"error": "package_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        package = get_object_or_404(
            Package.objects.select_related(
                "sender__user",
                "receiver__user",
                "city",
                "biker__user",
            ),
            id=package_id,
        )

        context = {
            "package_id": package.id,
            "slug": package.slug,
            "receiver_id": package.receiver.id,
            "receiver_name": f"{package.receiver.user.first_name} {package.receiver.user.last_name}".strip(),
            "sender_id": package.sender.id,
            "sender_name": f"{package.sender.user.first_name} {package.sender.user.last_name}".strip(),
            "pickup_location": package.pickup_location,
            "dropoff_location": package.dropoff_location,
            "city": package.city.name,
            "driver_id": package.biker.id if package.biker else None,
            "driver_name": (
                f"{package.biker.user.first_name} {package.biker.user.last_name}".strip()
                if package.biker
                else None
            ),
            "receiver_code": package.receiver_code,
            "comments": package.comments,
            "is_sender_initiated": package.is_sender_initiated,
            "assigned_at": package.assigned_at,
            "delivered_at": package.delivered_at,
            "added_at": package.added_at,
        }
        return Response(context, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request):
        data = request.data
        sender_phone = data.get("sender_phone")
        receiver_phone = data.get("receiver_phone")
        pickup_location = data.get("pickup_location")
        dropoff_location = data.get("dropoff_location")
        city_id = data.get("city_id")
        sender_name = data.get("sender_name")
        receiver_name = data.get("receiver_name")
        comments = data.get("comments")
        is_fast_delivery = data.get("is_fast_delivery", False)
        payment_method = (data.get("payment_method") or "cash").strip().lower()
        is_pay_forward = bool(data.get("is_pay_forward", False))
        invoice_amount = data.get("amount", 0)
        initiated_by = (data.get("initiated_by") or "user").strip().lower()
        biker_id = data.get("biker_id")

        required_fields = {
            "sender_phone": sender_phone,
            "receiver_phone": receiver_phone,
            "pickup_location": pickup_location,
            "dropoff_location": dropoff_location,
            "city_id": city_id,
        }
        missing_fields = [field for field, value in required_fields.items() if not value]
        if missing_fields:
            return Response(
                {"error": f"Missing required fields: {', '.join(missing_fields)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if initiated_by not in {"sender", "user"}:
            return Response(
                {"error": "initiated_by must be either 'sender' or 'user'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payment_method not in {"cash", "ecocash"}:
            return Response(
                {"error": "payment_method must be either 'cash' or 'ecocash'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invoice_amount = float(invoice_amount)
        except (TypeError, ValueError):
            return Response({"error": "amount must be numeric"}, status=status.HTTP_400_BAD_REQUEST)

        if invoice_amount < 0:
            return Response({"error": "amount must be zero or positive"}, status=status.HTTP_400_BAD_REQUEST)

        sender = self.resolve_customer(sender_phone, sender_name)
        receiver = self.resolve_customer(receiver_phone, receiver_name)
        city = get_object_or_404(City, id=city_id)
        biker = None
        if biker_id:
            biker = get_object_or_404(Biker, id=biker_id)

        package = Package.objects.create(
            sender=sender,
            receiver=receiver,
            is_sender_initiated=initiated_by == "sender",
            city=city,
            biker=biker,
            is_fast_delivery=is_fast_delivery,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            receiver_code=self.generate_code(),
            sender_code=self.generate_code(),
            comments=comments
        )

        package_status = PackageStatus.objects.create(package=package, status="Pending")
        invoice = Invoice.objects.create(
            package=package,
            amount=invoice_amount,
            payment_method=payment_method,
            is_pay_forward=is_pay_forward,
            is_paid=False,
        )

        return Response(
            {
                "message": "Package created successfully",
                "package": self.serialize_package(package),
            },
            status=status.HTTP_201_CREATED,
        )

class UserPackageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        latest_status = PackageStatus.objects.filter(package=OuterRef("pk")).order_by("-updated_at").values("status")[:1]

        packages = (
            Package.objects.select_related("sender__user", "receiver__user", "city", "biker__user")
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
                    "current_status": package.current_status or "Pending",
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

        return Response({"count": len(response_data), "results": response_data}, status=status.HTTP_200_OK)

    def resolve_customer(self, phone_number, full_name=None):
        CUSTOMER_DEFAULT_PASSWORD = "Pass@123"

        if User.objects.filter(username=phone_number).exists():
            user = User.objects.get(username=phone_number)
        else:
            first_name, last_name = self.split_name(full_name, phone_number)
            user = User.objects.create_user(
                username=phone_number,
                password=CUSTOMER_DEFAULT_PASSWORD,
                first_name=first_name,
                last_name=last_name,
            )

        Contact.objects.get_or_create(user=user, defaults={"phone_number": phone_number})
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

    def serialize_package(self, package):
        return {
            "id": package.id,
            "slug": package.slug,
            "sender_phone": package.sender.user.username,
            "receiver_phone": package.receiver.user.username,
            "pickup_location": package.pickup_location,
            "dropoff_location": package.dropoff_location,
            "city": package.city.name,
            "receiver_code": package.receiver_code,
            "comments": package.comments,
            "is_sender_initiated": package.is_sender_initiated,
            "assigned_at": package.assigned_at,
            "delivered_at": package.delivered_at,
            "added_at": package.added_at,
        }


class AssignPendingPackagesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        latest_status = PackageStatus.objects.filter(package=OuterRef("pk")).order_by("-updated_at").values("status")[:1]

        pending_packages = list(
            Package.objects.filter(biker__isnull=True)
            .annotate(current_status=Subquery(latest_status))
            .filter(current_status="Pending")
            .order_by("-is_fast_delivery", "added_at")
        )

        if not pending_packages:
            return Response(
                {
                    "message": "No pending packages available for assignment",
                    "assigned_count": 0,
                    "unassigned_count": 0,
                    "assigned_packages": [],
                },
                status=status.HTTP_200_OK,
            )

        free_bikers = []
        for biker in Biker.objects.select_related("user").order_by("id"):
            has_active_package = (
                Package.objects.filter(biker=biker)
                .annotate(current_status=Subquery(latest_status))
                .filter(current_status__in=["Pending", "In Transit"])
                .exists()
            )
            if not has_active_package:
                free_bikers.append(biker)

        if not free_bikers:
            return Response(
                {
                    "message": "No free riders available",
                    "assigned_count": 0,
                    "unassigned_count": len(pending_packages),
                    "assigned_packages": [],
                },
                status=status.HTTP_200_OK,
            )

        assignments = []
        for package, biker in zip(pending_packages, free_bikers):
            package.biker = biker
            package.assigned_at = timezone.now()
            package.save(update_fields=["biker", "assigned_at"])
            assignments.append(
                {
                    "package_id": package.id,
                    "is_fast_delivery": package.is_fast_delivery,
                    "assigned_biker_id": biker.id,
                    "assigned_biker_name": f"{biker.user.first_name} {biker.user.last_name}".strip(),
                    "assigned_at": package.assigned_at,
                    "added_at": package.added_at,
                }
            )

        return Response(
            {
                "message": "Pending packages assigned successfully",
                "assigned_count": len(assignments),
                "unassigned_count": len(pending_packages) - len(assignments),
                "assigned_packages": assignments,
            },
            status=status.HTTP_200_OK,
        )


class PickupVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        package_id = request.data.get("package_id")
        sender_code = (request.data.get("sender_code") or "").strip()

        if not package_id or not sender_code:
            return Response(
                {"error": "package_id and sender_code are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        package = get_object_or_404(Package.objects.select_related("biker__user"), id=package_id)
        if not package.biker:
            return Response(
                {"error": "Package has not been assigned to a biker yet"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.biker.user_id != request.user.id:
            return Response(
                {"error": "You are not assigned to this package"},
                status=status.HTTP_403_FORBIDDEN,
            )

        latest_status = PackageStatus.objects.filter(package=package).order_by("-updated_at").first()
        if latest_status and latest_status.status == "Delivered":
            return Response(
                {"error": "Package is already delivered"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.sender_code != sender_code:
            return Response(
                {"error": "Invalid sender code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sale_error = self.record_cash_sale(package, stage="pickup")
        if sale_error:
            return sale_error
        PackageStatus.objects.create(package=package, status="In Transit")

        return Response(
            {
                "message": "Package collected successfully",
                "package_id": package.id,
                "status": "In Transit",
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def record_cash_sale(package, stage):
        invoice = Invoice.objects.filter(package=package).first()
        if not invoice:
            return None

        if invoice.is_paid:
            return None

        # Pay-forward means payment is expected at dropoff; otherwise at pickup.
        if stage == "pickup" and invoice.is_pay_forward:
            return None
        if stage == "dropoff" and not invoice.is_pay_forward:
            return None

        account = Account.objects.filter(owner=package.biker.user).first()
        if not account:
            return Response({"error": "Account not found"}, status=status.HTTP_404_NOT_FOUND)

        IntracitySale.objects.get_or_create(
            invoice=invoice,
            defaults={
                "account": account,
                "amount": float(invoice.amount),
            },
        )

        invoice.is_paid = True
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["is_paid", "paid_at"])
        return None


class DropoffVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        package_id = request.data.get("package_id")
        receiver_code = (request.data.get("receiver_code") or "").strip()

        if not package_id or not receiver_code:
            return Response(
                {"error": "package_id and receiver_code are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        package = get_object_or_404(Package.objects.select_related("biker__user"), id=package_id)
        if not package.biker:
            return Response(
                {"error": "Package has not been assigned to a biker yet"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.biker.user_id != request.user.id:
            return Response(
                {"error": "You are not assigned to this package"},
                status=status.HTTP_403_FORBIDDEN,
            )

        latest_status = PackageStatus.objects.filter(package=package).order_by("-updated_at").first()
        if not latest_status or latest_status.status != "In Transit":
            return Response(
                {"error": "Package must be in transit before it can be delivered"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if latest_status.status == "Delivered":
            return Response(
                {"error": "Package is already delivered"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if package.receiver_code != receiver_code:
            return Response(
                {"error": "Invalid receiver code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sale_error = PickupVerificationView.record_cash_sale(package, stage="dropoff")
        if sale_error:
            return sale_error

        package.delivered_at = timezone.now()
        package.save(update_fields=["delivered_at"])
        PackageStatus.objects.create(package=package, status="Delivered")

        return Response(
            {
                "message": "Package delivered successfully",
                "package_id": package.id,
                "status": "Delivered",
                "delivered_at": package.delivered_at,
            },
            status=status.HTTP_200_OK,
        )


class CancelOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        package_id = request.data.get("package_id")
        if not package_id:
            return Response({"error": "package_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        package = get_object_or_404(Package.objects.select_related("sender__user", "receiver__user"), id=package_id)

        if request.user.id not in {package.sender.user_id, package.receiver.user_id}:
            return Response(
                {"error": "Only the sender or receiver can cancel this order"},
                status=status.HTTP_403_FORBIDDEN,
            )

        latest_status = PackageStatus.objects.filter(package=package).order_by("-updated_at").first()
        if not latest_status or latest_status.status != "Pending":
            return Response(
                {"error": "Order can only be cancelled when status is Pending"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PackageStatus.objects.create(package=package, status="Cancelled")

        return Response(
            {
                "message": "Order cancelled successfully",
                "package_id": package.id,
                "status": "Cancelled",
            },
            status=status.HTTP_200_OK,
        )

class EcocashPaymentView(APIView):
    # permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        package_id = request.data.get("package_id")
        phone_number = request.data.get("phone_number")
        if not package_id:
            return Response({"error": "package_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # package = get_object_or_404(Package.objects.select_related("sender__user", "receiver__user"), id=package_id)
        # invoice = get_object_or_404(Invoice, package=package)

        # if invoice.is_paid:
        #     return Response({"error": "This invoice has already been paid"}, status=status.HTTP_400_BAD_REQUEST)

        if not phone_number:
            return Response({"error": "phone_number is required for EcoCash payments"}, status=status.HTTP_400_BAD_REQUEST)

        if not settings.ECOCASH_AUTH_HEADER:
            return Response({"error": "EcoCash configuration is missing"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        normalized_phone = normalize_ecocash_phone(phone_number)
        external_id = ''.join(random.choices(string.digits, k=6))
        client_correlator = f"REF-{external_id}"
        reference_code = f"INV-{external_id}"

        payload = {
            "clientCorrelator": client_correlator,
            "referenceCode": reference_code,
            "tranType": "MER",
            "endUserId": normalized_phone,
            "paymentAmount": {
                "charginginformation": {
                    "amount": "1.00",
                    # "amount": f"{float(invoice.amount):.2f}",
                    "currency": "USD",
                    "description": "Intracity Payment"
                },
                "chargeMetaData": {
                    "channel": "WEB"
                }
            },
            "merchantCode": settings.ECOCASH_MERCHANT_CODE,
            "merchantPin": settings.ECOCASH_MERCHANT_PIN,
            "merchantNumber": settings.ECOCASH_MERCHANT_NUMBER,
            "countryCode": "ZW",
            "terminalID": settings.ECOCASH_TERMINAL_ID,
            "location": settings.ECOCASH_LOCATION,
            "superMerchantName": settings.ECOCASH_SUPER_MERCHANT_NAME,
            "merchantName": settings.ECOCASH_MERCHANT_NAME,
            "transactionOperationStatus": "Charged",
            "remarks": "Intracity Payment",
            "notifyUrl": settings.ECOCASH_NOTIFY_URL,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Basic c2J4XzU3OWY2NmQ0MWM0ZjpQYXNzQDEyMw==",
        }

        provider_response = None
        print(headers)
        print(settings.ECOCASH_PAYMENT_URL)
        print()
        req = Request(
            settings.ECOCASH_PAYMENT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
            )
        with urlopen(req, timeout=30) as response:
            provider_response = json.loads(response.read().decode("utf-8"))
        try:
            req = Request(
                settings.ECOCASH_PAYMENT_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urlopen(req, timeout=30) as response:
                provider_response = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
                provider_response = json.loads(error_body)
            except Exception:
                provider_response = {"error": str(exc), "reason": str(exc.reason)}
            return Response(
                {"error": "EcoCash request failed", "details": provider_response},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except URLError as exc:
            return Response(
                {"error": "EcoCash service unreachable", "details": str(exc.reason)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        operation_status = provider_response.get("transactionOperationStatus") or provider_response.get("transactionStatus")
        if not operation_status or operation_status.lower() != "charged":
            return Response(
                {
                    "error": "EcoCash payment not completed",
                    "provider_response": provider_response,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({})

        if not invoice.is_pay_forward:
            if not account_id:
                return Response(
                    {"error": "account_id is required to record sale for non-pay-forward invoices"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            account = Account.objects.filter(id=account_id).first()
            if not account:
                return Response({"error": "Account not found"}, status=status.HTTP_404_NOT_FOUND)

            IntracitySale.objects.get_or_create(
                invoice=invoice,
                defaults={
                    "account": account,
                    "amount": float(invoice.amount),
                },
            )

        invoice.is_paid = True
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["is_paid", "paid_at"])

        return Response(
            {
                "message": "EcoCash payment processed successfully",
                "invoice_id": invoice.id,
                "amount": float(invoice.amount),
                "provider_response": provider_response,
                "paid_at": invoice.paid_at,
            },
            status=status.HTTP_200_OK,
        )
