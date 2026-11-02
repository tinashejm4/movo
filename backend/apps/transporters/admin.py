from django.contrib import admin
from .models import (
    BikerDailySession,
    DriverClockInterval,
    DriverShiftException,
    DriverShiftReminderSetting,
    WeeklyDriverShift,
)

admin.site.register([
    BikerDailySession,
    WeeklyDriverShift,
    DriverShiftException,
    DriverClockInterval,
    DriverShiftReminderSetting,
])
