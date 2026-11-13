from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.notifications.services import queue_driver_shift_notification

from .models import (
    BikerDailySession,
    DriverClockInterval,
    DriverShiftException,
    DriverShiftReminderSetting,
    WeeklyDriverShift,
)


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
    if reason == DriverClockInterval.SCHEDULED:
        shift = effective_shift(session.biker, session.date)
        cutoff = scheduled_end(shift) if shift['is_open'] else end
        mark_assignment_return_pending(
            biker=session.biker,
            interval=interval,
            cutoff=cutoff,
        )
    return True


def mark_assignment_return_pending(*, biker, interval, cutoff):
    from apps.vehicles.models import VehicleAssignment

    assignment = VehicleAssignment.objects.select_for_update().filter(
        driver=biker,
        released_at__isnull=True,
        assigned_at__lte=cutoff,
    ).first()
    if assignment is not None:
        if not assignment.finish_mileage_required:
            assignment.finish_mileage_required = True
            assignment.save(update_fields=["finish_mileage_required"])
    if assignment is not None or interval is not None:
        queue_driver_shift_notification(
            biker=biker,
            interval=interval,
            cutoff=cutoff,
            event_type="shift.closed",
        )


@transaction.atomic
def reconcile_driver(biker, now=None):
    now = now or timezone.now()
    day = timezone.localdate(now)
    session = BikerDailySession.objects.select_for_update().filter(biker=biker, date=day).first()
    if not session:
        from apps.vehicles.models import VehicleAssignment

        assignment = VehicleAssignment.objects.select_for_update().filter(
            driver=biker,
            released_at__isnull=True,
            finish_mileage_required=False,
        ).first()
        if assignment is None:
            return False
        assignment_day = timezone.localdate(assignment.assigned_at)
        shift = effective_shift(biker, assignment_day)
        cutoff = scheduled_end(shift) if shift['is_open'] else now
        if now >= cutoff:
            mark_assignment_return_pending(
                biker=biker,
                interval=None,
                cutoff=cutoff,
            )
        return False
    shift = effective_shift(biker, day)
    if session.is_active and shift_allows_work(shift, now):
        cutoff = scheduled_end(shift)
        setting, _ = DriverShiftReminderSetting.objects.get_or_create(
            pk=1,
            defaults={"minutes_before_close": 30},
        )
        lead = setting.minutes_before_close
        if now >= cutoff - timedelta(minutes=lead):
            interval = (
                session.clock_intervals.filter(clocked_out_at__isnull=True)
                .order_by("-clocked_in_at", "-pk")
                .first()
            )
            if interval is None:
                interval = DriverClockInterval.objects.create(
                    session=session,
                    clocked_in_at=session.start_time,
                )
            queue_driver_shift_notification(
                biker=biker,
                interval=interval,
                cutoff=cutoff,
                event_type="shift.closing_soon",
            )
        return False
    local = timezone.localtime(now)
    if session.is_active:
        boundary = scheduled_end(shift) if shift['is_open'] and local.time().replace(tzinfo=None) >= shift['end_time'] else now
        return clock_out(session, now=now, reason=DriverClockInterval.SCHEDULED, boundary=boundary)

    shift_ended = not shift['is_open'] or now >= scheduled_end(shift)
    if not shift_ended:
        return False
    cutoff = scheduled_end(shift) if shift['is_open'] else now
    interval = session.clock_intervals.order_by('-clocked_in_at', '-pk').first()
    if interval is None:
        interval = DriverClockInterval.objects.create(
            session=session,
            clocked_in_at=session.start_time,
            clocked_out_at=cutoff,
            clock_out_reason=DriverClockInterval.SCHEDULED,
        )
    mark_assignment_return_pending(
        biker=biker,
        interval=interval,
        cutoff=cutoff,
    )
    return False


def reconcile_all_drivers(now=None):
    now = now or timezone.now()
    today = timezone.localdate(now)
    sessions = BikerDailySession.objects.filter(date__lte=today).select_related('biker')
    closed = 0
    for session in sessions.iterator():
        if session.date == today:
            closed += reconcile_driver(session.biker, now)
        else:
            with transaction.atomic():
                locked = BikerDailySession.objects.select_for_update().get(pk=session.pk)
                shift = effective_shift(locked.biker, locked.date)
                if locked.is_active:
                    boundary = scheduled_end(shift) if shift['is_open'] else now
                    closed += clock_out(locked, now=now, reason=DriverClockInterval.SCHEDULED, boundary=boundary)
                else:
                    cutoff = scheduled_end(shift) if shift['is_open'] else now
                    interval = locked.clock_intervals.order_by('-clocked_in_at', '-pk').first()
                    if interval is None:
                        interval = DriverClockInterval.objects.create(
                            session=locked,
                            clocked_in_at=locked.start_time,
                            clocked_out_at=cutoff,
                            clock_out_reason=DriverClockInterval.SCHEDULED,
                        )
                    mark_assignment_return_pending(
                        biker=locked.biker,
                        interval=interval,
                        cutoff=cutoff,
                    )
    from apps.vehicles.models import VehicleAssignment
    from apps.users.models import Biker

    current_session_biker_ids = BikerDailySession.objects.filter(
        date=today,
    ).values_list("biker_id", flat=True)
    unclocked_driver_ids = VehicleAssignment.objects.filter(
        released_at__isnull=True,
        finish_mileage_required=False,
    ).values_list("driver_id", flat=True).distinct()
    for biker in Biker.objects.filter(pk__in=unclocked_driver_ids).exclude(
        pk__in=current_session_biker_ids
    ):
        reconcile_driver(biker, now)
    return closed
