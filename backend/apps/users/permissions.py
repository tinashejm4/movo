from rest_framework.permissions import BasePermission

from .models import Staff


class IsStaff(BasePermission):

    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.is_active:
            return False
        return Staff.objects.filter(user_id=request.user.id).exists()
