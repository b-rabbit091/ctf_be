from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    ChallengeViewSet,
    ContestViewSet,
    DifficultyViewSet,
    SolutionTypes,
)

router = DefaultRouter()
router.register(r"challenges", ChallengeViewSet, basename="challenges")
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"difficulties", DifficultyViewSet, basename="difficulties")
router.register(r"solution-types", SolutionTypes, basename="solution-types")
router.register(r"contests", ContestViewSet, basename="contests")

urlpatterns = [
    path("", include(router.urls)),
]
