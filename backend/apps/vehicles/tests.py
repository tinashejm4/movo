from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import Biker, Branch, Staff
from .models import MileageRecord, Vehicle, VehicleAssignment


class VehicleAssignmentByVehicleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Main", address="Harare")
        self.staff_user = User.objects.create_user(username="staff", password="test")
        Staff.objects.create(user=self.staff_user, branch=self.branch, position="Manager")
        self.biker_user = User.objects.create_user(username="driver", password="test")
        self.biker = Biker.objects.create(user=self.biker_user, branch=self.branch)
        self.vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="ABC 1234",
            make="Honda",
            model="XR150",
        )

    def make_mileage(self, source, odometer, recorded_at):
        return MileageRecord.objects.create(
            vehicle=self.vehicle,
            odometer_km=odometer,
            recorded_at=recorded_at,
            source=source,
            recorded_by=self.staff_user,
        )

    def test_returns_only_the_active_assignment_for_vehicle(self):
        now = timezone.now()
        start = self.make_mileage(MileageRecord.Source.ASSIGNMENT_START, 10, now - timedelta(days=2))
        release = self.make_mileage(MileageRecord.Source.ASSIGNMENT_RELEASE, 20, now - timedelta(days=1))
        VehicleAssignment.objects.create(
            vehicle=self.vehicle,
            driver=self.biker,
            assigned_at=now - timedelta(days=2),
            start_mileage_record=start,
            released_at=now - timedelta(days=1),
            release_mileage_record=release,
        )
        active_start = self.make_mileage(MileageRecord.Source.ASSIGNMENT_START, 21, now)
        active = VehicleAssignment.objects.create(
            vehicle=self.vehicle,
            driver=self.biker,
            assigned_at=now,
            start_mileage_record=active_start,
        )
        self.client.force_authenticate(self.staff_user)

        response = self.client.get(f"/api/vehicles/assignments/by-vehicle/{self.vehicle.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], active.pk)

    def test_returns_not_found_when_vehicle_has_no_active_assignment(self):
        self.client.force_authenticate(self.staff_user)

        response = self.client.get(f"/api/vehicles/assignments/by-vehicle/{self.vehicle.pk}/")

        self.assertEqual(response.status_code, 404)

    def test_requires_staff_authentication(self):
        response = self.client.get(f"/api/vehicles/assignments/by-vehicle/{self.vehicle.pk}/")
        self.assertEqual(response.status_code, 401)

        regular_user = User.objects.create_user(username="customer", password="test")
        self.client.force_authenticate(regular_user)
        response = self.client.get(f"/api/vehicles/assignments/by-vehicle/{self.vehicle.pk}/")
        self.assertEqual(response.status_code, 403)


class VehicleAssignmentWriteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Main", address="Harare")
        self.staff_user = User.objects.create_user(username="fleet-staff", password="test")
        Staff.objects.create(user=self.staff_user, branch=self.branch, position="Manager")
        self.driver = self.create_driver("driver-one")
        self.next_driver = self.create_driver("driver-two")
        self.vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="XYZ 9876",
            make="Honda",
            model="XR150",
        )
        self.client.force_authenticate(self.staff_user)

    def create_driver(self, username):
        user = User.objects.create_user(username=username, password="test")
        return Biker.objects.create(user=user)

    def create_start_record(self, odometer, recorded_at=None):
        return MileageRecord.objects.create(
            vehicle=self.vehicle,
            odometer_km=odometer,
            recorded_at=recorded_at or timezone.now() - timedelta(minutes=1),
            source=MileageRecord.Source.ASSIGNMENT_START,
            recorded_by=self.staff_user,
        )

    def create_active_assignment(self, driver=None, odometer=100):
        assigned_at = timezone.now() - timedelta(minutes=1)
        start_record = self.create_start_record(odometer, assigned_at)
        return VehicleAssignment.objects.create(
            vehicle=self.vehicle,
            driver=driver or self.driver,
            assigned_at=assigned_at,
            start_mileage_record=start_record,
            assigned_by=self.staff_user,
        )

    def test_create_atomically_creates_assignment_start_mileage(self):
        assigned_at = timezone.now()
        response = self.client.post(
            "/api/vehicles/assignments/",
            {
                "vehicle": self.vehicle.pk,
                "driver": self.driver.pk,
                "assigned_at": assigned_at.isoformat(),
                "start_mileage_km": 27,
                "handover_notes": "Helmet issued.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        assignment = VehicleAssignment.objects.get(pk=response.data["id"])
        start_record = assignment.start_mileage_record
        self.assertEqual(start_record.odometer_km, 27)
        self.assertEqual(start_record.source, MileageRecord.Source.ASSIGNMENT_START)
        self.assertEqual(start_record.vehicle_id, self.vehicle.pk)
        self.assertEqual(start_record.recorded_by_id, self.staff_user.pk)
        self.assertEqual(assignment.handover_notes, "Helmet issued.")

    def test_create_keeps_existing_mileage_record_payload_compatible(self):
        assigned_at = timezone.now()
        start_record = self.create_start_record(27, assigned_at)
        response = self.client.post(
            "/api/vehicles/assignments/",
            {
                "vehicle": self.vehicle.pk,
                "driver": self.driver.pk,
                "assigned_at": assigned_at.isoformat(),
                "start_mileage_record": start_record.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["start_mileage_record"], start_record.pk)

    def test_create_rejects_driver_already_assigned_without_orphan_mileage(self):
        self.create_active_assignment()
        before_count = MileageRecord.objects.count()
        response = self.client.post(
            "/api/vehicles/assignments/",
            {
                "vehicle": Vehicle.objects.create(
                    vehicle_type=Vehicle.Type.CAR,
                    registration_number="CAR 100",
                    make="Toyota",
                    model="Corolla",
                ).pk,
                "driver": self.driver.pk,
                "assigned_at": timezone.now().isoformat(),
                "start_mileage_km": 200,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MileageRecord.objects.count(), before_count)

    def test_reassign_atomically_releases_and_creates_next_assignment(self):
        current = self.create_active_assignment()
        handover_at = timezone.now()
        response = self.client.post(
            f"/api/vehicles/assignments/{current.pk}/reassign/",
            {
                "driver": self.next_driver.pk,
                "handover_at": handover_at.isoformat(),
                "release_mileage_km": 105,
                "start_mileage_km": 105,
                "handover_notes": "Keys handed over.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        current.refresh_from_db()
        next_assignment = VehicleAssignment.objects.get(pk=response.data["assignment"]["id"])
        self.assertEqual(current.released_at, handover_at)
        self.assertEqual(current.release_mileage_record.odometer_km, 105)
        self.assertEqual(current.released_by_id, self.staff_user.pk)
        self.assertEqual(next_assignment.driver_id, self.next_driver.pk)
        self.assertEqual(next_assignment.assigned_at, handover_at)
        self.assertEqual(next_assignment.start_mileage_record.odometer_km, 105)
        self.assertEqual(next_assignment.handover_notes, "Keys handed over.")
        self.assertEqual(VehicleAssignment.objects.filter(vehicle=self.vehicle, released_at__isnull=True).count(), 1)

    def test_reassign_rolls_back_release_mileage_when_return_reading_is_invalid(self):
        current = self.create_active_assignment(odometer=100)
        before_count = MileageRecord.objects.count()
        response = self.client.post(
            f"/api/vehicles/assignments/{current.pk}/reassign/",
            {
                "driver": self.next_driver.pk,
                "handover_at": timezone.now().isoformat(),
                "release_mileage_km": 99,
                "start_mileage_km": 100,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        current.refresh_from_db()
        self.assertIsNone(current.released_at)
        self.assertEqual(MileageRecord.objects.count(), before_count)
        self.assertEqual(VehicleAssignment.objects.filter(vehicle=self.vehicle, released_at__isnull=True).count(), 1)

    def test_reassign_rejects_driver_with_another_active_vehicle(self):
        current = self.create_active_assignment()
        other_vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.CAR,
            registration_number="CAR 200",
            make="Toyota",
            model="Corolla",
        )
        other_start = MileageRecord.objects.create(
            vehicle=other_vehicle,
            odometer_km=10,
            recorded_at=timezone.now() - timedelta(minutes=1),
            source=MileageRecord.Source.ASSIGNMENT_START,
            recorded_by=self.staff_user,
        )
        VehicleAssignment.objects.create(
            vehicle=other_vehicle,
            driver=self.next_driver,
            assigned_at=other_start.recorded_at,
            start_mileage_record=other_start,
            assigned_by=self.staff_user,
        )
        before_count = MileageRecord.objects.count()
        response = self.client.post(
            f"/api/vehicles/assignments/{current.pk}/reassign/",
            {
                "driver": self.next_driver.pk,
                "handover_at": timezone.now().isoformat(),
                "release_mileage_km": 105,
                "start_mileage_km": 105,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MileageRecord.objects.count(), before_count)

    def test_create_endpoint_requires_staff_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/vehicles/assignments/", {}, format="json")
        self.assertEqual(response.status_code, 401)

