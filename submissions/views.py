from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from challenges.models import Challenge
from .models import UserFlagSubmission, UserTextSubmission
from .serializers import UserFlagSubmissionSerializer, UserTextSubmissionSerializer
from rest_framework.views import APIView


class UserFlagSubmissionViewSet(viewsets.ModelViewSet):
    queryset = UserFlagSubmission.objects.all()
    serializer_class = UserFlagSubmissionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['user_id'] = request.user.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class UserTextSubmissionViewSet(viewsets.ModelViewSet):
    queryset = UserTextSubmission.objects.all()
    serializer_class = UserTextSubmissionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['user_id'] = request.user.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PreviousSubmissionsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, challenge_id):
        user = request.user
        try:
            challenge = Challenge.objects.get(id=challenge_id)
        except Challenge.DoesNotExist:
            return Response({"detail": "Challenge not found"}, status=404)

        flag_submissions = UserFlagSubmission.objects.filter(user=user, challenges=challenge)
        text_submissions = UserTextSubmission.objects.filter(user=user, challenges=challenge)

        flag_serializer = UserFlagSubmissionSerializer(flag_submissions, many=True)
        text_serializer = UserTextSubmissionSerializer(text_submissions, many=True)

        return Response({
            "flag_submissions": flag_serializer.data,
            "text_submissions": text_serializer.data
        })
