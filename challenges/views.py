from rest_framework import viewsets, permissions, status
from .models import Challenge, Category, Difficulty, SolutionType
from .permissions import IsAdminOrReadOnly
from .serializers import ChallengeDetailSerializer, ChallengeListSerializer, CategorySerializer, \
    DifficultySerializer, SolutionTypeSerializer, ChallengeUpdateSerializer, ChallengeCreateSerializer
from rest_framework.response import Response


class ChallengeViewSet(viewsets.ModelViewSet):
    queryset = Challenge.objects.all().order_by('-created_at')
    serializer_class = ChallengeListSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ChallengeDetailSerializer
        return ChallengeListSerializer

    def get_queryset(self):
        queryset = Challenge.objects.all().order_by('-created_at')
        q_type = self.request.query_params.get("type")
        category = self.request.query_params.get("category")
        difficulty = self.request.query_params.get("difficulty")

        if q_type in ["practice", "competition"]:
            queryset = queryset.filter(question_type=q_type)
        if category:
            queryset = queryset.filter(category=category)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        return queryset

    def create(self, request, *args, **kwargs):
        """Allow only admin to create challenge"""
        if not request.user.is_admin:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = ChallengeCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Allow only admin to update challenge"""
        if not request.user.is_admin:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )

        partial = kwargs.pop('partial', True)  # allow partial updates
        instance = self.get_object()
        serializer = ChallengeUpdateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]


class DifficultyViewSet(viewsets.ModelViewSet):
    queryset = Difficulty.objects.all()
    serializer_class = DifficultySerializer
    permission_classes = [IsAdminOrReadOnly]


class SolutionTypes(viewsets.ModelViewSet):
    queryset = SolutionType.objects.all()
    serializer_class = SolutionTypeSerializer
    permission_classes = [IsAdminOrReadOnly]
