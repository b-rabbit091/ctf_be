from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAuthenticatedReadOnly(BasePermission):
    """
    Allows only authenticated users to read data (GET/HEAD/OPTIONS).
    Blocks all write operations (POST, PUT, PATCH, DELETE) for everyone.
    """

    def has_permission(self, request, view):
        # Must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False

        # Only allow read-only methods
        return request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        # Same rule applies for object-level access
        return self.has_permission(request, view)


class IsOwnerOrAdminReadOnly(BasePermission):
    """
    Allows users to read their own objects and admins to read any object.
    Disallows all write operations unless manually overridden in the view.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Only read-only allowed
        if request.method in SAFE_METHODS:
            # Admin can read anything
            if hasattr(request.user, "is_admin") and request.user.is_admin():
                return True

            # Owner can read their own items
            if hasattr(obj, "user"):
                return obj.user == request.user

            # Fallback: read allowed
            return True

        # No write access
        return False


class IsAdminOrReadOnly(BasePermission):
    """
    Admins can POST/PUT/PATCH/DELETE.
    Students/Users can only read.
    """

    def has_permission(self, request, view):
        # Allow GET, HEAD, OPTIONS for all authenticated users
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated

        # Only admins can write
        return request.user.is_authenticated and hasattr(request.user, "is_admin") and request.user.is_admin()


# dashboard/permissions.py


class IsAdminOnly(BasePermission):
    """
    Only authenticated admins can access.
    No write allowed for non-admins, but this view will only support GET anyway.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and hasattr(request.user, "is_admin") and request.user.is_admin()
