# users/permissions.py
from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """
    Allows access only to admin users.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin()


class IsStudentUser(BasePermission):
    """
    Allows access only to student users.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_student()


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level permission: owners can access their own data; admin can access all.
    """

    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and (obj == request.user or request.user.is_admin())
