from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.bookkeeping.models import ExchangeRate
from apps.users.models import Customer, Suburb
from apps.users.utils import is_valid_zimbabwean_number

from ..models import (Invoice, RoundTripOrder, RoundTripParcel, RoundTripStop,
                      RoundTripStopAction)
from .customer_provisioning import resolve_or_create_customer
from .round_trip_pricing import calculate_round_trip_price


STOP_ACTIONS = {
    "sender_pickup": ("PICKUP_ITEM", "VERIFY_HANDOFF"),
    "recipient": ("DROP_OFF_ITEM", "COLLECT_CASH", "VERIFY_HANDOFF"),
    "sender_return": ("HAND_OVER_CASH", "VERIFY_HANDOFF"),
}


@transaction.atomic
def create_round_trip(*, user, data):
    sender = Customer.objects.filter(user=user).first()
    if sender is None:
        raise ValidationError({"sender": "Customer profile required."})
    recipient_input = data["stops"][0]
    contact = recipient_input["contact"]
    if not is_valid_zimbabwean_number(contact["phone"]):
        raise ValidationError({"phone": "Invalid Zimbabwean phone number."})
    price = calculate_round_trip_price(
        pickup_area_id=data["pickup"]["area_id"],
        recipient_area_id=recipient_input["area_id"],
        is_fast_delivery=data.get("is_fast_delivery", False),
    )
    pickup_area = Suburb.objects.get(pk=data["pickup"]["area_id"])
    recipient_area = Suburb.objects.get(pk=recipient_input["area_id"])
    recipient = resolve_or_create_customer(contact["phone"], contact["name"])
    if not sender.user.is_active or not recipient.user.is_active:
        raise ValidationError({"contact": "Sender or recipient is inactive."})
    collection = data["collection"]
    order = RoundTripOrder.objects.create(
        sender=sender, recipient=recipient, city_id=price["city_id"],
        cash_amount=collection["amount"], cash_currency=collection["currency"],
        is_fast_delivery=data.get("is_fast_delivery", False),
        comments=data.get("comments", ""),
    )
    RoundTripParcel.objects.create(order=order, description=data["parcels"][0]["description"])
    for sequence, kind, area, address, contact_customer in (
        (1, "sender_pickup", pickup_area, data["pickup"]["address"], sender),
        (2, "recipient", recipient_area, recipient_input["address"], recipient),
        (3, "sender_return", pickup_area, data["pickup"]["address"], sender),
    ):
        stop = RoundTripStop.objects.create(order=order, sequence=sequence, kind=kind,
                                            area=area, address=address, contact=contact_customer)
        RoundTripStopAction.objects.bulk_create([
            RoundTripStopAction(stop=stop, action=action) for action in STOP_ACTIONS[kind]
        ])
    Invoice.objects.create(
        round_trip=order, amount=price["amount"], is_pay_forward=False,
        exchange_rate=ExchangeRate.objects.last(),
    )
    from .round_trip_dispatch import assign_pending_round_trips_safely
    transaction.on_commit(assign_pending_round_trips_safely)
    return order
