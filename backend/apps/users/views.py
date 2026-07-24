import secrets
import requests, base64
import logging
from django.utils import timezone
from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from apps.users.permissions import IsStaff
from apps.users.serializers import (
    CitySerializer,
    SuburbSerializer,
    CustomerProfilePatchRequestSerializer,
    CustomerProfileResponseSerializer,
    ErrorResponseSerializer,
    CustomerRegisterLoginRequestSerializer,
    OTPCreateRequestSerializer,
    OTPCreateResponseSerializer,
    StaffLoginRequestSerializer,
    StaffProfileResponseSerializer,
    TokenPairResponseSerializer,
    TokenRefreshRequestSerializer,
    TokenRefreshResponseSerializer,
)
from .models import OTP, City, Contact, Customer, Staff, Suburb
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from apps.users.utils import normalize_zimbabwean_number
from .utils import is_valid_zimbabwean_number

logger = logging.getLogger(__name__)


CUSTOMER_DEFAULT_PASSWORD = "Pass@123"


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer
    permission_classes = [IsAuthenticated]


class SuburbViewSet(viewsets.ModelViewSet):
    queryset = Suburb.objects.all()
    serializer_class = SuburbSerializer
    permission_classes = [IsAuthenticated]


class StaffProfileView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @extend_schema(
        tags=["Users"],
        responses={
            200: StaffProfileResponseSerializer,
            404: OpenApiResponse(
                ErrorResponseSerializer, description="Staff profile not found"
            ),
        },
    )
    def get(self, request):
        try:
            staff = Staff.objects.select_related("branch").get(user=request.user)
        except Staff.DoesNotExist:
            return Response(
                {"error": "Staff profile not found"}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {
                "staff_id": staff.id,
                "branch_id": staff.branch_id,
                "branch_name": staff.branch.name,
            },
            status=status.HTTP_200_OK,
        )


class StaffLoginView(APIView):
    authentication_classes = []

    @extend_schema(
        tags=["Users"],
        request=StaffLoginRequestSerializer,
        responses={
            200: TokenPairResponseSerializer,
            401: OpenApiResponse(
                ErrorResponseSerializer, description="Invalid credentials"
            ),
            403: OpenApiResponse(ErrorResponseSerializer, description="Inactive user"),
        },
    )
    def post(self, request):
        data = request.data
        username = data.get("username")
        password = data.get("password")
        user = authenticate(username=username, password=password)
        if not user:
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )
        if not user.is_active:
            return Response(
                {
                    "error": "User is locked out because all branch accounts were closed for the day."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "username": user.username,
            }
        )


