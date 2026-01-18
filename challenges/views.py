from rest_framework import permissions, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import Category, Challenge, Contest, Difficulty, SolutionType
from .permissions import IsAdminOrReadOnly
from .serializers import (
    CategorySerializer,
    ChallengeDetailSerializer,
    ChallengeListSerializer,
    ChallengeUpdateSerializer,
    ContestSerializer,
    DifficultySerializer,
    SolutionTypeSerializer,
)


class ChallengeViewSet(viewsets.ModelViewSet):
    queryset = Challenge.objects.all().order_by("-created_at")
    serializer_class = ChallengeListSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        # list view
        if self.action == "retrieve":
            return ChallengeDetailSerializer
        if self.action in ["create", "update", "partial_update"]:
            return ChallengeUpdateSerializer
        return ChallengeListSerializer

    def get_queryset(self):
        """
        Optionally filter by type, category, or difficulty
        """
        queryset = Challenge.objects.all().order_by("-created_at")
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

    # ---- create ----------------------------------------------------

    def create(self, request, *args, **kwargs):
        if not getattr(request.user, "is_admin", False):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ChallengeUpdateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        challenge = serializer.save(author=request.user)

        return Response(
            ChallengeDetailSerializer(challenge).data,
            status=status.HTTP_201_CREATED,
        )

    # ---- update / partial_update -----------------------------------

    def update(self, request, *args, **kwargs):
        """
        Full update. Admin-only. Handles both practice & competition.
        """
        if not getattr(request.user, "is_admin", False):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = ChallengeUpdateSerializer(
            instance,
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        challenge = serializer.save()

        return Response(ChallengeDetailSerializer(challenge).data)

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH – same logic as update but partial=True.
        """
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


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


class ContestViewSet(viewsets.ModelViewSet):
    queryset = Contest.objects.all()
    serializer_class = ContestSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = Contest.objects.all()

        if self.action in {"list", "retrieve"}:
            qs = qs.filter(publish_result=True)

        return qs
