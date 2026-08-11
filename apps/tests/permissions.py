from rest_framework import permissions


class IsContentManagerOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow Content Managers and Admins to manage and publish tests without separate approval.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if superuser, staff, or role is ADMIN or CONTENT_MANAGER
        user = request.user
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True

        role = getattr(user, 'role', None)
        if role in ['ADMIN', 'CONTENT_MANAGER', 'admin', 'content_manager']:
            return True

        return False


class IsContentManagerOrReadOnly(permissions.BasePermission):
    """
    Allows read-only access to published tests for students/users,
    while full write/publish access is restricted to Content Managers and Admins.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True

        role = getattr(user, 'role', None)
        return role in ['ADMIN', 'CONTENT_MANAGER', 'admin', 'content_manager']
