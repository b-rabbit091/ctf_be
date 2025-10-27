from rest_framework import viewsets
from challenges.models import Challenge
from challenges.serializers import ChallengeSerializer
from challenges.permissions import IsAdminOrReadOnly
from rest_framework.permissions import IsAuthenticated

class ChallengeViewSet(viewsets.ModelViewSet):
    queryset = Challenge.objects.all()
    serializer_class = ChallengeSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
