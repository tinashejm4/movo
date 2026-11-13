from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.intracity.services.package_assignment import is_biker_busy
from apps.notifications.models import Notification
from apps.users.models import Biker, Branch, Staff
from apps.vehicles.models import MileageRecord, Vehicle, VehicleAssignment

from .models import BikerDailySession, DriverClockInterval, DriverShiftException, DriverShiftReminderSetting, WeeklyDriverShift
from .shift_service import effective_shift, reconcile_all_drivers


class DriverShiftTests(APITestCase):
    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 10, 2, 10))
        self.clock = patch('django.utils.timezone.now', return_value=self.now)
        self.mock_now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.driver_user = User.objects.create_user(username='shift-driver')
        self.biker = Biker.objects.create(user=self.driver_user)
        self.staff_user = User.objects.create_user(username='shift-staff')
        branch = Branch.objects.create(name='Shift branch', address='Street')
        Staff.objects.create(user=self.staff_user, branch=branch, position='Manager')
        self.activation = reverse('activate_deactivate')

    def set_time(self, hour, minute=0):
        self.now = timezone.make_aware(datetime(2026, 10, 2, hour, minute))
        self.mock_now.return_value = self.now

    def test_weekly_defaults_and_exception_precedence(self):
        self.assertEqual(WeeklyDriverShift.objects.count(), 7)
        today = timezone.localdate()
        shift = effective_shift(self.biker, today)
        self.assertEqual((shift['start_time'], shift['end_time']), (time(8), time(17)))
        tomorrow = today + timedelta(days=1)
        WeeklyDriverShift.objects.filter(weekday=tomorrow.weekday()).update(is_open=False, start_time=None, end_time=None)
        self.assertFalse(effective_shift(self.biker, tomorrow)['is_open'])
        DriverShiftException.objects.create(biker=self.biker, date=tomorrow, is_open=True, start_time=time(9), end_time=time(13))
        self.assertEqual(effective_shift(self.biker, tomorrow)['end_time'], time(13))
        self.assertEqual(effective_shift(self.biker, tomorrow + timedelta(days=7))['is_open'], False)

    def test_activation_boundaries_and_interval_history(self):
        self.client.force_authenticate(user=self.driver_user)
        self.set_time(7, 59)
        self.assertEqual(self.client.patch(self.activation, {'is_biker_activated': True}).status_code, 400)
        self.set_time(8)
        self.assertEqual(self.client.patch(self.activation, {'is_biker_activated': True}).status_code, 200)
        self.set_time(10)
        self.client.patch(self.activation, {'is_biker_activated': False})
        self.set_time(11)
        self.client.patch(self.activation, {'is_biker_activated': True})
        self.set_time(17)
        self.assertEqual(self.client.patch(self.activation, {'is_biker_activated': True}).status_code, 400)
        session = BikerDailySession.objects.get(biker=self.biker)
        self.assertFalse(session.is_active)
        intervals = list(session.clock_intervals.order_by('clocked_in_at'))
        self.assertEqual(len(intervals), 2)
        self.assertEqual([i.clock_out_reason for i in intervals], ['manual', 'scheduled'])
        self.assertEqual(intervals[1].clocked_out_at, self.now)

    def test_scheduler_and_dispatch_guard(self):
        self.client.force_authenticate(user=self.driver_user)
        self.client.patch(self.activation, {'is_biker_activated': True})
        self.assertFalse(is_biker_busy(self.biker))
        self.set_time(17)
        self.assertTrue(is_biker_busy(self.biker))
        self.assertEqual(reconcile_all_drivers(), 1)
        self.assertEqual(reconcile_all_drivers(), 0)
        self.assertFalse(BikerDailySession.objects.get(biker=self.biker).is_active)

    def test_manual_deactivation_keeps_assignment_until_effective_shift_end(self):
        vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="SHIFT 01",
            make="Honda",
            model="XR150",
        )
        start = MileageRecord.objects.create(
            vehicle=vehicle,
            odometer_km=100,
            recorded_at=self.now,
            source=MileageRecord.Source.ASSIGNMENT_START,
        )
        assignment = VehicleAssignment.objects.create(
            vehicle=vehicle,
            driver=self.biker,
            assigned_at=self.now,
            start_mileage_record=start,
        )
        self.client.force_authenticate(user=self.driver_user)
        self.client.patch(self.activation, {"is_biker_activated": True})
        self.set_time(10)
        self.client.patch(self.activation, {"is_biker_activated": False})
        self.set_time(11)
        self.assertEqual(
            self.client.patch(self.activation, {"is_biker_activated": True}).status_code,
            200,
        )
        assignment.refresh_from_db()
        self.assertFalse(assignment.finish_mileage_required)
        self.assertIsNone(assignment.released_at)
        self.client.patch(self.activation, {"is_biker_activated": False})
        assignment.refresh_from_db()
        self.assertFalse(assignment.finish_mileage_required)
        self.assertIsNone(assignment.released_at)

        DriverShiftException.objects.create(
            biker=self.biker,
            date=self.now.date(),
            is_open=True,
            start_time=time(8),
            end_time=time(12, 30),
        )
        self.set_time(12, 29)
        reconcile_all_drivers()
        assignment.refresh_from_db()
        self.assertFalse(assignment.finish_mileage_required)
        self.set_time(12, 30)
        reconcile_all_drivers()
        assignment.refresh_from_db()
        self.assertTrue(assignment.finish_mileage_required)
        notice = Notification.objects.get(event_type="shift.closed", user=self.driver_user)
        self.assertIn("finish mileage", notice.body.lower())

    def test_assignment_without_clock_session_becomes_pending_at_shift_end(self):
        vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="SHIFT 02",
            make="Honda",
            model="XR150",
        )
        start = MileageRecord.objects.create(
            vehicle=vehicle,
            odometer_km=200,
            recorded_at=self.now,
            source=MileageRecord.Source.ASSIGNMENT_START,
        )
        assignment = VehicleAssignment.objects.create(
            vehicle=vehicle,
            driver=self.biker,
            assigned_at=self.now,
            start_mileage_record=start,
        )
        self.set_time(17)
        reconcile_all_drivers()
        assignment.refresh_from_db()
        self.assertTrue(assignment.finish_mileage_required)
        self.assertEqual(Notification.objects.filter(
            user=self.driver_user,
            event_type="shift.closed",
        ).count(), 1)

    def test_historical_closed_session_does_not_mark_todays_assignment_pending(self):
        vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="SHIFT 03",
            make="Honda",
            model="XR150",
        )
        start = MileageRecord.objects.create(
            vehicle=vehicle,
            odometer_km=300,
            recorded_at=self.now,
            source=MileageRecord.Source.ASSIGNMENT_START,
        )
        assignment = VehicleAssignment.objects.create(
            vehicle=vehicle,
            driver=self.biker,
            assigned_at=self.now,
            start_mileage_record=start,
        )
        previous_day = self.now.date() - timedelta(days=1)
        WeeklyDriverShift.objects.filter(weekday=previous_day.weekday()).update(
            is_open=False,
            start_time=None,
            end_time=None,
        )
        old_session_start = timezone.make_aware(datetime.combine(previous_day, time(8)))
        old_session = BikerDailySession.objects.create(
            biker=self.biker,
            date=previous_day,
            start_time=old_session_start,
            end_time=old_session_start + timedelta(hours=1),
            is_active=False,
        )
        DriverClockInterval.objects.create(
            session=old_session,
            clocked_in_at=old_session_start,
            clocked_out_at=old_session.end_time,
            clock_out_reason=DriverClockInterval.MANUAL,
        )

        self.set_time(14, 48)
        reconcile_all_drivers()

        assignment.refresh_from_db()
        self.assertFalse(assignment.finish_mileage_required)
        self.assertEqual(
            Notification.objects.filter(event_type="shift.closed").count(),
            0,
        )

    def test_scheduler_still_closes_stale_active_sessions_from_previous_days(self):
        previous_day = self.now.date() - timedelta(days=1)
        session_start = timezone.make_aware(datetime.combine(previous_day, time(8)))
        session = BikerDailySession.objects.create(
            biker=self.biker,
            date=previous_day,
            start_time=session_start,
            is_active=True,
        )
        interval = DriverClockInterval.objects.create(
            session=session,
            clocked_in_at=session_start,
        )

        self.assertEqual(reconcile_all_drivers(), 1)

        session.refresh_from_db()
        interval.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertEqual(interval.clock_out_reason, DriverClockInterval.SCHEDULED)
        self.assertEqual(interval.clocked_out_at, timezone.make_aware(datetime.combine(previous_day, time(17))))

    def test_reconciliation_clears_same_day_pending_flag_before_shift_end(self):
        vehicle = Vehicle.objects.create(
            vehicle_type=Vehicle.Type.MOTORCYCLE,
            registration_number="SHIFT 04",
            make="Honda",
            model="XR150",
        )
        start = MileageRecord.objects.create(
            vehicle=vehicle,
            odometer_km=400,
            recorded_at=self.now,
            source=MileageRecord.Source.ASSIGNMENT_START,
        )
        assignment = VehicleAssignment.objects.create(
            vehicle=vehicle,
            driver=self.biker,
            assigned_at=self.now,
            start_mileage_record=start,
            finish_mileage_required=True,
        )
        self.set_time(14, 48)

        from .shift_service import reconcile_driver

        reconcile_driver(self.biker)

        assignment.refresh_from_db()
        self.assertFalse(assignment.finish_mileage_required)

    def test_staff_api_and_immediate_early_close(self):
        self.client.force_authenticate(user=self.driver_user)
        self.client.patch(self.activation, {'is_biker_activated': True})
        self.assertEqual(self.client.get(reverse('admin_driver_shifts')).status_code, 403)
        self.client.force_authenticate(user=self.staff_user)
        self.assertEqual(len(self.client.get(reverse('admin_driver_shifts')).data), 7)
        exception_url = reverse('admin_driver_shift_exceptions', args=[self.driver_user.id])
        self.assertEqual(self.client.post(exception_url, {
            'date': '2026-10-02', 'is_open': True, 'start_time': '08:00', 'end_time': '09:00',
        }).status_code, 201)
        session = BikerDailySession.objects.get(biker=self.biker)
        self.assertFalse(session.is_active)
        self.assertEqual(session.clock_intervals.get().clock_out_reason, DriverClockInterval.SCHEDULED)
        self.assertEqual(effective_shift(self.biker, timezone.localdate())['end_time'], time(9))
        self.assertEqual(self.client.post(exception_url, {
            'date': '2026-10-02', 'is_open': True, 'start_time': '08:00', 'end_time': '09:00',
        }).status_code, 400)
        delete_url = reverse('admin_driver_shift_exception_detail', args=[self.driver_user.id, '2026-10-02'])
        self.assertEqual(self.client.put(delete_url, {
            'is_open': True, 'start_time': '08:00', 'end_time': '13:00',
        }).status_code, 200)
        self.assertEqual(effective_shift(self.biker, timezone.localdate())['end_time'], time(13))
        self.assertEqual(self.client.delete(delete_url).status_code, 204)
        self.assertEqual(effective_shift(self.biker, timezone.localdate())['end_time'], time(17))

    def test_closed_day_and_invalid_hours(self):
        self.client.force_authenticate(user=self.staff_user)
        weekly_url = reverse('admin_driver_shift_detail', args=[4])
        self.assertEqual(self.client.put(weekly_url, {'is_open': True, 'start_time': '17:00', 'end_time': '08:00'}).status_code, 400)
        self.assertEqual(self.client.put(weekly_url, {'is_open': False, 'start_time': None, 'end_time': None}, format='json').status_code, 200)
        self.client.force_authenticate(user=self.driver_user)
        self.assertEqual(self.client.patch(self.activation, {'is_biker_activated': True}).status_code, 400)

    def test_weekly_edit_closes_active_driver_immediately(self):
        self.client.force_authenticate(user=self.driver_user)
        self.client.patch(self.activation, {'is_biker_activated': True})
        self.client.force_authenticate(user=self.staff_user)
        weekly_url = reverse('admin_driver_shift_detail', args=[4])
        response = self.client.put(weekly_url, {
            'is_open': True, 'start_time': '08:00', 'end_time': '09:00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BikerDailySession.objects.get(biker=self.biker).is_active)
        self.assertTrue(is_biker_busy(self.biker))

    def test_warning_once_then_closing_alert_once(self):
        other_user = User.objects.create_user(username='off-shift-driver')
        Biker.objects.create(user=other_user)
        self.client.force_authenticate(user=self.driver_user)
        self.client.patch(self.activation, {'is_biker_activated': True})
        self.set_time(16, 29)
        reconcile_all_drivers()
        self.assertFalse(Notification.objects.exists())
        self.set_time(16, 30)
        reconcile_all_drivers()
        reconcile_all_drivers()
        self.assertEqual(list(Notification.objects.values_list('event_type', flat=True)), ['shift.closing_soon'])
        self.set_time(17)
        reconcile_all_drivers()
        reconcile_all_drivers()
        self.assertEqual(
            list(Notification.objects.order_by('id').values_list('event_type', flat=True)),
            ['shift.closing_soon', 'shift.closed'],
        )
        self.assertFalse(Notification.objects.filter(user=other_user).exists())

    def test_late_clock_in_manual_off_and_changed_cutoff(self):
        self.client.force_authenticate(user=self.staff_user)
        reminder_url = reverse('admin_driver_shift_reminder')
        self.assertEqual(self.client.get(reminder_url).data, {'minutes_before_close': 30})
        self.assertEqual(self.client.put(reminder_url, {'minutes_before_close': 0}).status_code, 400)
        self.assertEqual(self.client.put(reminder_url, {'minutes_before_close': 121}).status_code, 400)
        self.assertEqual(self.client.put(reminder_url, {'minutes_before_close': 15}).status_code, 200)
        self.assertEqual(DriverShiftReminderSetting.objects.get(pk=1).minutes_before_close, 15)
        self.set_time(16, 50)
        self.client.force_authenticate(user=self.driver_user)
        self.client.patch(self.activation, {'is_biker_activated': True})
        reconcile_all_drivers()
        self.assertEqual(Notification.objects.filter(event_type='shift.closing_soon').count(), 1)
        self.client.patch(self.activation, {'is_biker_activated': False})
        self.set_time(17)
        reconcile_all_drivers()
        self.assertEqual(Notification.objects.filter(event_type='shift.closed').count(), 1)
        self.assertEqual(Notification.objects.count(), 2)

    def test_cutoff_edit_can_issue_new_warning_and_immediate_close_skips_warning(self):
        self.client.force_authenticate(user=self.driver_user)
        self.client.patch(self.activation, {'is_biker_activated': True})
        self.set_time(16, 35)
        reconcile_all_drivers()
        self.client.force_authenticate(user=self.staff_user)
        weekly_url = reverse('admin_driver_shift_detail', args=[4])
        self.client.put(weekly_url, {'is_open': True, 'start_time': '08:00', 'end_time': '16:50'})
        self.assertEqual(Notification.objects.filter(event_type='shift.closing_soon').count(), 2)
        self.client.put(weekly_url, {'is_open': True, 'start_time': '08:00', 'end_time': '16:30'})
        self.assertEqual(Notification.objects.filter(event_type='shift.closing_soon').count(), 2)
        self.assertEqual(Notification.objects.filter(event_type='shift.closed').count(), 1)

    def test_reminder_setting_requires_staff(self):
        self.client.force_authenticate(user=self.driver_user)
        url = reverse('admin_driver_shift_reminder')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.put(url, {'minutes_before_close': 15}).status_code, 403)
