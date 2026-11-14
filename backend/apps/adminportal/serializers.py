from rest_framework import serializers, status

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
    minutes_before_close = serializers.IntegerField(
        min_value=1,
        max_value=120,
        help_text="Minutes before the effective shift end when the warning is sent.",
    )


class WeeklyShiftResponseSerializer(ShiftFieldsSerializer):
    weekday = serializers.IntegerField(
        min_value=0,
        max_value=6,
        help_text="Day of week where Monday is 0 and Sunday is 6.",
    )


class DetailResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    code = serializers.CharField(required=False)


class DriverShiftCheckResponseSerializer(serializers.Serializer):
    in_bounds = serializers.BooleanField()
    status = serializers.ChoiceField(choices=('ended', 'not_started', 'active'))


class DriverShiftValidationErrorSerializer(serializers.Serializer):
    minutes_before_close = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    is_open = serializers.ListField(child=serializers.CharField(), required=False)
    start_time = serializers.ListField(child=serializers.CharField(), required=False)
    end_time = serializers.ListField(child=serializers.CharField(), required=False)
    date = serializers.ListField(child=serializers.CharField(), required=False)
    non_field_errors = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    detail = serializers.CharField(required=False)

