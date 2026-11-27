from celery import shared_task

from .services.package_expiration import expire_uncollected_packages
from .services.round_trip_expiration import expire_uncollected_round_trips


@shared_task(time_limit=300)
def expire_uncollected_packages_task():
    result = expire_uncollected_packages()
    result["round_trips"] = expire_uncollected_round_trips()
    return result
