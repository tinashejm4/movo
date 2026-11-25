from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.users.models import Suburb

from .package_pricing import PackagePricingError, calculate_package_price


@transaction.atomic
def calculate_round_trip_price(*, pickup_area_id, recipient_area_id, is_fast_delivery=False):
    pickup = Suburb.objects.filter(pk=pickup_area_id).select_related("city").first()
    recipient = Suburb.objects.filter(pk=recipient_area_id).first()
    if not pickup or not recipient:
        raise ValidationError({"area_id": "Suburb not found."})
    if pickup.city_id != recipient.city_id:
        raise ValidationError({"area_id": "Both stops must be in the same city."})
    if not pickup.is_active or not recipient.is_active:
        raise ValidationError({"area_id": "Both stops must be in active service areas."})
    if any(value is None for value in (
        pickup.x_coord, pickup.y_coord, recipient.x_coord, recipient.y_coord,
    )):
        raise ValidationError({"area_id": "Both stops need configured coordinates."})
    try:
        one_way = calculate_package_price(
            pickup.id, recipient.id, pickup.city_id, is_fast_delivery
        )
    except (PackagePricingError, TypeError) as exc:
        raise ValidationError({"price": str(exc)}) from exc
    amount = (Decimal(str(one_way["amount"])) * Decimal("1.5")).quantize(Decimal("0.01"))
    return {
        "city_id": pickup.city_id,
        "distance_km": one_way["distance_km"],
        "is_fast_delivery": bool(is_fast_delivery),
        "one_way_amount": Decimal(str(one_way["amount"])),
        "amount": amount,
    }
