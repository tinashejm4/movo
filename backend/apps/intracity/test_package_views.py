from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Biker, City, Contact, Customer

from .models import Package, PackageStatus


class IntracityPackageListTests(APITestCase):
    def setUp(self):
        self.city = City.objects.create(
            name="Harare", province="Harare", country="Zimbabwe"
        )
        sender_user = User.objects.create_user(
            username="0779000011", password="pass"
        )
        receiver_user = User.objects.create_user(
            username="0779000012", password="pass"
        )
        driver_user = User.objects.create_user(
            username="rider-with-number",
            password="pass",
            first_name="Rider",
            last_name="One",
        )
        self.sender = Customer.objects.create(user=sender_user)
        self.receiver = Customer.objects.create(user=receiver_user)
        self.driver = Biker.objects.create(user=driver_user)
        Contact.objects.create(user=driver_user, phone_number="0779000013")
        self.client.force_authenticate(user=sender_user)

    def test_packages_include_assigned_driver_number(self):
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
        self.assertEqual(response.data["results"][0]["driver_number"], "0779000013")

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
