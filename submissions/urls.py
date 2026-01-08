from django.urls import path, include
from .views import PreviousSubmissionsAPIView, FlagSubmissionViewSet, TextSubmissionViewSet, ChallengeSubmissionViewSet, \
    LeaderboardViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

router.register(r"flag-submissions", FlagSubmissionViewSet, basename="flag-submission")
router.register(r"text-submissions", TextSubmissionViewSet, basename="text-submission")
urlpatterns = [
    path("<int:pk>/", ChallengeSubmissionViewSet.as_view({"post": "create"}), name="challenge-submit"),

    path('previous-submissions/<int:challenge_id>/', PreviousSubmissionsAPIView.as_view(),
         name='previous-challenge-submissions'),
    path("leaderboard/", LeaderboardViewSet.as_view(), name="leaderboard"),

    path('', include(router.urls)),

]
