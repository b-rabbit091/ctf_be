from rest_framework.routers import DefaultRouter
from .views import ChallengeViewSet

router = DefaultRouter()
router.register(r'challenges', ChallengeViewSet, basename='challenges')

urlpatterns = router.urls
