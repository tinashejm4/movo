from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Biker, City, Contact, Customer

from ..models import Invoice, Package, PackageStatus


class IntracityPackageListTests(APITestCase):
    def setUp(self):
        self.city = City.objects.create(
            name="Harare", province="Harare", country="Zimbabwe"
        )
        self.sender_user = User.objects.create_user(
            username="0779000011", password="pass"
        )
        self.receiver_user = User.objects.create_user(
            username="0779000012", password="pass"
        )
        self.driver_user = User.objects.create_user(
            username="rider-with-number",
            password="pass",
            first_name="Rider",
            last_name="One",
        )
        self.sender = Customer.objects.create(user=self.sender_user)
        self.receiver = Customer.objects.create(user=self.receiver_user)
        self.driver = Biker.objects.create(user=self.driver_user)
        Contact.objects.create(user=self.driver_user, phone_number="0779000013")
        self.client.force_authenticate(user=self.sender_user)

    def test_package_list_returns_compact_payload_shape(self):
        package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=self.city,
            biker=self.driver,
            pickup_address="Avondale",
            dropoff_address="Borrowdale",
            sender_code="111111",
            receiver_code="222222",
        )
        PackageStatus.objects.create(package=package, status="Pending")

        response = self.client.get(reverse("intracity_package_list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data["results"][0]
        self.assertEqual(result["package_id"], package.id)
        self.assertEqual(result["initiator_id"], self.sender.user_id)
        self.assertEqual(result["slug"], package.slug)
        self.assertEqual(result["pickup_address"], "Avondale")
        self.assertEqual(result["dropoff_address"], "Borrowdale")
        self.assertFalse(result["is_incoming"])
        self.assertNotIn("incoming", result)
        self.assertIn("package_created_at", result)
        self.assertIn("collected_at", result)
        self.assertIn("delivered_at", result)
        self.assertNotIn("driver_number", result)
        self.assertNotIn("can_cancel", result)

    def test_package_list_direction_is_relative_to_requesting_user(self):
        package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=self.city,
            biker=self.driver,
            pickup_address="Avondale",
            dropoff_address="Borrowdale",
            sender_code="111111",
            receiver_code="222222",
            is_sender_initiated=False,
        )
        PackageStatus.objects.create(package=package, status="Pending")

        self.client.force_authenticate(user=self.receiver_user)
        response = self.client.get(reverse("intracity_package_list"))
        self.assertTrue(response.data["results"][0]["is_incoming"])

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(reverse("intracity_package_list"))
        self.assertIsNone(response.data["results"][0]["is_incoming"])

    def test_self_send_is_incoming_in_package_list(self):
        package = Package.objects.create(
            sender=self.sender,
            receiver=self.sender,
            city=self.city,
            pickup_address="Avondale",
            dropoff_address="Avondale",
            sender_code="333333",
            receiver_code="444444",
        )
        PackageStatus.objects.create(package=package, status="Pending")

        response = self.client.get(reverse("intracity_package_list"))

        self.assertTrue(response.data["results"][0]["is_incoming"])

    def test_package_status_includes_assigned_driver_number(self):
        package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=self.city,
            biker=self.driver,
            pickup_address="Avondale",
            dropoff_address="Borrowdale",
            sender_code="111111",
            receiver_code="222222",
        )
        PackageStatus.objects.create(package=package, status="Pending")

        response = self.client.get(
            reverse("intracity_package_status"),
            {"package_id": package.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["driver_number"], "0779000013")

    def test_package_status_includes_can_cancel(self):
        package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=self.city,
            pickup_address="Avondale",
            dropoff_address="Borrowdale",
            sender_code="555555",
            receiver_code="666666",
        )
        PackageStatus.objects.create(package=package, status="Pending")
        Invoice.objects.create(package=package, amount="10.00")

        response = self.client.get(
            reverse("intracity_package_status"),
            {"package_id": package.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["can_cancel"])

    def test_package_detail_returns_initiating_user_id(self):
        package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=self.city,
            pickup_address="Avondale",
            dropoff_address="Borrowdale",
            sender_code="555555",
            receiver_code="666666",
        )
        PackageStatus.objects.create(package=package, status="Pending")

        response = self.client.get(
            reverse("intracity_package_detail"),
            {"package_id": package.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["initiator_id"], self.sender.user_id)

        package.is_sender_initiated = False
        package.save(update_fields=["is_sender_initiated"])
        response = self.client.get(
            reverse("intracity_package_detail"),
            {"package_id": package.id},
        )
        self.assertEqual(response.data["initiator_id"], self.receiver.user_id)

    def test_package_detail_returns_only_sender_confirmation_code_to_sender(self):
        package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=self.city,
            pickup_address="Avondale",
            dropoff_address="Borrowdale",
            sender_code="123456",
            receiver_code="654321",
        )
        PackageStatus.objects.create(package=package, status="Pending")

        response = self.client.get(
            reverse("intracity_package_detail"),
            {"package_id": package.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["confirmation_code"], "123456")
        self.assertNotIn("sender_code", response.data)
        self.assertNotIn("receiver_code", response.data)

    def test_package_detail_returns_only_receiver_confirmation_code_to_receiver(self):
        package = Package.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            city=self.city,
            pickup_address="Avondale",
            dropoff_address="Borrowdale",
            sender_code="123456",
            receiver_code="654321",
        )
        PackageStatus.objects.create(package=package, status="Pending")
        self.client.force_authenticate(user=self.receiver.user)

        response = self.client.get(
            reverse("intracity_package_detail"),
            {"package_id": package.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["confirmation_code"], "654321")
        self.assertNotIn("sender_code", response.data)
        self.assertNotIn("receiver_code", response.data)


class IntracityPaidPackageCancellationTests(APITestCase):
    def setUp(self):
        city = City.objects.create(
            name="Bulawayo", province="Bulawayo", country="Zimbabwe"
        )
        sender_user = User.objects.create_user(
            username="0779000021", password="pass"
        )
        receiver_user = User.objects.create_user(
            username="0779000022", password="pass"
        )
        sender = Customer.objects.create(user=sender_user)
        receiver = Customer.objects.create(user=receiver_user)
        self.package = Package.objects.create(
            sender=sender,
            receiver=receiver,
            city=city,
            pickup_address="Hillside",
            dropoff_address="Suburbs",
            sender_code="777777",
            receiver_code="888888",
        )
        PackageStatus.objects.create(package=self.package, status="Pending")
        Invoice.objects.create(
            package=self.package,
            amount="10.00",
            is_paid=True,
        )
        self.client.force_authenticate(user=sender_user)

    def test_paid_pending_package_cannot_be_cancelled(self):
        response = self.client.post(
            reverse("intracity_cancel_order"),
            {"package_id": self.package.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Paid orders cannot be cancelled")
        self.assertEqual(
            PackageStatus.objects.filter(package=self.package).count(),
            1,
        )
