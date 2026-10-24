from celery import shared_task

from .services.package_expiration import expire_uncollected_packages


@shared_task(time_limit=300)
def expire_uncollected_packages_task():
    return expire_uncollected_packages()
