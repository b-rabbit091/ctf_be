from __future__ import annotations

from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from challenges.models import Challenge
from .models import UserFlagSubmission, UserTextSubmission
from rest_framework.views import APIView
from .permissions import IsOwnerOrAdmin

from .serializers import FlagSubmissionSerializer, TextSubmissionSerializer, ChallengeSubmissionSerializer, \
    GroupChallengeSubmissionSerializer, GroupFlagSubmissionSerializer, GroupTextSubmissionSerializer

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from challenges.models import Challenge
from collections import defaultdict
from django.contrib.auth import get_user_model
from django.db.models import Max
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from challenges.models import Contest
from submissions.models import UserFlagSubmission, UserTextSubmission

User = get_user_model()
class FlagSubmissionViewSet(viewsets.ModelViewSet):
    """
    API for flag submissions.

    POST body:
      - challenge_id (required)
      - contest_id (optional; omit or null for practice)
      - value (flag string)

    Backend enforces:
      - auth
      - challenge exists
      - if contest_id set: challenge in contest & time window
      - challenge.solution_type allows flag
      - correctness via FlagSolution
    """

    queryset = UserFlagSubmission.objects.select_related(
        "user", "challenge", "contest", "status"
    ).all()
    serializer_class = FlagSubmissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Admin sees all, others see only their own
        if getattr(user, "role", None) == "admin":
            return qs
        return qs.filter(user=user)

    def perform_create(self, serializer):
        return super().perform_create(serializer)


class TextSubmissionViewSet(viewsets.ModelViewSet):
    """
    API for text submissions.

    POST body:
      - challenge_id (required)
      - contest_id (optional; omit or null for practice)
      - content (text solution)

    Same backend enforcement as flag submissions.
    """

    queryset = UserTextSubmission.objects.select_related(
        "user", "challenge", "contest", "status"
    ).all()
    serializer_class = TextSubmissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "role", None) == "admin":
            return qs
        return qs.filter(user=user)

    def perform_create(self, serializer):
        return super().perform_create(serializer)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied

from challenges.models import Challenge
from submissions.models import (
    UserFlagSubmission, UserTextSubmission,
    GroupFlagSubmission, GroupTextSubmission,
)
from users.models import UserGroup


class PreviousSubmissionsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, challenge_id):
        user = request.user

        try:
            challenge = Challenge.objects.get(id=challenge_id)
        except Challenge.DoesNotExist:
            raise NotFound("Challenge not found")

        # GROUP-ONLY: show only submissions made by the user's own group
        if challenge.group_only:
            try:
                membership = user.group_membership  # related_name='group_membership'
            except UserGroup.DoesNotExist:
                raise PermissionDenied("You must join a group to view submissions for this challenge.")

            group = membership.group

            flag_submissions = (
                GroupFlagSubmission.objects
                .filter(group=group, challenge=challenge)
                .order_by("-submitted_at")
            )
            text_submissions = (
                GroupTextSubmission.objects
                .filter(group=group, challenge=challenge)
                .order_by("-submitted_at")
            )

            return Response({
                "flag_submissions": GroupFlagSubmissionSerializer(flag_submissions, many=True).data,
                "text_submissions": GroupTextSubmissionSerializer(text_submissions, many=True).data,
            })

        # NORMAL: show only submissions made by the user
        flag_submissions = (
            UserFlagSubmission.objects
            .filter(user=user, challenge=challenge)
            .order_by("-submitted_at")
        )
        text_submissions = (
            UserTextSubmission.objects
            .filter(user=user, challenge=challenge)
            .order_by("-submitted_at")
        )

        return Response({
            "flag_submissions": FlagSubmissionSerializer(flag_submissions, many=True).data,
            "text_submissions": TextSubmissionSerializer(text_submissions, many=True).data,
        })




