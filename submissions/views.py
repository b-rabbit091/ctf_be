from rest_framework import viewsets
from submissions.models import Submission
from submissions.serializers import SubmissionSerializer
from submissions.permissions import IsOwnerOrAdmin
from rest_framework.permissions import IsAuthenticated

class SubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = SubmissionSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return Submission.objects.all()
        return Submission.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
