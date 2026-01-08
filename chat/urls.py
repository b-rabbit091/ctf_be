# chat/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import PracticeChatView, ChatThreadViewSet

router = DefaultRouter()
router.register(r"thread", ChatThreadViewSet, basename="chat-thread")

urlpatterns = [
    path("practice/", PracticeChatView.as_view(), name="chat-practice"),
    path("", include(router.urls)),
]
