from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookkeeping.models import Asset
from apps.users.models import Biker, Branch, Staff
from .models import InsurancePolicy, LicensingRecord, MileageRecord, ServiceRecord, Vehicle, VehicleAssignment


class VehicleAssetTests(TestCase):
    def test_create_vehicle_creates_linked_asset(self):
        vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.CAR,
            registration_number="ASSET 100",
            make="Toyota",
            model="Corolla",
        )

        self.assertEqual(vehicle.asset.asset_type, "vehicle")
        self.assertEqual(vehicle.asset.name, "Toyota Corolla")
        self.assertEqual(vehicle.asset.unique_identifier, "ASSET 100")
        self.assertEqual(vehicle.asset.fleet_vehicles.get(), vehicle)

        vehicle.status = Vehicle.Status.MAINTENANCE
        vehicle.save()
        self.assertEqual(Asset.objects.count(), 1)

    def test_failed_vehicle_creation_rolls_back_asset(self):
        Vehicle.objects.create(
            vehicle_type=Vehicle.Type.CAR,
            registration_number="ASSET 101",
            make="Toyota",
            model="Corolla",
            vin="VIN-101",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Vehicle.objects.create(
                vehicle_type=Vehicle.Type.CAR,
                registration_number="ASSET 102",
                make="Honda",
                model="Fit",
                vin="VIN-101",
            )
        self.assertFalse(Asset.objects.filter(unique_identifier="ASSET 102").exists())

    def test_explicit_asset_is_preserved(self):
        asset = Asset.objects.create(
            asset_type="vehicle", name="Existing vehicle", unique_identifier="ASSET EXISTING"
        )
        vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.CAR,
            registration_number="ASSET 106",
            make="Toyota",
            model="Corolla",
            asset=asset,
        )
        self.assertEqual(vehicle.asset_id, asset.pk)
        self.assertEqual(Asset.objects.count(), 1)

    def test_asset_name_respects_maximum_length(self):
        vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.CAR,
            registration_number="ASSET 103",
            make="A" * 100,
            model="B" * 100,
        )
        self.assertEqual(len(vehicle.asset.name), 100)

    def test_api_links_existing_vehicle_asset_and_rejects_invalid_assets(self):
        branch = Branch.objects.create(name="Asset branch", address="Harare")
        staff_user = User.objects.create_user(username="asset-staff")
        Staff.objects.create(user=staff_user, branch=branch, position="Manager")
        client = APIClient()
        client.force_authenticate(staff_user)
        asset = Asset.objects.create(asset_type="vehicle", name="Vehicle", unique_identifier="ASSET 104")
        equipment = Asset.objects.create(asset_type="equipment", name="Equipment", unique_identifier="ASSET 105")
        data = {
            "vehicle_type": "car",
            "registration_number": "ASSET 104",
            "make": "Toyota",
            "model": "Corolla",
            "asset": asset.id,
        }

        options = client.get("/api/vehicles/vehicles/available-assets/")
        self.assertEqual(options.status_code, 200)
        self.assertEqual([item["id"] for item in options.data], [asset.id])
        missing = client.post("/api/vehicles/vehicles/", {key: value for key, value in data.items() if key != "asset"})
        self.assertEqual(missing.status_code, 400)
        self.assertIn("asset", missing.data)
        invalid = client.post("/api/vehicles/vehicles/", {**data, "asset": equipment.id})
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(Vehicle.objects.exists())
        response = client.post("/api/vehicles/vehicles/", data)
        self.assertEqual(response.status_code, 201)
        vehicle = Vehicle.objects.get(pk=response.data["id"])
        self.assertEqual(response.data["asset"], asset.id)
        self.assertEqual(vehicle.asset_id, asset.id)
        self.assertEqual(vehicle.asset.unique_identifier, "ASSET 104")
        self.assertEqual(Asset.objects.count(), 2)
        self.assertEqual(client.get("/api/vehicles/vehicles/available-assets/").data, [])
        response = client.post("/api/vehicles/vehicles/", {**data, "registration_number": "OTHER"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("asset", response.data)
        self.assertEqual(Vehicle.objects.count(), 1)
        updated = client.patch(f"/api/vehicles/vehicles/{vehicle.id}/", {"make": "Honda"}, format="json")
        self.assertEqual(updated.status_code, 200)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.asset_id, asset.id)
        self.assertEqual(vehicle.make, "Honda")


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

    def test_vehicle_list_reports_availability_and_assigned_biker_id(self):
        self.client.force_authenticate(self.staff_user)

        response = self.client.get("/api/vehicles/vehicles/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data[0]["available"])
        self.assertIsNone(response.data[0]["assigned_to"])

        now = timezone.now()
        start = self.make_mileage(MileageRecord.Source.ASSIGNMENT_START, 10, now)
        VehicleAssignment.objects.create(
            vehicle=self.vehicle,
            driver=self.biker,
            assigned_at=now,
            start_mileage_record=start,
        )

        response = self.client.get("/api/vehicles/vehicles/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data[0]["available"])
        self.assertEqual(response.data[0]["assigned_to"], self.biker.pk)

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


class MileageRecordReadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Mileage branch", address="Harare")
        self.staff_user = User.objects.create_user(
            username="mileage-staff", password="test", first_name="Moyo", last_name="Staff"
        )
        Staff.objects.create(user=self.staff_user, branch=self.branch, position="Manager")
        self.other_staff = User.objects.create_user(username="recorder", password="test")
        self.vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="MIL 100",
            make="Honda",
            model="XR150",
        )
        self.other_vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.CAR,
            registration_number="MIL 200",
            make="Toyota",
            model="Corolla",
        )
        self.client.force_authenticate(self.staff_user)

    def make_record(self, vehicle, odometer, recorded_at, recorded_by=None):
        return MileageRecord.objects.create(
            vehicle=vehicle,
            odometer_km=odometer,
            recorded_at=recorded_at,
            source=MileageRecord.Source.MANUAL,
            recorded_by=recorded_by or self.other_staff,
        )

    def test_list_includes_previous_reading_difference_and_display_names(self):
        recorded_at = timezone.now()
        earlier = self.make_record(self.vehicle, 1200, recorded_at - timedelta(days=1))
        current = self.make_record(self.vehicle, 1350, recorded_at)

        response = self.client.get("/api/vehicles/mileage-records/")

        self.assertEqual(response.status_code, 200)
        data = {item["id"]: item for item in response.data}
        self.assertIsNone(data[earlier.pk]["previous_odometer_km"])
        self.assertIsNone(data[earlier.pk]["distance_travelled_km"])
        self.assertEqual(data[current.pk]["previous_odometer_km"], 1200)
        self.assertEqual(data[current.pk]["distance_travelled_km"], 150)
        self.assertEqual(data[current.pk]["vehicle"], self.vehicle.pk)
        self.assertEqual(data[current.pk]["vehicle_name"], "Honda XR150")
        self.assertEqual(data[current.pk]["vehicle_registration_number"], "MIL 100")
        self.assertEqual(data[current.pk]["recorded_by"], self.other_staff.pk)
        self.assertEqual(data[current.pk]["recorded_by_name"], "recorder")

    def test_previous_reading_isolated_per_vehicle_and_equal_times_use_id(self):
        recorded_at = timezone.now()
        first = self.make_record(self.vehicle, 100, recorded_at)
        same_time = self.make_record(self.vehicle, 150, recorded_at)
        other = self.make_record(self.other_vehicle, 500, recorded_at)

        response = self.client.get("/api/vehicles/mileage-records/")

        self.assertEqual(response.status_code, 200)
        data = {item["id"]: item for item in response.data}
        self.assertEqual(data[same_time.pk]["previous_odometer_km"], first.odometer_km)
        self.assertEqual(data[same_time.pk]["distance_travelled_km"], 50)
        self.assertIsNone(data[other.pk]["previous_odometer_km"])

    def test_vehicle_id_filter_returns_only_records_for_that_vehicle(self):
        own = self.make_record(self.vehicle, 100, timezone.now())
        self.make_record(self.other_vehicle, 200, timezone.now())

        response = self.client.get(f"/api/vehicles/mileage-records/?vehicle_id={self.vehicle.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [own.pk])

    def test_vehicle_id_filter_rejects_invalid_value(self):
        response = self.client.get("/api/vehicles/mileage-records/?vehicle_id=unknown")

        self.assertEqual(response.status_code, 400)
        self.assertIn("vehicle_id", response.data)


class ServiceRecordApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Service branch", address="Harare")
        self.staff_user = User.objects.create_user(
            username="service-staff", password="test", first_name="Tariro", last_name="Staff"
        )
        Staff.objects.create(user=self.staff_user, branch=self.branch, position="Manager")
        self.vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="SVC 100",
            make="Honda",
            model="XR150",
        )
        self.other_vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.CAR,
            registration_number="SVC 200",
            make="Toyota",
            model="Corolla",
        )
        self.client.force_authenticate(self.staff_user)

    def create_service(self, vehicle, **overrides):
        values = {
            "vehicle": vehicle,
            "service_date": "2026-11-07",
            "description": "Oil and filter replacement",
            "service_provider": "Movo Workshop",
            "odometer_km": 1200,
            "cost": "25.50",
            "currency": "USD",
            "next_service_date": None,
            "next_service_odometer_km": 6200,
            "notes": "Routine service",
            "recorded_by": self.staff_user,
        }
        values.update(overrides)
        return ServiceRecord.objects.create(**values)

    def test_list_includes_vehicle_and_recorder_display_fields(self):
        service = self.create_service(self.vehicle)

        response = self.client.get("/api/vehicles/service-records/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["id"], service.pk)
        self.assertEqual(response.data[0]["vehicle"], self.vehicle.pk)
        self.assertEqual(response.data[0]["vehicle_name"], "Honda XR150")
        self.assertEqual(response.data[0]["vehicle_registration_number"], "SVC 100")
        self.assertEqual(response.data[0]["recorded_by"], self.staff_user.pk)
        self.assertEqual(response.data[0]["recorded_by_name"], "Tariro Staff")

    def test_vehicle_id_filter_returns_only_records_for_that_vehicle(self):
        own = self.create_service(self.vehicle)
        self.create_service(self.other_vehicle)

        response = self.client.get(f"/api/vehicles/service-records/?vehicle_id={self.vehicle.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [own.pk])

    def test_vehicle_id_filter_rejects_invalid_value(self):
        response = self.client.get("/api/vehicles/service-records/?vehicle_id=unknown")

        self.assertEqual(response.status_code, 400)
        self.assertIn("vehicle_id", response.data)

    def test_create_sets_recorder_from_authenticated_user(self):
        response = self.client.post(
            "/api/vehicles/service-records/",
            {
                "vehicle": self.vehicle.pk,
                "service_date": "2026-11-07",
                "description": "Oil and filter replacement",
                "service_provider": "Movo Workshop",
                "odometer_km": 1200,
                "cost": "25.50",
                "currency": "USD",
                "next_service_date": None,
                "next_service_odometer_km": 6200,
                "notes": "Routine service",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        saved = ServiceRecord.objects.get(pk=response.data["id"])
        self.assertEqual(saved.recorded_by_id, self.staff_user.pk)
        self.assertEqual(saved.vehicle_id, self.vehicle.pk)

    def test_list_requires_staff_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/vehicles/service-records/").status_code, 401)

        regular_user = User.objects.create_user(username="service-customer", password="test")
        self.client.force_authenticate(regular_user)
        self.assertEqual(self.client.get("/api/vehicles/service-records/").status_code, 403)


class InsuranceAndLicensingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Records branch", address="Harare")
        self.staff_user = User.objects.create_user(
            username="records-staff", password="test", first_name="Tariro", last_name="Staff"
        )
        Staff.objects.create(user=self.staff_user, branch=self.branch, position="Manager")
        self.other_vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="REC 100",
            make="Honda",
            model="XR150",
        )
        self.vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.CAR,
            registration_number="REC 200",
            make="Toyota",
            model="Corolla",
            status=Vehicle.Status.RETIRED,
        )
        self.client.force_authenticate(self.staff_user)

    def create_policy(self, vehicle, **overrides):
        values = {
            "vehicle": vehicle,
            "insurer": "Example Insurance",
            "policy_number": "POL-2026-001",
            "coverage_description": "Comprehensive cover",
            "start_date": "2026-01-01",
            "expiry_date": "2026-12-31",
            "premium": "250.00",
            "currency": "USD",
            "recorded_by": self.staff_user,
            "notes": "Renew before expiry.",
        }
        values.update(overrides)
        return InsurancePolicy.objects.create(**values)

    def create_license(self, vehicle, **overrides):
        values = {
            "vehicle": vehicle,
            "licence_type": "Vehicle licence",
            "reference_number": "LIC-2026-001",
            "issuing_authority": "Vehicle Registration Office",
            "issue_date": "2026-01-01",
            "expiry_date": "2026-12-31",
            "cost": "50.00",
            "currency": "USD",
            "recorded_by": self.staff_user,
            "notes": "Renew before expiry.",
        }
        values.update(overrides)
        return LicensingRecord.objects.create(**values)

    def test_insurance_list_filter_and_display_fields(self):
        policy = self.create_policy(self.vehicle)
        self.create_policy(self.other_vehicle, policy_number="POL-OTHER")

        response = self.client.get(f"/api/vehicles/insurance-policies/?vehicle_id={self.vehicle.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], policy.pk)
        self.assertEqual(response.data[0]["vehicle"], self.vehicle.pk)
        self.assertEqual(response.data[0]["vehicle_name"], "Toyota Corolla")
        self.assertEqual(response.data[0]["vehicle_registration_number"], "REC 200")
        self.assertEqual(response.data[0]["recorded_by_name"], "Tariro Staff")

    def test_insurance_list_rejects_invalid_vehicle_id(self):
        response = self.client.get("/api/vehicles/insurance-policies/?vehicle_id=0")
        self.assertEqual(response.status_code, 400)
        self.assertIn("vehicle_id", response.data)

    def test_insurance_create_sets_authenticated_recorder(self):
        response = self.client.post(
            "/api/vehicles/insurance-policies/",
            {
                "vehicle": self.vehicle.pk,
                "insurer": "Example Insurance",
                "policy_number": "POL-NEW",
                "coverage_description": "Comprehensive cover",
                "start_date": "2026-01-01",
                "expiry_date": "2026-12-31",
                "premium": "250.00",
                "currency": "USD",
                "notes": "Renew before expiry.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(InsurancePolicy.objects.get(pk=response.data["id"]).recorded_by_id, self.staff_user.pk)

    def test_licensing_list_filter_and_display_fields(self):
        record = self.create_license(self.vehicle)
        self.create_license(self.other_vehicle, reference_number="LIC-OTHER")

        response = self.client.get(f"/api/vehicles/licensing-records/?vehicle_id={self.vehicle.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], record.pk)
        self.assertEqual(response.data[0]["vehicle"], self.vehicle.pk)
        self.assertEqual(response.data[0]["vehicle_name"], "Toyota Corolla")
        self.assertEqual(response.data[0]["vehicle_registration_number"], "REC 200")
        self.assertEqual(response.data[0]["recorded_by_name"], "Tariro Staff")

    def test_licensing_list_rejects_invalid_vehicle_id(self):
        response = self.client.get("/api/vehicles/licensing-records/?vehicle_id=bad")
        self.assertEqual(response.status_code, 400)
        self.assertIn("vehicle_id", response.data)

    def test_licensing_create_sets_authenticated_recorder(self):
        response = self.client.post(
            "/api/vehicles/licensing-records/",
            {
                "vehicle": self.vehicle.pk,
                "licence_type": "Vehicle licence",
                "reference_number": "LIC-NEW",
                "issuing_authority": "Vehicle Registration Office",
                "issue_date": "2026-01-01",
                "expiry_date": "2026-12-31",
                "cost": "50.00",
                "currency": "USD",
                "notes": "Renew before expiry.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(LicensingRecord.objects.get(pk=response.data["id"]).recorded_by_id, self.staff_user.pk)

    def test_both_lists_require_staff_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/vehicles/insurance-policies/").status_code, 401)
        self.assertEqual(self.client.get("/api/vehicles/licensing-records/").status_code, 401)
        regular_user = User.objects.create_user(username="records-customer", password="test")
        self.client.force_authenticate(regular_user)
        self.assertEqual(self.client.get("/api/vehicles/insurance-policies/").status_code, 403)
        self.assertEqual(self.client.get("/api/vehicles/licensing-records/").status_code, 403)


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

    def test_create_defaults_start_mileage_to_previous_release(self):
        prior = self.create_active_assignment()
        release = MileageRecord.objects.create(
            vehicle=self.vehicle,
            odometer_km=145,
            recorded_at=timezone.now() - timedelta(minutes=1),
            source=MileageRecord.Source.ASSIGNMENT_RELEASE,
            recorded_by=self.staff_user,
        )
        prior.released_at = release.recorded_at
        prior.release_mileage_record = release
        prior.released_by = self.staff_user
        prior.save(update_fields=("released_at", "release_mileage_record", "released_by"))
        assigned_at = timezone.now()
        response = self.client.post(
            "/api/vehicles/assignments/",
            {
                "vehicle": self.vehicle.pk,
                "driver": self.next_driver.pk,
                "assigned_at": assigned_at.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        assignment = VehicleAssignment.objects.get(pk=response.data["id"])
        self.assertEqual(assignment.start_mileage_record.odometer_km, 145)

    def test_biker_can_finish_assignment_only_when_finish_mileage_is_required(self):
        assignment = self.create_active_assignment(odometer=100)
        url = f"/api/vehicles/assignments/{assignment.pk}/finish/"
        self.client.force_authenticate(self.driver.user)
        early = self.client.post(url, {"release_mileage_km": 110}, format="json")
        self.assertEqual(early.status_code, 400)
        assignment.finish_mileage_required = True
        assignment.save(update_fields=("finish_mileage_required",))
        too_low = self.client.post(url, {"release_mileage_km": 99}, format="json")
        self.assertEqual(too_low.status_code, 400)
        finished = self.client.post(url, {"release_mileage_km": 120}, format="json")
        self.assertEqual(finished.status_code, 200, finished.data)
        assignment.refresh_from_db()
        self.assertEqual(assignment.release_mileage_record.odometer_km, 120)
        self.assertFalse(assignment.finish_mileage_required)

    def test_biker_cannot_finish_another_drivers_assignment(self):
        assignment = self.create_active_assignment(driver=self.next_driver)
        assignment.finish_mileage_required = True
        assignment.save(update_fields=("finish_mileage_required",))
        self.client.force_authenticate(self.driver.user)
        response = self.client.post(
            f"/api/vehicles/assignments/{assignment.pk}/finish/",
            {"release_mileage_km": 110},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

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
