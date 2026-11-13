from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.bookkeeping.models import Account, Asset, AssetImage, CapitalExpense, GeneralExpense, ExpenseAccount, LedgerEntry
from apps.users.models import Branch, Staff


class AssetsViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="asset-staff")
        branch = Branch.objects.create(name="Asset Branch", address="Main street")
        Staff.objects.create(user=self.user, branch=branch, position="Manager")
        self.account = Account.objects.create(name="Cash", currency="USD")
        self.expense_type = ExpenseAccount.objects.create(name="Equipment")
        self.url = reverse("admin_assets")
        self.client.force_authenticate(user=self.user)
        self.data = {
            "name": "Laptop",
            "asset_type": "equipment",
            "unique_identifier": "laptop-001",
            "supplier": "Supplier",
            "description": "Work laptop",
            "account_id": self.account.id,
            "expense_type_id": self.expense_type.id,
            "amount": "125.50",
        }

    def test_create_asset_posts_capital_expense_and_lists_it(self):
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        asset = Asset.objects.get(pk=response.data["asset_id"])
        expense = CapitalExpense.objects.get(pk=response.data["capital_expense_id"])
        self.assertEqual(expense.asset, asset)
        self.assertEqual(expense.added_by, self.user)
        self.assertEqual(expense.expense.added_by, self.user)
        self.assertEqual(expense.expense.ledger_entry.amount, Decimal("-125.50"))
        self.assertEqual(expense.expense.ledger_entry.running_balance, Decimal("-125.50"))
        self.assertEqual(expense.expense.description, "Laptop - laptop-001")
        self.assertEqual(expense.expense.ledger_entry.description, "Laptop - laptop-001")
        self.assertFalse(GeneralExpense.objects.filter(expense=expense.expense).exists())
        listing = self.client.get(self.url)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["assets"][0]["supplier"], "Supplier")
        self.assertEqual(listing.data["assets"][0]["capital_expenses"][0]["account"], "Cash")
        self.assertEqual(listing.data["assets"][0]["capital_expenses"][0]["currency"], "USD")
        self.assertEqual(listing.data["assets"][0]["capital_expenses"][0]["description"], "Laptop - laptop-001")

    def test_explicit_expense_description_remains_supported(self):
        response = self.client.post(self.url, {**self.data, "expense_description": "Purchase"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        expense = CapitalExpense.objects.get(pk=response.data["capital_expense_id"])
        self.assertEqual(expense.expense.description, "Purchase")

    def test_invalid_or_duplicate_requests_do_not_create_ledger_entries(self):
        for overrides in ({"amount": "0"}, {"account_id": 999999}, {"expense_type_id": 999999}, {"asset_type": "invalid"}):
            with self.subTest(overrides=overrides):
                response = self.client.post(self.url, {**self.data, **overrides}, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(Asset.objects.exists())
                self.assertFalse(LedgerEntry.objects.exists())
        self.assertEqual(self.client.post(self.url, self.data, format="json").status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.post(self.url, self.data, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Asset.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 1)

    def test_staff_authentication_required(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(user=User.objects.create_user(username="not-staff"))
        self.assertEqual(self.client.post(self.url, self.data, format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_asset_images_upload_list_and_full_view(self):
        asset = Asset.objects.create(name="Camera", asset_type="equipment", unique_identifier="camera-001")
        other = Asset.objects.create(name="Other", asset_type="other", unique_identifier="other-001")
        url = reverse("admin_asset_images", kwargs={"asset_id": asset.id})
        image_bytes = BytesIO()
        Image.new("RGB", (2, 2), "red").save(image_bytes, format="PNG")

        def image_file():
            return SimpleUploadedFile("image.png", image_bytes.getvalue(), content_type="image/png")

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.assertEqual(self.client.get(url).data["images"], [])
            invalid = SimpleUploadedFile("invalid.png", b"invalid", content_type="image/png")
            self.assertEqual(self.client.post(url, {"image": invalid}, format="multipart").status_code, 400)
            self.assertEqual(self.client.post(url, {}, format="multipart").status_code, 400)
            first = self.client.post(url, {"image": image_file()}, format="multipart")
            second = self.client.post(url, {"image": image_file()}, format="multipart")
            self.assertEqual(first.status_code, 201)
            self.assertEqual(second.status_code, 201)
            self.assertEqual(AssetImage.objects.filter(asset=asset).count(), 2)
            self.assertEqual(len(self.client.get(url).data["images"]), 2)
            image_url = reverse("admin_asset_image", kwargs={"asset_id": asset.id, "image_id": first.data["id"]})
            wrong_url = reverse("admin_asset_image", kwargs={"asset_id": other.id, "image_id": first.data["id"]})
            self.assertEqual(self.client.get(wrong_url).status_code, 404)
            response = self.client.get(image_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertEqual(b"".join(response.streaming_content), image_bytes.getvalue())
            self.client.force_authenticate(user=None)
            self.assertEqual(self.client.get(image_url).status_code, 401)
            self.assertEqual(self.client.post(url, {"image": image_file()}, format="multipart").status_code, 401)
