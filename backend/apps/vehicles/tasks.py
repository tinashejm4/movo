from celery import shared_task

from .fuel_prices import refresh_fuel_prices


@shared_task(name="apps.vehicles.tasks.refresh_fuel_prices_task")
def refresh_fuel_prices_task():
    return len(refresh_fuel_prices())
