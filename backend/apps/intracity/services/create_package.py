import random
import string

from django.db import transaction

from apps.bookkeeping.models import ExchangeRate
from apps.users.models import City, Customer, Suburb

from ..models import Invoice, Package, PackageStatus
from .customer_provisioning import resolve_or_create_customer
from .package_assignment import assign_pending_packages_safely
from .package_notifications import send_package_booking_sms


class PackageCreationError(Exception):
    pass


class PackageCreationNotFound(PackageCreationError):
    pass


@transaction.atomic
def create_package(*, user, data):
    counterpart_phone = data.get("phone")
    counterpart_name = data.get("name")
    pickup_address = data.get("pickup_location")
    dropoff_address = data.get("dropoff_location")
    pickup_area_id = data.get("pickup_area_id")
    dropoff_area_id = data.get("dropoff_area_id")
    comments = data.get("comments")
    invoice_amount = data.get("amount")
    is_fast_delivery = bool(data.get("is_fast_delivery", False))
    is_pay_forward = bool(data.get("is_pay_forward", False))
    is_sender_initiated = bool(data.get("is_sender_initiated", True))

    counterpart = resolve_or_create_customer(
        counterpart_phone,
        counterpart_name,
    )
    city = City.objects.first()

    if is_sender_initiated:
        sender = Customer.objects.get(user=user)
        receiver = counterpart
    else:
        sender = counterpart
        receiver = Customer.objects.get(user=user)

    try:
        pickup_area = Suburb.objects.get(id=pickup_area_id)
        dropoff_area = Suburb.objects.get(id=dropoff_area_id)
    except Suburb.DoesNotExist as exc:
        raise PackageCreationNotFound("suburb not found") from exc

    package = Package.objects.create(
        sender=sender,
        receiver=receiver,
        is_sender_initiated=is_sender_initiated,
        city=city,
        is_fast_delivery=is_fast_delivery,
        pickup_area=pickup_area,
        pickup_address=pickup_address,
        dropoff_area=dropoff_area,
        dropoff_address=dropoff_address,
        receiver_code=_generate_collection_code(),
        sender_code=_generate_collection_code(),
        comments=comments,
    )
    PackageStatus.objects.create(package=package, status="Pending")
    invoice = Invoice.objects.create(
        package=package,
        amount=invoice_amount,
        is_pay_forward=is_pay_forward,
        is_paid=False,
        exchange_rate=ExchangeRate.objects.last(),
    )

    transaction.on_commit(
        lambda: send_package_booking_sms(
            counterpart_phone,
            package,
            invoice,
        )
    )
    transaction.on_commit(assign_pending_packages_safely)
    return package, invoice


def _generate_collection_code():
    while True:
        code = "".join(random.choices(string.digits, k=6))
        if not Package.objects.filter(receiver_code=code).exists():
            return code