class ChallengeSubmissionViewSet(viewsets.ViewSet):
    """
    POST /api/submission/<challenge_id>/
    Payload: { "value": "...", "content": "..." }
    """
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, pk=None):
        try:
            challenge = Challenge.objects.select_related("solution_type").get(pk=pk)
        except Challenge.DoesNotExist:
            raise NotFound("Challenge not found.")

        # Pick the right serializer based on challenge.group_only
        serializer_class = (
            GroupChallengeSubmissionSerializer
            if getattr(challenge, "group_only", False)
            else ChallengeSubmissionSerializer
        )

        serializer = serializer_class(
            data=request.data,
            context={"request": request, "challenge": challenge},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(result, status=status.HTTP_201_CREATED)



class LeaderboardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class LeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    total_score = serializers.IntegerField()


class LeaderboardResponseSerializer(serializers.Serializer):
    type = serializers.CharField()
    contest = serializers.CharField(allow_null=True)
    results = LeaderboardEntrySerializer(many=True)


class LeaderboardViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = LeaderboardPagination

    def list(self, request, *args, **kwargs):
        try:
            lb_type = (request.query_params.get("mode") or "practice").strip().lower()
            contest_id = (request.query_params.get("contest_id") or "").strip()
            search = (request.query_params.get("search") or "").strip().lower()

            if lb_type not in {"practice", "competition"}:
                return self._error("type must be practice or competition", status.HTTP_400_BAD_REQUEST)

            contest = None
            if lb_type == "competition":
                if not contest_id:
                    return self._error("No contest selected.", status.HTTP_400_BAD_REQUEST)

                contest = Contest.objects.filter(id=contest_id).only("id", "slug", "publish_result").first()
                if not contest:
                    return self._error("Contest not found.", status.HTTP_404_NOT_FOUND)
                if not contest.publish_result:
                    return self._error("Results for this contest are not published yet.", status.HTTP_403_FORBIDDEN)

            rows = self._build_rows(lb_type, contest,search)

            page = self.paginate_queryset(rows)
            if page is not None:
                payload = {
                    "type": lb_type,
                    "contest": contest.slug if contest else None,
                    "results": page,
                }
                return self.get_paginated_response(LeaderboardResponseSerializer(payload).data)

            payload = {
                "type": lb_type,
                "contest": contest.slug if contest else None,
                "results": rows,
            }
            return Response(LeaderboardResponseSerializer(payload).data, status=status.HTTP_200_OK)

        except Exception:
            return self._error("Unable to load leaderboard at this time.", status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _error(self, msg, code):
        return Response({"error": msg}, status=code)

    def _build_rows(self, lb_type, contest,search):
        solved_filter = {
            "challenge__question_type": lb_type,
            "status__status__iexact": "solved",
        }
        if lb_type == "practice":
            solved_filter["contest__isnull"] = True
        else:
            solved_filter["contest"] = contest

        flag_rows = self._best_scores(UserFlagSubmission.objects.filter(**solved_filter))
        text_rows = self._best_scores(UserTextSubmission.objects.filter(**solved_filter))

        best = defaultdict(dict)  # user_id -> {challenge_id: best_score}

        for row in list(flag_rows) + list(text_rows):
            uid = row["user_id"]
            ch_id = row["challenge_id"]
            score = int(row["best_score"] or 0)

            prev = best[uid].get(ch_id)
            if prev is None or score > prev:
                best[uid][ch_id] = score

        totals = {uid: sum(scores.values()) for uid, scores in best.items()}
        if not totals:
            return []

        users = User.objects.filter(id__in=totals.keys()).only("id", "username")
        rows = [{"user_id": u.id, "username": u.username, "total_score": int(totals.get(u.id, 0))} for u in users]

        rows.sort(key=lambda r: (-r["total_score"], (r["username"] or "").lower(), r["user_id"]))

        for i, r in enumerate(rows, start=1):
            r["rank"] = i

        if search:
            rows = [
                r for r in rows
                if search in (r.get("username") or "").lower()
            ]

        return rows

    def _best_scores(self, qs):
        return qs.values("user_id", "challenge_id").annotate(best_score=Max("user_score"))
