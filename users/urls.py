from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminInviteViewSet,
    MyTokenObtainPairView,
    UserGroupViewSet,
    UserViewSet,
    VerifyEmailView,
)

router = DefaultRouter()
router.register(r"groups", UserGroupViewSet, basename="user-group")
router.register(r"", UserViewSet, basename="users")
router.register(r"admin-invite", AdminInviteViewSet, basename="admin-invite")

urlpatterns = [
    # JWT authentication
    path("token/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Student email verification
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
]

# Include router URLs
urlpatterns += router.urls
