from rest_framework.permissions import BasePermission
from django.contrib.auth.models import User


class IsStaff(BasePermission):

    def has_permission(self, request, view):
        staff_users = User.objects.filter(staff__isnull=False)
        return request.user.is_authenticated and request.user in  staff_users
