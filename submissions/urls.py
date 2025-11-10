from django.urls import path
from .views import PreviousSubmissionsAPIView

urlpatterns = [
    path('previous-submissions/<int:challenge_id>/', PreviousSubmissionsAPIView.as_view(), name='previous-challenge-submissions'),
]
