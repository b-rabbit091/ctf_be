# chat/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatThreadViewSet, PracticeChatView

router = DefaultRouter()
router.register(r"thread", ChatThreadViewSet, basename="chat-thread")

urlpatterns = [
    path("practice/", PracticeChatView.as_view(), name="chat-practice"),
    path("", include(router.urls)),
]
