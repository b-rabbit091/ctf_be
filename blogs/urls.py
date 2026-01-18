from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BlogViewSet

router = DefaultRouter()
router.register(r"", BlogViewSet, basename="blogs")

urlpatterns = [
    path("", include(router.urls)),
]
