from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .models import BikerDailySession, DriverClockInterval, DriverShiftException, WeeklyDriverShift


def effective_shift(biker, day):
    exception = DriverShiftException.objects.filter(biker=biker, date=day).first()
    shift = exception or WeeklyDriverShift.objects.get(weekday=day.weekday())
    return {
        'date': day,
        'is_open': shift.is_open,
        'start_time': shift.start_time if shift.is_open else None,
        'end_time': shift.end_time if shift.is_open else None,
        'source': 'exception' if exception else 'weekly',
    }


def shift_allows_work(shift, now):
    local = timezone.localtime(now)
    return (shift['is_open'] and shift['start_time'] <= local.time().replace(tzinfo=None)
            < shift['end_time'])


def scheduled_end(shift):
    return timezone.make_aware(datetime.combine(shift['date'], shift['end_time']), timezone.get_current_timezone())


def clock_out(session, *, now, reason, boundary=None):
    if not session.is_active:
        return False
    interval = session.clock_intervals.filter(clocked_out_at__isnull=True).order_by('-clocked_in_at', '-pk').first()
    if interval is None:
        interval = DriverClockInterval.objects.create(session=session, clocked_in_at=session.start_time)
    end = boundary or now
    # An edited schedule can move the boundary before the driver clocked in.
    if end < interval.clocked_in_at:
        end = now
    interval.clocked_out_at = end
    interval.clock_out_reason = reason
    interval.save(update_fields=['clocked_out_at', 'clock_out_reason'])
    session.is_active = False
    session.end_time = end
    session.save(update_fields=['is_active', 'end_time'])
    return True


@transaction.atomic
def reconcile_driver(biker, now=None):
    now = now or timezone.now()
    day = timezone.localdate(now)
    session = BikerDailySession.objects.select_for_update().filter(biker=biker, date=day, is_active=True).first()
    if not session:
        return False
    shift = effective_shift(biker, day)
    if shift_allows_work(shift, now):
        return False
    local = timezone.localtime(now)
    boundary = scheduled_end(shift) if shift['is_open'] and local.time().replace(tzinfo=None) >= shift['end_time'] else now
    return clock_out(session, now=now, reason=DriverClockInterval.SCHEDULED, boundary=boundary)


def reconcile_all_drivers(now=None):
    now = now or timezone.now()
    today = timezone.localdate(now)
    sessions = BikerDailySession.objects.filter(date__lte=today, is_active=True).select_related('biker')
    closed = 0
    for session in sessions.iterator():
        if session.date == today:
            closed += reconcile_driver(session.biker, now)
        else:
            with transaction.atomic():
                locked = BikerDailySession.objects.select_for_update().get(pk=session.pk)
                shift = effective_shift(locked.biker, locked.date)
                boundary = scheduled_end(shift) if shift['is_open'] else now
                closed += clock_out(locked, now=now, reason=DriverClockInterval.SCHEDULED, boundary=boundary)
    return closed
