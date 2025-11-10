from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChallengeViewSet, CategoryViewSet, DifficultyViewSet, SolutionTypes

router = DefaultRouter()
router.register(r'challenges', ChallengeViewSet, basename='challenges')
router.register(r'categories', CategoryViewSet, basename='categories')
router.register(r'difficulties', DifficultyViewSet, basename='difficulties')
router.register(r'solution-types', SolutionTypes, basename='solution-types')

urlpatterns = [
    path('', include(router.urls)),
]
