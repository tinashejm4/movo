from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Biker, City, Customer, Suburb

from .models import Package, PackageStatus
from .services.package_assignment import assign_pending_packages


class AutomaticPackageAssignmentTests(APITestCase):
    def setUp(self):
        self.city = City.objects.create(
            name="Harare",
            province="Harare",
            country="Zimbabwe",
        )
        self.pickup_area = Suburb.objects.create(
            city=self.city,
            name="Avondale",
            x_pos=0,
            y_pos=0,
        )
        self.dropoff_area = Suburb.objects.create(
            city=self.city,
            name="Borrowdale",
            x_pos=1,
            y_pos=1,
        )
        self.sender_user = User.objects.create_user(
            username="263771000001",
            password="pass",
            first_name="Sender",
        )
        self.sender = Customer.objects.create(user=self.sender_user)
        self.client.force_authenticate(user=self.sender_user)

    @patch(
        "apps.intracity.services.package_assignment._publish_assignments"
    )
    @patch(
        "apps.intracity.services.create_package.send_package_booking_sms"
    )
    @patch(
        "apps.intracity.services.create_package.assign_pending_packages_safely",
        side_effect=assign_pending_packages,
    )
    def test_create_package_assigns_available_biker_after_commit(
        self,
        automatic_assignment,
        _send_sms,
        publish_assignments,
    ):
        biker_user = User.objects.create_user(
            username="771000009",
            password="pass",
            first_name="Tendai",
            last_name="Moyo",
        )
        biker = Biker.objects.create(user=biker_user)

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                reverse("intracity_create_package"),
                {
                    "phone": "0771000002",
                    "name": "Receiver",
                    "pickup_location": "Avondale",
                    "pickup_area_id": self.pickup_area.id,
                    "dropoff_location": "Borrowdale",
                    "dropoff_area_id": self.dropoff_area.id,
                    "amount": "10.00",
                    "is_sender_initiated": True,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertGreaterEqual(len(callbacks), 1)
        automatic_assignment.assert_called_once_with()
        package = Package.objects.get(id=response.data["package_id"])
        self.assertEqual(package.biker_id, biker.id)
        self.assertIsNotNone(package.assigned_at)
        publish_assignments.assert_called_once()
        payloads = publish_assignments.call_args.args[0]
        self.assertEqual(payloads[0]["package_id"], package.id)
        self.assertEqual(payloads[0]["biker_id"], biker.id)

    @patch(
        "apps.intracity.services.package_assignment._publish_assignments"
    )
    def test_dispatch_leaves_package_pending_when_no_biker_is_available(
        self,
        publish_assignments,
    ):
        receiver_user = User.objects.create_user(
            username="263771000002",
            password="pass",
        )
        receiver = Customer.objects.create(user=receiver_user)
        package = Package.objects.create(
            sender=self.sender,
            receiver=receiver,
            city=self.city,
            pickup_area=self.pickup_area,
            pickup_address="Avondale",
            dropoff_area=self.dropoff_area,
            dropoff_address="Borrowdale",
            sender_code="111111",
            receiver_code="222222",
        )
        PackageStatus.objects.create(package=package, status="Pending")

        result = assign_pending_packages()

        package.refresh_from_db()
        self.assertIsNone(package.biker_id)
        self.assertEqual(result["assigned_count"], 0)
        self.assertEqual(result["unassigned_count"], 1)
        publish_assignments.assert_not_called()
