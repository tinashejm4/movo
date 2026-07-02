from rest_framework.permissions import BasePermission
from django.contrib.auth.models import User


class IsStaff(BasePermission):

    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.is_active:
            return False
        return User.objects.filter(id=request.user.id, staff__isnull=False).exists()
