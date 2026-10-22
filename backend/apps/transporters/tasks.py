from celery import shared_task

from .shift_service import reconcile_all_drivers


@shared_task
def clock_out_finished_shifts():
    return reconcile_all_drivers()
