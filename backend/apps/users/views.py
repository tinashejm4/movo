import datetime
import secrets
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.users.permissions import IsStaff
from .models import OTP, Contact, Customer, Staff
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView
from django.contrib.auth.models import User
from django.contrib.auth import authenticate


CUSTOMER_DEFAULT_PASSWORD = "Pass@123"


class StaffProfileView(APIView):
	permission_classes = [IsAuthenticated, IsStaff]

	def get(self, request):
		try:
			staff = Staff.objects.select_related("branch").get(user=request.user)
		except Staff.DoesNotExist:
			return Response({"error": "Staff profile not found"}, status=status.HTTP_404_NOT_FOUND)

		return Response(
			{
				"staff_id": staff.id,
				"branch_id": staff.branch_id,
				"branch_name": staff.branch.name,
			},
			status=status.HTTP_200_OK,
		)
	
class StaffLoginView(APIView):

	def post(self, request):
		data = request.data
		username = data.get("username")
		password = data.get("password")
		user = authenticate(username=username, password=password)
		if not user:
			return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
		if not user.is_active:
			return Response(
				{"error": "User is locked out because all branch accounts were closed for the day."},
				status=status.HTTP_403_FORBIDDEN,
			)
        
		# Generate JWT tokens
		refresh = RefreshToken.for_user(user)
		return Response({
			"access": str(refresh.access_token),
			"refresh": str(refresh),
			"username": user.username,
		})


class TokenRefreshView(SimpleJWTTokenRefreshView):
	"""Refresh access tokens using a valid refresh token."""

	def post(self, request, *args, **kwargs):
		refresh_token = request.data.get("refresh")
		if not refresh_token:
			return Response({"error": "refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

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
			return Response({"error": "User not found for this token"}, status=status.HTTP_401_UNAUTHORIZED)

		if not user.is_active:
			return Response(
				{"error": "User is locked out because all branch accounts were closed for the day."},
				status=status.HTTP_403_FORBIDDEN,
			)

		return super().post(request, *args, **kwargs)

class OTPCreateView(APIView):

	def post(self, request):
		data = request.data
		username = data.get("phone_number")

		if not username:
			return Response({"error": "Phone number is required"}, status=status.HTTP_400_BAD_REQUEST)

		# Generate a 6-digit OTP.
		otp_code = f"{secrets.randbelow(1_000_000):06d}"

		# Create or update the OTP for the given username
		otp, created = OTP.objects.update_or_create(
			username=username,
			defaults={"otp_code": otp_code},
		)

		#Send the OTP to the user's phone number using your preferred method (e.g., SMS gateway, email, etc.)
		print(f"Sending OTP {otp_code} to phone number {username}")  # Replace this with actual sending logic
		return Response({"otp": otp_code}, status=status.HTTP_201_CREATED)

class CustomerRegisterLoginView(APIView):

	def post(self, request):
		# Customer registration/login will be done through phone and an OTP will be sent to the phone 
		# number for verification. the otp will be sent together with the phone number and the name of the customer. 
		# If the customer already exists, the login view will be called instead.
		data = request.data
		username = data.get("phone_number")
		otp_code = data.get("otp_code")

		if not username or not otp_code:
			return Response({"error": "phone_number and otp_code are required"}, status=status.HTTP_400_BAD_REQUEST)

		try:
			otp = OTP.objects.get(username=username, otp_code=otp_code)
		except OTP.DoesNotExist:
			return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

		if timezone.now() > otp.expiry_time:
			return Response({"error": "OTP has expired"}, status=status.HTTP_400_BAD_REQUEST)

		if User.objects.filter(username=username).exists():
			user = authenticate(username=username, password=CUSTOMER_DEFAULT_PASSWORD)
			refresh = RefreshToken.for_user(user)
			return Response({
				"access": str(refresh.access_token),
				"refresh": str(refresh),
				"username": user.username,
			})

		user = User.objects.create_user(username=username, password=CUSTOMER_DEFAULT_PASSWORD)
		Customer.objects.create(user=user)
		Contact.objects.create(user=user, phone_number=username)
		otp.delete()

		# Generate JWT tokens
		refresh = RefreshToken.for_user(user)
		return Response({
			"access": str(refresh.access_token),
			"refresh": str(refresh),
			"username": user.username,
		})
