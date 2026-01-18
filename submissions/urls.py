from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ChallengeSubmissionViewSet,
    FlagSubmissionViewSet,
    LeaderboardViewSet,
    PreviousSubmissionsAPIView,
    ReportViewSet,
    TextSubmissionViewSet,
)

router = DefaultRouter()

router.register(r"flag-submissions", FlagSubmissionViewSet, basename="flag-submission")
router.register(r"text-submissions", TextSubmissionViewSet, basename="text-submission")
urlpatterns = [
    path("<int:pk>/", ChallengeSubmissionViewSet.as_view({"post": "create"}), name="challenge-submit"),
    path("previous-submissions/<int:challenge_id>/", PreviousSubmissionsAPIView.as_view(), name="previous-challenge-submissions"),
    path("leaderboard/", LeaderboardViewSet.as_view({"get": "list"}), name="leaderboard"),
    path(
        "reports/generate/",
        ReportViewSet.as_view({"post": "generate"}),
        name="reports-generate",
    ),
    path("", include(router.urls)),
]