class TokenRefreshView(SimpleJWTTokenRefreshView):
    """Refresh access tokens using a valid refresh token."""

    authentication_classes = []

    @extend_schema(
        tags=["Users"],
        request=TokenRefreshRequestSerializer,
        responses={
            200: TokenRefreshResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Missing or invalid refresh token"
            ),
            401: OpenApiResponse(
                ErrorResponseSerializer, description="User not found for this token"
            ),
            403: OpenApiResponse(ErrorResponseSerializer, description="Inactive user"),
        },
    )
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "refresh token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
        except TokenError:
            # Let SimpleJWT generate the standard invalid token response shape.
            return super().post(request, *args, **kwargs)

        user_id_claim = api_settings.USER_ID_CLAIM
        user_id = token.get(user_id_claim)
        if not user_id:
            return super().post(request, *args, **kwargs)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found for this token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {
                    "error": "User is locked out because all branch accounts were closed for the day."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().post(request, *args, **kwargs)


class OTPCreateView(APIView):
    authentication_classes = []

    @extend_schema(
        tags=["Users"],
        request=OTPCreateRequestSerializer,
        responses={
            201: OTPCreateResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Phone number is required"
            ),
        },
    )
    def post(self, request):
        data = request.data
        username = data.get("phone_number")

        if not username:
            return Response(
                {"error": "Phone number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not is_valid_zimbabwean_number(username):
            return Response(
                {"error": "Invalid Zimbabwean phone number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate a 6-digit OTP.
        otp_code = f"{secrets.randbelow(1_000_000):06d}"

        # Create or update the OTP for the given username
        otp, _created = OTP.objects.update_or_create(
            username=normalize_zimbabwean_number(username),
            defaults={"otp_code": otp_code},
        )

        if not settings.TXTCONSOLE_SYSTEM_ID or not settings.TXTCONSOLE_PASSWORD:
            return Response(
                {"error": "SMS provider credentials are missing"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": "Basic "
            + base64.b64encode(
                f"{settings.TXTCONSOLE_SYSTEM_ID}:{settings.TXTCONSOLE_PASSWORD}".encode()
            ).decode(),
        }

        payload = {
            "destination": f"263{normalize_zimbabwean_number(username)}",
            "text": f"Your Movo OTP is {otp_code}. It expires in 5 minutes.",
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
                    "txtConsole OTP send failed for %s: %s",
                    username,
                    error_details,
                )
                return Response(
                    {"error": "Failed to send OTP SMS"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
        except requests.RequestException as exc:
            logger.exception("txtConsole OTP send exception for %s", username)
            return Response(
                {"error": "SMS provider request failed"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"otp": otp_code}, status=status.HTTP_201_CREATED)


class CustomerRegisterLoginView(APIView):
    authentication_classes = []

    @extend_schema(
        tags=["Users"],
        request=CustomerRegisterLoginRequestSerializer,
        responses={
            200: TokenPairResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer, description="Missing, invalid, or expired OTP"
            ),
        },
    )
    def post(self, request):
        # Customer registration/login will be done through phone and an OTP will be sent to the phone
        # number for verification. the otp will be sent together with the phone number and the name of the customer.
        # If the customer already exists, the customer will be instantly logged in.
        data = request.data
        username = data.get("phone_number")
        otp_code = data.get("otp_code")
        is_profile_complete = False
        username = normalize_zimbabwean_number(username)

        print(
            f"Received request with phone_number: {username} and otp_code: {otp_code}"
        )  # Debugging line

        if not username or not otp_code:
            return Response(
                {"error": "phone_number and otp_code are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            otp = OTP.objects.get(username=username, otp_code=otp_code)
        except OTP.DoesNotExist:
            return Response(
                {"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST
            )

        if timezone.now() > otp.expiry_time:
            return Response(
                {"error": "OTP has expired"}, status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username=username).exists():
            user = authenticate(username=username, password=CUSTOMER_DEFAULT_PASSWORD)
            refresh = RefreshToken.for_user(user)

            if not user.first_name or not user.last_name:
                is_profile_complete = False
            else:
                is_profile_complete = True

            return Response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "username": user.username,
                    "is_profile_complete": is_profile_complete,
                }
            )

        user = User.objects.create_user(
            username=username, password=CUSTOMER_DEFAULT_PASSWORD
        )
        Customer.objects.create(user=user)
        Contact.objects.create(user=user, phone_number=username)
        otp.delete()

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "username": user.username,
                "is_profile_complete": is_profile_complete,
            }
        )


class CustomerProfileView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Customer.objects.select_related("user").all()
    serializer_class = CustomerProfileResponseSerializer

    def get_object(self):
        return Customer.objects.get(user=self.request.user)

    @extend_schema(
        tags=["Users"],
        responses={
            200: CustomerProfileResponseSerializer,
            404: OpenApiResponse(
                ErrorResponseSerializer, description="Customer profile not found"
            ),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        try:
            customer = self.get_object()
        except Customer.DoesNotExist:
            return Response(
                {"error": "Customer profile not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = customer.user
        phone_number = ""
        if hasattr(user, "contact") and user.contact:
            phone_number = user.contact.phone_number or ""

        return Response(
            {
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "phone_number": phone_number,
                "is_profile_complete": bool(user.first_name and user.last_name),
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Users"],
        request=CustomerProfilePatchRequestSerializer,
        responses={
            200: CustomerProfileResponseSerializer,
            400: OpenApiResponse(
                ErrorResponseSerializer,
                description="Missing required name fields or profile already completed",
            ),
            404: OpenApiResponse(
                ErrorResponseSerializer, description="Customer profile not found"
            ),
        },
    )
    def partial_update(self, request, *args, **kwargs):
        try:
            customer = self.get_object()
        except Customer.DoesNotExist:
            return Response(
                {"error": "Customer profile not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = customer.user
        missing_fields = [
            field for field in ["first_name", "last_name"] if not getattr(user, field)
        ]
        if not missing_fields:
            return Response(
                {"error": "Profile name is already complete"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updates = {}
        for field in missing_fields:
            value = request.data.get(field)
            if value is None or not str(value).strip():
                return Response(
                    {"error": f"{field} is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            updates[field] = str(value).strip().capitalize()

        for field, value in updates.items():
            setattr(user, field, value)
        user.save(update_fields=list(updates.keys()))

        phone_number = ""
        if hasattr(user, "contact") and user.contact:
            phone_number = user.contact.phone_number or ""

        return Response(
            {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone_number": phone_number,
                "is_profile_complete": bool(user.first_name and user.last_name),
            },
            status=status.HTTP_200_OK,
        )
