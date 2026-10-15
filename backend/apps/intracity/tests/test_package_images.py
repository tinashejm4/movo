from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import City, Customer

from ..models import Package, PackageImage


class PackageImageEndpointTests(APITestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        media_settings = override_settings(
            MEDIA_ROOT=self.media_dir.name,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            },
        )
        media_settings.enable()
        self.addCleanup(media_settings.disable)

        sender_user = User.objects.create_user(username="image-sender")
        receiver_user = User.objects.create_user(username="image-receiver")
        self.other_user = User.objects.create_user(username="image-outsider")
        sender = Customer.objects.create(user=sender_user)
        receiver = Customer.objects.create(user=receiver_user)
        city = City.objects.create(name="Harare", province="Harare", country="Zimbabwe")
        self.package = Package.objects.create(
            sender=sender,
            receiver=receiver,
            city=city,
            pickup_address="Avondale",
            dropoff_address="Borrowdale",
            sender_code="111111",
            receiver_code="222222",
        )
        self.url = reverse("intracity_package_images", args=[self.package.pk])
        self.client.force_authenticate(user=sender_user)

    def test_post_stores_original_bytes_and_get_lists_image(self):
        buffer = BytesIO()
        Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
        original = buffer.getvalue()
        upload = SimpleUploadedFile("parcel.png", original, content_type="image/png")

        created = self.client.post(self.url, {"image": upload}, format="multipart")

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        image = PackageImage.objects.get(package=self.package)
        with image.image.open("rb") as stored:
            self.assertEqual(stored.read(), original)
        self.assertEqual(created.data["id"], image.id)
        self.assertEqual(created.data["package"], self.package.id)

        listed = self.client.get(self.url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data["images"]), 1)
        self.assertEqual(listed.data["images"][0]["image"], image.image.url)

    def test_missing_upload_is_rejected(self):
        response = self.client.post(self.url, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PackageImage.objects.count(), 0)

    def test_unrelated_user_cannot_upload_or_list_images(self):
        self.client.force_authenticate(user=self.other_user)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.post(self.url, {}, format="multipart").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_only_get_and_post_are_available(self):
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.patch(self.url, {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
