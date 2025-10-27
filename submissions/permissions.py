from rest_framework.permissions import BasePermission

class IsOwnerOrAdmin(BasePermission):
    """
    Students can see their own submissions; Admins can see all.
    """
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and (obj.user == request.user or request.user.is_admin())
