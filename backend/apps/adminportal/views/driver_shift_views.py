from datetime import date

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transporters.models import (
    DriverShiftException,
    DriverShiftReminderSetting,
    WeeklyDriverShift,
)
from apps.transporters.shift_service import reconcile_all_drivers, reconcile_driver
from apps.users.models import Biker
from apps.users.permissions import IsStaff


class ShiftFieldsSerializer(serializers.Serializer):
    is_open = serializers.BooleanField()
    start_time = serializers.TimeField(allow_null=True, required=False)
    end_time = serializers.TimeField(allow_null=True, required=False)

    def validate(self, attrs):
        opened = attrs['is_open']
        start = attrs.get('start_time')
        end = attrs.get('end_time')
        if opened and (start is None or end is None or start >= end):
            raise serializers.ValidationError('Open shifts require start_time before end_time.')
        if not opened and (start is not None or end is not None):
            raise serializers.ValidationError('Closed shifts must have null start_time and end_time.')
        return attrs


class ExceptionSerializer(ShiftFieldsSerializer):
    date = serializers.DateField()


class ReminderSettingSerializer(serializers.Serializer):
    minutes_before_close = serializers.IntegerField(min_value=1, max_value=120)


class DriverShiftReminderView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        setting, _ = DriverShiftReminderSetting.objects.get_or_create(pk=1)
        return Response({'minutes_before_close': setting.minutes_before_close})

    def put(self, request):
        serializer = ReminderSettingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        setting, _ = DriverShiftReminderSetting.objects.get_or_create(pk=1)
        setting.minutes_before_close = serializer.validated_data['minutes_before_close']
        setting.save(update_fields=['minutes_before_close'])
        return Response({'minutes_before_close': setting.minutes_before_close})


def shift_payload(shift):
    return {
        'is_open': shift.is_open,
        'start_time': shift.start_time,
        'end_time': shift.end_time,
    }


class WeeklyShiftsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        return Response([
            {'weekday': shift.weekday, **shift_payload(shift)}
            for shift in WeeklyDriverShift.objects.order_by('weekday')
        ])


class WeeklyShiftDetailView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def put(self, request, weekday):
        shift = get_object_or_404(WeeklyDriverShift, weekday=weekday)
        serializer = ShiftFieldsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(shift, field, value)
        if not shift.is_open:
            shift.start_time = shift.end_time = None
        shift.save()
        if timezone.localdate().weekday() == weekday:
            reconcile_all_drivers()
        return Response({'weekday': weekday, **shift_payload(shift)})


class DriverExceptionsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @staticmethod
    def biker(biker_user_id):
        return get_object_or_404(Biker, user_id=biker_user_id)

    def get(self, request, biker_user_id):
        biker = self.biker(biker_user_id)
        return Response([
            {'date': exception.date, **shift_payload(exception)}
            for exception in biker.shift_exceptions.order_by('date')
        ])

    def post(self, request, biker_user_id):
        biker = self.biker(biker_user_id)
        serializer = ExceptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if DriverShiftException.objects.filter(biker=biker, date=data['date']).exists():
            return Response({'detail': 'An exception already exists for this date.'}, status=status.HTTP_400_BAD_REQUEST)
        exception = DriverShiftException.objects.create(biker=biker, **data)
        if exception.date == timezone.localdate():
            reconcile_driver(biker)
        return Response({'date': exception.date, **shift_payload(exception)}, status=status.HTTP_201_CREATED)


class DriverExceptionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @staticmethod
    def exception(biker_user_id, day):
        try:
            parsed_day = date.fromisoformat(day)
        except ValueError:
            raise Http404('Invalid date')
        return get_object_or_404(DriverShiftException, biker__user_id=biker_user_id, date=parsed_day)

    def put(self, request, biker_user_id, day):
        exception = self.exception(biker_user_id, day)
        serializer = ShiftFieldsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(exception, field, value)
        if not exception.is_open:
            exception.start_time = exception.end_time = None
        exception.save()
        if exception.date == timezone.localdate():
            reconcile_driver(exception.biker)
        return Response({'date': day, **shift_payload(exception)})

    def delete(self, request, biker_user_id, day):
        exception = self.exception(biker_user_id, day)
        biker = exception.biker
        exception.delete()
        if exception.date == timezone.localdate():
            reconcile_driver(biker)
        return Response(status=status.HTTP_204_NO_CONTENT)
