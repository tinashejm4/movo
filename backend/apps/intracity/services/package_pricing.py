import math

from apps.users.models import City, Suburb

from ..models import Price


class PackagePricingError(Exception):
    pass


class PackagePricingNotFound(PackagePricingError):
    pass


def calculate_package_price(
    *,
    from_suburb_id,
    to_suburb_id,
    city_id=None,
    is_fast_delivery=False,
):
    try:
        from_suburb = Suburb.objects.get(id=from_suburb_id)
        to_suburb = Suburb.objects.get(id=to_suburb_id)
    except Suburb.DoesNotExist as exc:
        raise PackagePricingNotFound("suburb not found") from exc

    try:
        distance_km = from_suburb.distance_to(to_suburb)
    except ValueError as exc:
        raise PackagePricingError(str(exc)) from exc

    if distance_km is None:
        raise PackagePricingError("distance_km is required")
    if distance_km < 0:
        raise PackagePricingError("distance_km must be zero or positive")

    if isinstance(is_fast_delivery, str):
        fast_delivery = is_fast_delivery.strip().lower() == "true"
    else:
        fast_delivery = bool(is_fast_delivery)

    if city_id:
        city = City.objects.filter(id=city_id).first()
        if city is None:
            raise PackagePricingNotFound("city not found")
    else:
        city = City.objects.first()

    if city is None:
        raise PackagePricingError("No city configured")

    price = Price.objects.filter(city=city).last()
    if price is None:
        raise PackagePricingError("No pricing configured for this city")

    amount = float(price.base_price) + (
        float(price.rate_per_km) * distance_km
    )
    if fast_delivery:
        amount *= float(price.fast_delivery_multiplier)

    decimal_part = amount - math.floor(amount)
    amount = math.ceil(amount) if decimal_part > 0.40 else math.floor(amount)

    return {
        "city_id": city.id,
        "distance_km": distance_km,
        "is_fast_delivery": fast_delivery,
        "amount": amount,
    }
