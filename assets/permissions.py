from rest_framework.permissions import SAFE_METHODS, BasePermission

from .roles import is_it_staff


class IsITStaff(BasePermission):
    """Only admins and IT Staff."""

    def has_permission(self, request, view):
        return is_it_staff(request.user)


class IsITStaffOrReadOnly(BasePermission):
    """Any logged in user can read, only IT staff can change things."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.method in SAFE_METHODS or is_it_staff(request.user)


class TicketPermission(BasePermission):
    """Employees can read their tickets and raise new ones. Staff can do everything."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_it_staff(request.user):
            return True
        return request.method in SAFE_METHODS or request.method == "POST"
