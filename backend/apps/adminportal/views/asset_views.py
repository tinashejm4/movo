from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookkeeping.models import Account, Asset, AssetImage, CapitalExpense, Expense, ExpenseAccount
from apps.users.permissions import IsStaff


class AssetCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    asset_type = serializers.ChoiceField(choices=Asset.ASSET_TYPES)
    unique_identifier = serializers.CharField(max_length=100)
    supplier = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    account_id = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all(), source="account")
    expense_type_id = serializers.PrimaryKeyRelatedField(queryset=ExpenseAccount.objects.all(), source="expense_type")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    expense_description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_unique_identifier(self, value):
        if Asset.objects.filter(unique_identifier=value).exists():
            raise serializers.ValidationError("An asset with this identifier already exists.")
        return value


class AssetsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        expenses = CapitalExpense.objects.select_related(
            "expense__account", "expense__expense_type", "expense__added_by"
        ).order_by("-expense__actual_date", "-id")
        assets = Asset.objects.prefetch_related(Prefetch("capital_expenses", queryset=expenses)).order_by("-added_at", "-id")
        return Response({"assets": [{
            "id": asset.id,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "unique_identifier": asset.unique_identifier,
            "supplier": asset.supplier,
            "description": asset.description,
            "added_at": asset.added_at,
            "capital_expenses": [{
                "id": capital.id,
                "account": capital.expense.account.name,
                "currency": capital.expense.account.currency,
                "expense_type": capital.expense.expense_type.name,
                "amount": capital.expense.amount,
                "supplier": capital.expense.supplier,
                "description": capital.expense.description,
                "actual_date": capital.expense.actual_date,
                "added_by": capital.expense.added_by.username if capital.expense.added_by else None,
                "is_reversed": capital.expense.is_reversed,
            } for capital in asset.capital_expenses.all()],
        } for asset in assets]})

    def post(self, request):
        serializer = AssetCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "; ".join(
                f"{field}: {', '.join(str(message) for message in messages)}"
                for field, messages in serializer.errors.items()
            )}, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                asset = Asset.objects.create(
                    name=data["name"],
                    asset_type=data["asset_type"],
                    unique_identifier=data["unique_identifier"],
                    supplier=data["supplier"],
                    description=data["description"],
                )
                expense = Expense.objects.create(
                    account=data["account"],
                    expense_type=data["expense_type"],
                    amount=data["amount"],
                    supplier=data["supplier"],
                    description=data["expense_description"] or f'{asset.name} - {asset.unique_identifier}',
                    added_by=request.user,
                )
                capital = CapitalExpense.objects.create(asset=asset, expense=expense, added_by=request.user)
        except IntegrityError:
            if Asset.objects.filter(unique_identifier=data["unique_identifier"]).exists():
                return Response({"error": "An asset with this identifier already exists."}, status=status.HTTP_409_CONFLICT)
            raise
        return Response({"asset_id": asset.id, "capital_expense_id": capital.id}, status=status.HTTP_201_CREATED)


class AssetImagesView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, asset_id):
        asset = get_object_or_404(Asset, pk=asset_id)
        images = asset.images.order_by("-added_at", "-id").values("id", "added_at")
        return Response({"images": list(images)})

    def post(self, request, asset_id):
        asset = get_object_or_404(Asset, pk=asset_id)
        image = request.FILES.get("image")
        if not image:
            return Response({"error": "Select an image to upload."}, status=status.HTTP_400_BAD_REQUEST)
        if image.size > 10 * 1024 * 1024:
            return Response({"error": "Image must be 10 MB or smaller."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            image = serializers.ImageField().run_validation(image)
        except serializers.ValidationError as error:
            return Response({"error": str(error.detail[0])}, status=status.HTTP_400_BAD_REQUEST)
        if image.image.format not in {"JPEG", "PNG", "GIF", "WEBP"}:
            return Response({"error": "Use a JPEG, PNG, GIF or WebP image."}, status=status.HTTP_400_BAD_REQUEST)
        asset_image = AssetImage.objects.create(asset=asset, image=image)
        return Response({"id": asset_image.id, "added_at": asset_image.added_at}, status=status.HTTP_201_CREATED)


class AssetImageContentView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, asset_id, image_id):
        record = get_object_or_404(AssetImage, pk=image_id, asset_id=asset_id)
        try:
            image = record.image.open("rb")
        except FileNotFoundError:
            return Response({"error": "Image file not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            with Image.open(image) as decoded:
                content_type = Image.MIME.get(decoded.format)
                decoded.verify()
            if content_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
                image.close()
                return Response({"error": "Unsupported image format."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
            image.seek(0)
        except (UnidentifiedImageError, OSError, ValueError):
            image.close()
            return Response({"error": "Unable to read image."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        response = FileResponse(image, content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        return response
