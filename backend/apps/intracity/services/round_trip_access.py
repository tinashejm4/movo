from django.db.models import Q

from apps.users.models import Staff

from ..models import RoundTripOrder


def is_round_trip_staff(user):
    return user.is_staff or Staff.objects.filter(user=user).exists()


def visible_round_trips(user):
    if is_round_trip_staff(user):
        return RoundTripOrder.objects.all()
    return RoundTripOrder.objects.filter(
        Q(sender__user=user) | Q(recipient__user=user) | Q(biker__user=user)
    ).distinct()
