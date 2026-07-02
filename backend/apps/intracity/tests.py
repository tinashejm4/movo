from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.bookkeeping.models import Account, Sale

from apps.users.models import Biker, City, Contact, Customer

from .models import Invoice, Package, PackageStatus


class IntracityPackageCreationTests(APITestCase):
	def setUp(self):
		self.city = City.objects.create(name="Harare", province="Harare", country="Zimbabwe")

	def test_user_initiated_creation_auto_creates_customers(self):
		payload = {
			"sender_name": "Tariro Moyo",
			"sender_phone": "0771000001",
			"receiver_name": "Nyasha Kamba",
			"receiver_phone": "0771000002",
			"pickup_location": "Avondale",
			"dropoff_location": "Borrowdale",
			"city_id": self.city.id,
			"initiated_by": "user",
			"comments": "Handle with care",
		}

		response = self.client.post(reverse("intracity_create_package"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		package_id = response.data["package"]["id"]
		package = Package.objects.get(id=package_id)

		self.assertFalse(package.is_sender_initiated)
		self.assertEqual(package.sender.user.username, payload["sender_phone"])
		self.assertEqual(package.receiver.user.username, payload["receiver_phone"])
		self.assertTrue(Contact.objects.filter(phone_number=payload["sender_phone"]).exists())
		self.assertTrue(Contact.objects.filter(phone_number=payload["receiver_phone"]).exists())
		self.assertTrue(Customer.objects.filter(user__username=payload["sender_phone"]).exists())
		self.assertTrue(Customer.objects.filter(user__username=payload["receiver_phone"]).exists())

	def test_sender_initiated_creation_marks_package(self):
		payload = {
			"sender_name": "Simba M",
			"sender_phone": "0771000011",
			"receiver_name": "Maya K",
			"receiver_phone": "0771000012",
			"pickup_location": "CBD",
			"dropoff_location": "Westgate",
			"city_id": self.city.id,
			"initiated_by": "sender",
		}

		response = self.client.post(reverse("intracity_create_package"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		package = Package.objects.get(id=response.data["package"]["id"])
		self.assertTrue(package.is_sender_initiated)


class IntracityAssignmentTests(APITestCase):
	def setUp(self):
		self.dispatcher = User.objects.create_user(username="dispatch", password="dispatchpass")
		self.client.force_authenticate(user=self.dispatcher)

		self.city = City.objects.create(name="Harare", province="Harare", country="Zimbabwe")

		sender_user = User.objects.create_user(username="0779000001", password="pass")
		receiver_user = User.objects.create_user(username="0779000002", password="pass")
		self.sender_customer = Customer.objects.create(user=sender_user)
		self.receiver_customer = Customer.objects.create(user=receiver_user)

		rider_one_user = User.objects.create_user(username="rider-one", password="pass", first_name="Rider", last_name="One")
		rider_two_user = User.objects.create_user(username="rider-two", password="pass", first_name="Rider", last_name="Two")
		self.rider_one = Biker.objects.create(user=rider_one_user)
		self.rider_two = Biker.objects.create(user=rider_two_user)

	def _create_pending_package(self, *, is_fast_delivery=False):
		package = Package.objects.create(
			sender=self.sender_customer,
			receiver=self.receiver_customer,
			city=self.city,
			pickup_location="A",
			dropoff_location="B",
			sender_code="111111",
			receiver_code="222222",
			is_fast_delivery=is_fast_delivery,
		)
		PackageStatus.objects.create(package=package, status="Pending")
		return package

	def test_assign_pending_packages_prioritizes_fast_delivery_then_fifo(self):
		normal_first = self._create_pending_package(is_fast_delivery=False)
		fast_second = self._create_pending_package(is_fast_delivery=True)
		normal_third = self._create_pending_package(is_fast_delivery=False)

		response = self.client.post(reverse("intracity_assign_pending_packages"), {}, format="json")

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["assigned_count"], 2)
		self.assertEqual(response.data["unassigned_count"], 1)

		fast_second.refresh_from_db()
		normal_first.refresh_from_db()
		normal_third.refresh_from_db()

		self.assertIsNotNone(fast_second.biker)
		self.assertIsNotNone(normal_first.biker)
		self.assertIsNone(normal_third.biker)
		self.assertIsNotNone(fast_second.assigned_at)
		self.assertIsNotNone(normal_first.assigned_at)
		self.assertIsNone(normal_third.assigned_at)

		assigned_ids_in_order = [item["package_id"] for item in response.data["assigned_packages"]]
		self.assertEqual(assigned_ids_in_order[0], fast_second.id)
		self.assertEqual(assigned_ids_in_order[1], normal_first.id)
		self.assertIn("assigned_at", response.data["assigned_packages"][0])


class IntracityPickupVerificationTests(APITestCase):
	def setUp(self):
		self.city = City.objects.create(name="Harare", province="Harare", country="Zimbabwe")

		sender_user = User.objects.create_user(username="0780000001", password="pass")
		receiver_user = User.objects.create_user(username="0780000002", password="pass")
		self.sender_customer = Customer.objects.create(user=sender_user)
		self.receiver_customer = Customer.objects.create(user=receiver_user)

		self.biker_user = User.objects.create_user(username="pickup-rider", password="pass")
		self.other_biker_user = User.objects.create_user(username="other-rider", password="pass")
		self.biker = Biker.objects.create(user=self.biker_user)
		self.other_biker = Biker.objects.create(user=self.other_biker_user)

		self.package = Package.objects.create(
			sender=self.sender_customer,
			receiver=self.receiver_customer,
			city=self.city,
			biker=self.biker,
			pickup_location="A",
			dropoff_location="B",
			sender_code="654321",
			receiver_code="123456",
		)
		self.cash_account = Account.objects.create(name="Intracity Cash Drawer")
		self.invoice = Invoice.objects.create(
			package=self.package,
			amount=12.50,
			payment_method="cash",
			is_pay_forward=False,
			is_paid=False,
		)
		PackageStatus.objects.create(package=self.package, status="Pending")

	def test_pickup_verify_updates_status_when_code_matches(self):
		self.client.force_authenticate(user=self.biker_user)
		payload = {
			"package_id": self.package.id,
			"sender_code": "654321",
			"account_id": self.cash_account.id,
		}

		response = self.client.post(reverse("intracity_pickup_verify"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["status"], "In Transit")
		latest_status = PackageStatus.objects.filter(package=self.package).order_by("-updated_at").first()
		self.assertIsNotNone(latest_status)
		self.assertEqual(latest_status.status, "In Transit")
		self.invoice.refresh_from_db()
		self.assertTrue(self.invoice.is_paid)
		self.assertIsNotNone(self.invoice.paid_at)
		sale = Sale.objects.filter(intracity_invoice=self.invoice).first()
		self.assertIsNotNone(sale)
		self.assertEqual(sale.account_id, self.cash_account.id)

	def test_pickup_verify_rejects_wrong_sender_code(self):
		self.client.force_authenticate(user=self.biker_user)
		payload = {"package_id": self.package.id, "sender_code": "000000"}

		response = self.client.post(reverse("intracity_pickup_verify"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(response.data["error"], "Invalid sender code")

	def test_pickup_verify_rejects_other_biker(self):
		self.client.force_authenticate(user=self.other_biker_user)
		payload = {"package_id": self.package.id, "sender_code": "654321"}

		response = self.client.post(reverse("intracity_pickup_verify"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_pickup_verify_requires_account_for_cash_non_pay_forward(self):
		self.client.force_authenticate(user=self.biker_user)
		payload = {"package_id": self.package.id, "sender_code": "654321"}

		response = self.client.post(reverse("intracity_pickup_verify"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(response.data["error"], "account_id is required for pickup cash payments")
		latest_status = PackageStatus.objects.filter(package=self.package).order_by("-updated_at").first()
		self.assertEqual(latest_status.status, "Pending")


class IntracityDropoffVerificationTests(APITestCase):
	def setUp(self):
		self.city = City.objects.create(name="Harare", province="Harare", country="Zimbabwe")

		sender_user = User.objects.create_user(username="0790000001", password="pass")
		receiver_user = User.objects.create_user(username="0790000002", password="pass")
		self.sender_customer = Customer.objects.create(user=sender_user)
		self.receiver_customer = Customer.objects.create(user=receiver_user)

		self.biker_user = User.objects.create_user(username="dropoff-rider", password="pass")
		self.other_biker_user = User.objects.create_user(username="dropoff-other", password="pass")
		self.biker = Biker.objects.create(user=self.biker_user)
		self.other_biker = Biker.objects.create(user=self.other_biker_user)

		self.package = Package.objects.create(
			sender=self.sender_customer,
			receiver=self.receiver_customer,
			city=self.city,
			biker=self.biker,
			pickup_location="A",
			dropoff_location="B",
			sender_code="111222",
			receiver_code="333444",
		)
		PackageStatus.objects.create(package=self.package, status="Pending")
		PackageStatus.objects.create(package=self.package, status="In Transit")

	def test_dropoff_verify_updates_status_when_code_matches(self):
		self.client.force_authenticate(user=self.biker_user)
		payload = {"package_id": self.package.id, "receiver_code": "333444"}

		response = self.client.post(reverse("intracity_dropoff_verify"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["status"], "Delivered")
		self.package.refresh_from_db()
		self.assertIsNotNone(self.package.delivered_at)
		latest_status = PackageStatus.objects.filter(package=self.package).order_by("-updated_at").first()
		self.assertEqual(latest_status.status, "Delivered")

	def test_dropoff_verify_rejects_wrong_receiver_code(self):
		self.client.force_authenticate(user=self.biker_user)
		payload = {"package_id": self.package.id, "receiver_code": "000000"}

		response = self.client.post(reverse("intracity_dropoff_verify"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(response.data["error"], "Invalid receiver code")

	def test_dropoff_verify_rejects_other_biker(self):
		self.client.force_authenticate(user=self.other_biker_user)
		payload = {"package_id": self.package.id, "receiver_code": "333444"}

		response = self.client.post(reverse("intracity_dropoff_verify"), payload, format="json")

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class IntracityPackageListTests(APITestCase):
	def setUp(self):
		self.city = City.objects.create(name="Harare", province="Harare", country="Zimbabwe")

		self.user = User.objects.create_user(username="list-user", password="pass")
		self.other_user = User.objects.create_user(username="other-user", password="pass")
		self.third_user = User.objects.create_user(username="third-user", password="pass")
		self.biker_user = User.objects.create_user(username="list-rider", password="pass")
		self.biker = Biker.objects.create(user=self.biker_user)

		self.sender_customer = Customer.objects.create(user=self.user)
		self.receiver_customer = Customer.objects.create(user=self.other_user)

		self.own_package = Package.objects.create(
			sender=self.sender_customer,
			receiver=self.receiver_customer,
			city=self.city,
			biker=self.biker,
			pickup_location="Central",
			dropoff_location="Mabelreign",
			sender_code="101010",
			receiver_code="202020",
		)
		PackageStatus.objects.create(package=self.own_package, status="Pending")

		other_sender = Customer.objects.create(user=self.third_user)
		other_receiver = Customer.objects.create(user=self.user)
		self.other_package = Package.objects.create(
			sender=other_sender,
			receiver=other_receiver,
			city=self.city,
			pickup_location="Other Pickup",
			dropoff_location="Other Dropoff",
			sender_code="303030",
			receiver_code="404040",
		)
		PackageStatus.objects.create(package=self.other_package, status="Pending")

	def test_package_list_returns_only_logged_in_users_packages(self):
		self.client.force_authenticate(user=self.user)

		response = self.client.get(reverse("intracity_package_list"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["count"], 2)
		self.assertEqual(len(response.data["results"]), 2)

		for item in response.data["results"]:
			self.assertIn("package_id", item)
			self.assertIn("current_status", item)
			self.assertIn("city", item)
			self.assertIn("pickup_location", item)
			self.assertIn("dropoff_location", item)
			self.assertNotIn("receiver_code", item)
			self.assertNotIn("comments", item)

		package_ids = {item["package_id"] for item in response.data["results"]}
		self.assertIn(self.own_package.id, package_ids)
		self.assertIn(self.other_package.id, package_ids)


class IntracityCancelOrderTests(APITestCase):
	def setUp(self):
		self.city = City.objects.create(name="Harare", province="Harare", country="Zimbabwe")

		self.sender_user = User.objects.create_user(username="cancel-sender", password="pass")
		self.receiver_user = User.objects.create_user(username="cancel-receiver", password="pass")
		self.other_user = User.objects.create_user(username="cancel-other", password="pass")

		self.sender_customer = Customer.objects.create(user=self.sender_user)
		self.receiver_customer = Customer.objects.create(user=self.receiver_user)

		self.package = Package.objects.create(
			sender=self.sender_customer,
			receiver=self.receiver_customer,
			city=self.city,
			pickup_location="A",
			dropoff_location="B",
			sender_code="111000",
			receiver_code="222000",
		)
		PackageStatus.objects.create(package=self.package, status="Pending")

	def test_cancel_order_succeeds_when_pending(self):
		self.client.force_authenticate(user=self.sender_user)

		response = self.client.post(
			reverse("intracity_cancel_order"),
			{"package_id": self.package.id},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["status"], "Cancelled")
		latest_status = PackageStatus.objects.filter(package=self.package).order_by("-updated_at").first()
		self.assertIsNotNone(latest_status)
		self.assertEqual(latest_status.status, "Cancelled")

	def test_cancel_order_fails_when_not_pending(self):
		PackageStatus.objects.create(package=self.package, status="In Transit")
		self.client.force_authenticate(user=self.sender_user)

		response = self.client.post(
			reverse("intracity_cancel_order"),
			{"package_id": self.package.id},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(response.data["error"], "Order can only be cancelled when status is Pending")

	def test_cancel_order_fails_for_unrelated_user(self):
		self.client.force_authenticate(user=self.other_user)

		response = self.client.post(
			reverse("intracity_cancel_order"),
			{"package_id": self.package.id},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
