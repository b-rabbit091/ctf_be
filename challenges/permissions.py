from rest_framework.permissions import BasePermission


class IsAdminOrReadOnly(BasePermission):
    """
    Admin can create/edit/delete; Students can only read.
    """

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.is_authenticated
        return request.user.is_authenticated and request.user.is_admin()


class IsAdminOnly(BasePermission):
    """
    Only authenticated admins can access.
    No write allowed for non-admins, but this view will only support GET anyway.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and hasattr(request.user, "is_admin") and request.user.is_admin()
