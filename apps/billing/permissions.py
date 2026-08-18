from rest_framework import permissions


class IsAdminOrSuperAdmin(permissions.BasePermission):
    """
    Ruxsat faqat ADMIN yoki SUPER_ADMIN foydalanuvchilariga beriladi.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True

        role = str(getattr(user, 'role', '')).upper()
        return role in ['ADMIN', 'SUPER_ADMIN']


class IsSuperAdmin(permissions.BasePermission):
    """
    Ruxsat faqat SUPER_ADMIN foydalanuvchisiga beriladi.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if getattr(user, 'is_superuser', False):
            return True

        role = str(getattr(user, 'role', '')).upper()
        return role == 'SUPER_ADMIN'
