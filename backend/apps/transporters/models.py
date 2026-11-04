from django.db import models

from apps.users.models import Biker
from apps.bookkeeping.models import Asset


# Create your models here.
class BikerDailySession(models.Model):
    biker = models.ForeignKey(Biker, on_delete=models.CASCADE, related_name='daily_sessions')
    date = models.DateField()
    start_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    end_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('biker', 'date')

    def __str__(self):
        return f'{self.biker.user.username} - {self.date}'


class WeeklyDriverShift(models.Model):
    weekday = models.PositiveSmallIntegerField(unique=True)  # Monday = 0
    is_open = models.BooleanField(default=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)


class DriverShiftException(models.Model):
    biker = models.ForeignKey(Biker, on_delete=models.CASCADE, related_name='shift_exceptions')
    date = models.DateField()
    is_open = models.BooleanField(default=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['biker', 'date'], name='unique_driver_shift_exception')]


class DriverClockInterval(models.Model):
    MANUAL = 'manual'
    SCHEDULED = 'scheduled'
    CLOCK_OUT_REASONS = [(MANUAL, 'Manual'), (SCHEDULED, 'Scheduled')]

    session = models.ForeignKey(BikerDailySession, on_delete=models.CASCADE, related_name='clock_intervals')
    clocked_in_at = models.DateTimeField()
    clocked_out_at = models.DateTimeField(null=True, blank=True)
    clock_out_reason = models.CharField(max_length=10, choices=CLOCK_OUT_REASONS, null=True, blank=True)


class DriverShiftReminderSetting(models.Model):
    minutes_before_close = models.PositiveSmallIntegerField(default=30)


class Vehicle(models.Model):
    VEHICLE_TYPES = [
        ('car', 'Car'),
        ('truck', 'Truck'),
        ('scooter', 'Scooter'),
        ('motorcycle', 'Motorcycle'),
        ('tricycle', 'Tricycle')
    ]

    vehicle_type = models.CharField(max_length=50, choices=VEHICLE_TYPES)
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    license_plate = models.CharField(max_length=20, unique=True)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='vehicles')

    def __str__(self):
        return f'{self.make} {self.model} ({self.license_plate})'

class MileageRecord(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='mileage_records')
    mileage = models.PositiveIntegerField()
    added_at = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ('vehicle', 'added_at')

    def __str__(self):
        return f'{self.vehicle} - {self.added_at} - {self.mileage}'