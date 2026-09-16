from decimal import Decimal
import math
from venv import logger
from django.utils import timezone

from apps.users.models import City, Suburb
from django.db.models import OuterRef, Subquery
from ..models import Price, Package, PackageStatus


class PackagePricingError(Exception):
    pass


class PackagePricingNotFound(PackagePricingError):
    pass


def calculate_package_price(from_suburb_id,to_suburb_id,city_id,is_fast_delivery=False):
    try:
        from_suburb = Suburb.objects.get(id=from_suburb_id)
        to_suburb = Suburb.objects.get(id=to_suburb_id)
        cbd = Suburb.objects.get(city_id=city_id, name = "CBD")
    except Suburb.DoesNotExist as exc:
        raise PackagePricingNotFound("suburb not found") from exc

    collection_distance = 0
    if cbd not in [from_suburb, to_suburb]:
        collection_distance = from_suburb.distance_to(cbd)
    
    try:
        transit_distance = from_suburb.distance_to(to_suburb)
    except ValueError as exc:
        raise PackagePricingError(str(exc)) from exc


    if transit_distance is None:
        raise PackagePricingError("distance_km is required")
    if transit_distance < 0:
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

    latest_status = (
        PackageStatus.objects.filter(package=OuterRef("pk"))
        .order_by("-updated_at", "-pk")
        .values("status")[:1]
    )

    pending_packages_count = (
        Package.objects.select_for_update()
        .filter(added_at__date=timezone.now().date())
        .annotate(status=Subquery(latest_status))
        .filter(status="Pending").count()
    )

    amount = float(price.base_price) + (
        float(price.rate_per_km) * (transit_distance + collection_distance)
    ) + (pending_packages_count / 10)

    if fast_delivery:

        pending_packages_fast_delivery_count = (
            Package.objects.select_for_update()
            .filter(added_at__date=timezone.now().date())
            .annotate(status=Subquery(latest_status))
            .filter(status="Pending", is_fast_delivery=True).count()
        )

        fast_delivery_amount = min(3, amount, 1.5+(pending_packages_fast_delivery_count / 4))
        amount += fast_delivery_amount

    decimal_part = amount - math.floor(amount)
    amount = math.ceil(amount) if decimal_part > 0.35 else math.floor(amount)

    return {
        "city_id": city.id,
        "distance_km": transit_distance+collection_distance,
        "is_fast_delivery": fast_delivery,
        "amount": amount,
    }
