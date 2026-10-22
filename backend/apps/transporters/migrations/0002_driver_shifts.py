import datetime

import django.db.models.deletion
from django.db import migrations, models


def seed_weekly_shifts(apps, schema_editor):
    shift = apps.get_model('transporters', 'WeeklyDriverShift')
    shift.objects.bulk_create([
        shift(weekday=day, is_open=True, start_time=datetime.time(8), end_time=datetime.time(17))
        for day in range(7)
    ])


def backfill_intervals(apps, schema_editor):
    session_model = apps.get_model('transporters', 'BikerDailySession')
    interval = apps.get_model('transporters', 'DriverClockInterval')
    interval.objects.bulk_create([
        interval(
            session_id=session.id,
            clocked_in_at=session.start_time,
            clocked_out_at=session.end_time if not session.is_active else None,
            clock_out_reason='manual' if session.end_time and not session.is_active else None,
        )
        for session in session_model.objects.filter(is_active=True) | session_model.objects.filter(end_time__isnull=False)
    ])


class Migration(migrations.Migration):
    dependencies = [('transporters', '0001_initial')]

    operations = [
        migrations.CreateModel(name='WeeklyDriverShift', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('weekday', models.PositiveSmallIntegerField(unique=True)),
            ('is_open', models.BooleanField(default=True)),
            ('start_time', models.TimeField(blank=True, null=True)),
            ('end_time', models.TimeField(blank=True, null=True)),
        ]),
        migrations.CreateModel(name='DriverShiftException', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('date', models.DateField()),
            ('is_open', models.BooleanField(default=True)),
            ('start_time', models.TimeField(blank=True, null=True)),
            ('end_time', models.TimeField(blank=True, null=True)),
            ('biker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shift_exceptions', to='users.biker')),
        ], options={'constraints': [models.UniqueConstraint(fields=('biker', 'date'), name='unique_driver_shift_exception')]}),
        migrations.CreateModel(name='DriverClockInterval', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('clocked_in_at', models.DateTimeField()),
            ('clocked_out_at', models.DateTimeField(blank=True, null=True)),
            ('clock_out_reason', models.CharField(blank=True, choices=[('manual', 'Manual'), ('scheduled', 'Scheduled')], max_length=10, null=True)),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clock_intervals', to='transporters.bikerdailysession')),
        ]),
        migrations.RunPython(seed_weekly_shifts, migrations.RunPython.noop),
        migrations.RunPython(backfill_intervals, migrations.RunPython.noop),
    ]
