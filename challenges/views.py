from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import Category, Challenge, Contest, Difficulty, SolutionType
from .permissions import IsAdminOnly, IsAdminOrReadOnly
from .serializers import (
    CategorySerializer,
    ChallengeDetailSerializer,
    ChallengeListSerializer,
    ChallengeUpdateSerializer,
    ContestCreateSerializer,
    ContestSerializer,
    DifficultySerializer,
    SolutionTypeSerializer,
)


class ChallengeViewSet(viewsets.ModelViewSet):
    queryset = Challenge.objects.all().order_by("-created_at")
    serializer_class = ChallengeListSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {"id": ["in"]}

    def get_serializer_class(self):
        # list view
        if self.action == "retrieve":
            return ChallengeDetailSerializer
        if self.action in ["create", "update", "partial_update"]:
            return ChallengeUpdateSerializer
        return ChallengeListSerializer

    def get_queryset(self):
        queryset = Challenge.objects.all().order_by("-created_at")

        q_type = self.request.query_params.get("type")
        category = self.request.query_params.get("category")
        difficulty = self.request.query_params.get("difficulty")

        if q_type == "competition":
            # must be linked to at least one contest
            queryset = queryset.filter(
                question_type="competition",
                contests__isnull=False,
            ).distinct()

        elif q_type == "practice":
            queryset = queryset.filter(question_type="practice")

        elif q_type == "N/A":
            # optional: explicitly fetch unassigned questions
            queryset = queryset.filter(
                question_type="N/A",
                contests__isnull=True,
            )

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

    @action(detail=False, methods=["patch"], url_path="bulk-update")
    def bulk_update(self, request, *args, **kwargs):
        if not getattr(request.user, "is_admin", False):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "ids must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ids = [int(i) for i in ids]
        except (TypeError, ValueError):
            return Response({"detail": "ids must contain integers."}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(id__in=ids)
        found_ids = list(qs.values_list("id", flat=True))
        found_set = set(found_ids)

        missing = [i for i in ids if i not in found_set]
        if missing:
            return Response({"detail": f"Some ids were not found: {missing}"}, status=status.HTTP_404_NOT_FOUND)

        # NOTE: your rule says: if contest_id is null OR not sent => remove from contests
        contest_id = request.data.get("contest_id", None)
        question_type = request.data.get("question_type", None)

        allowed_qtypes = {"N/A", "practice", "competition", None}
        if question_type not in allowed_qtypes:
            return Response({"detail": "Invalid question_type."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # ---- contest assignment / removal ----
            if contest_id is None:
                # Remove these challenges from ALL contests (delete join-table rows)
                through = Contest.challenges.through
                deleted, _ = through.objects.filter(challenge_id__in=found_ids).delete()
            else:
                # Assign these challenges to the specified contest
                try:
                    contest_id_int = int(contest_id)
                except (TypeError, ValueError):
                    return Response({"detail": "contest_id must be an integer or null."}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    contest = Contest.objects.select_for_update().get(id=contest_id_int)
                except Contest.DoesNotExist:
                    return Response({"detail": "contest_id not found."}, status=status.HTTP_404_NOT_FOUND)

                contest.challenges.add(*found_ids)

            # ---- question_type update ----
            if question_type is not None:
                qs.update(question_type=question_type)

        return Response(
            {
                "success": True,
                "updated_ids": ids,
                "contest_id": contest_id,
                "question_type": question_type,
            },
            status=status.HTTP_200_OK,
        )

    # @action(detail=False, methods=["patch"], url_path="bulk-update")
    # def bulk_update(self, request, *args, **kwargs):
    #     """
    #     Bulk partial update for challenges (Admin-only).
    #     Supports contest assignment + question_type change without breaking single update().
    #     Payload:
    #       {
    #         "ids": [14, 15, 16],
    #         "contest_id": 1,                 // optional
    #         "question_type": "competition"   // optional
    #       }
    #     """
    #     if not getattr(request.user, "is_admin", False):
    #         return Response(
    #             {"detail": "You do not have permission to perform this action."},
    #             status=status.HTTP_403_FORBIDDEN,
    #         )
    #
    #     ids = request.data.get("ids", [])
    #     if not isinstance(ids, list) or not ids:
    #         return Response({"detail": "ids must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)
    #
    #     qs = self.get_queryset().filter(id__in=ids)
    #     found_ids = set(qs.values_list("id", flat=True))
    #     missing = [i for i in ids if i not in found_ids]
    #     if missing:
    #         return Response({"detail": f"Some ids were not found: {missing}"}, status=status.HTTP_404_NOT_FOUND)
    #
    #     contest_id = request.data.get("contest_id", None)
    #     question_type = request.data.get("question_type", None)
    #
    #     # Only allow these question types via bulk (tighten security)
    #     allowed_qtypes = {"N/A", "practice", "competition", None}
    #     if question_type not in allowed_qtypes:
    #         return Response({"detail": "Invalid question_type."}, status=status.HTTP_400_BAD_REQUEST)
    #
    #     with transaction.atomic():
    #         contest = None
    #         if contest_id is not None:
    #             try:
    #                 contest = Contest.objects.get(id=contest_id)
    #             except Contest.DoesNotExist:
    #                 return Response({"detail": "contest_id not found."}, status=status.HTTP_404_NOT_FOUND)
    #
    #             # Add selected challenges into contest
    #             contest.challenges.add(*list(found_ids))
    #
    #         # 2) Update question_type if provided
    #         if question_type is not None:
    #             qs.update(question_type=question_type)
    #
    #     return Response(
    #         {
    #             "success": True,
    #             "updated_ids": ids,
    #             "contest_id": contest_id,
    #             "question_type": question_type,
    #         },
    #         status=status.HTTP_200_OK,
    #     )

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


# views.py


class ContestViewSet(viewsets.ModelViewSet):
    queryset = Contest.objects.all().order_by("-created_at")
    serializer_class = ContestSerializer
    permission_classes = [IsAdminOnly]

    def get_serializer_class(self):
        if self.action == "create":
            return ContestCreateSerializer
        return ContestSerializer

    # your create/list overrides can remain or be removed (permission already covers)
    def create(self, request, *args, **kwargs):
        if not getattr(request.user, "is_admin", False):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        if not getattr(request.user, "is_admin", False):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        """
        PATCH /api/challenges/contests/<contest_id>/
        Payload:
          {"challenges": [23, 24]}
        Meaning:
          remove these challenge ids from THIS contest only (delete M2M join rows)
        """
        if not getattr(request.user, "is_admin", False):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        contest = self.get_object()

        if not isinstance(request.data, dict):
            return Response({"detail": "Invalid payload. Expected an object."}, status=status.HTTP_400_BAD_REQUEST)

        # challenges = ids to REMOVE
        remove_ids = request.data.get("challenges", None)

        # Don't let serializer treat "challenges" as replace
        payload = dict(request.data)
        payload.pop("challenges", None)

        # Update other fields normally (if any)
        if payload:
            serializer = self.get_serializer(contest, data=payload, partial=True)
            serializer.is_valid(raise_exception=True)
            contest = serializer.save()

        if remove_ids is None:
            # nothing to remove; just return updated contest
            return Response(self.get_serializer(contest).data, status=status.HTTP_200_OK)

        if not isinstance(remove_ids, list):
            return Response({"detail": "challenges must be a list of integers."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            remove_ids = [int(x) for x in remove_ids]
        except (TypeError, ValueError):
            return Response({"detail": "challenges must be a list of integers."}, status=status.HTTP_400_BAD_REQUEST)

        if not remove_ids:
            return Response(self.get_serializer(contest).data, status=status.HTTP_200_OK)

        # Optional (fast) existence check (prevents junk IDs; still one query)
        existing = set(Challenge.objects.filter(id__in=remove_ids).values_list("id", flat=True))
        missing = [i for i in remove_ids if i not in existing]
        if missing:
            return Response({"detail": f"Some challenge ids were not found: {missing}"}, status=status.HTTP_404_NOT_FOUND)

        through = Contest.challenges.through
        deleted, _ = through.objects.filter(
            contest_id=contest.id,
            challenge_id__in=remove_ids,
        ).delete()

        Challenge.objects.filter(id__in=remove_ids, contests__isnull=True).update(question_type="N/A")

        return Response(
            {
                "success": True,
                "contest_id": contest.id,
                "contest": self.get_serializer(contest).data,
            },
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        if not getattr(request.user, "is_admin", False):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        contest = self.get_object()

        # capture attached challenge ids BEFORE delete
        attached_ids = list(contest.challenges.values_list("id", flat=True))

        # delete contest (auto-clears M2M join rows for this contest)
        contest.delete()

        # any challenge that is now in ZERO contests => set to N/A
        if attached_ids:
            Challenge.objects.filter(id__in=attached_ids, contests__isnull=True).update(question_type="N/A")

        return Response(status=status.HTTP_204_NO_CONTENT)
