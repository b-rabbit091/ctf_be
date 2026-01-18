from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from challenges.models import Challenge, Contest
from submissions.models import (
    GroupFlagSubmission,
    GroupTextSubmission,
    UserFlagSubmission,
    UserTextSubmission,
)
from users.models import UserGroup
from users.permissions import IsAdminUser

from .models import UserFlagSubmission, UserTextSubmission
from .pagination import LeaderboardPagination
from .permissions import IsOwnerOrAdmin
from .serializers import (
    ChallengeSubmissionSerializer,
    FlagSubmissionSerializer,
    GroupChallengeSubmissionSerializer,
    GroupFlagSubmissionSerializer,
    GroupTextSubmissionSerializer,
    LeaderboardResponseSerializer,
    TextSubmissionSerializer,
)
from .utils import (
    apply_time_window,
    best_score,
    get_solution_label,
    latest_attempt,
    one_correct_solution,
    parse_iso_dt,
    safe_int,
    safe_status_str,
    to_group_entity,
    to_user_entity,
)

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

    queryset = UserFlagSubmission.objects.select_related("user", "challenge", "contest", "status").all()
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

    queryset = UserTextSubmission.objects.select_related("user", "challenge", "contest", "status").all()
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

            flag_submissions = GroupFlagSubmission.objects.filter(group=group, challenge=challenge).order_by("-submitted_at")
            text_submissions = GroupTextSubmission.objects.filter(group=group, challenge=challenge).order_by("-submitted_at")

            return Response(
                {
                    "flag_submissions": GroupFlagSubmissionSerializer(flag_submissions, many=True).data,
                    "text_submissions": GroupTextSubmissionSerializer(text_submissions, many=True).data,
                }
            )

        # NORMAL: show only submissions made by the user
        flag_submissions = UserFlagSubmission.objects.filter(user=user, challenge=challenge).order_by("-submitted_at")
        text_submissions = UserTextSubmission.objects.filter(user=user, challenge=challenge).order_by("-submitted_at")

        return Response(
            {
                "flag_submissions": FlagSubmissionSerializer(flag_submissions, many=True).data,
                "text_submissions": TextSubmissionSerializer(text_submissions, many=True).data,
            }
        )


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
        serializer_class = GroupChallengeSubmissionSerializer if getattr(challenge, "group_only", False) else ChallengeSubmissionSerializer

        serializer = serializer_class(
            data=request.data,
            context={"request": request, "challenge": challenge},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(result, status=status.HTTP_201_CREATED)


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

            rows = self._build_rows(lb_type, contest, search)

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

    def _build_rows(self, lb_type, contest, search):
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
            rows = [r for r in rows if search in (r.get("username") or "").lower()]

        return rows

    def _best_scores(self, qs):
        return qs.values("user_id", "challenge_id").annotate(best_score=Max("user_score"))


# reports/views.py


class ReportViewSet(viewsets.ViewSet):
    """
    SECURITY FIRST:
      - Admin-only: returns correct solutions and full submission contents.
      - Never expose this endpoint to students unless you remove correct solutions + redact user content.

    POST /api/reports/generate/
    body:
      {
        "challenge_id": 123,
        "from": "2026-01-14T00:00:00Z",   # optional
        "to":   "2026-01-17T23:59:59Z"    # optional
      }

    Response format is IDENTICAL for user and group reports:
      {
        "challenge": {...},
        "count": N,
        "rows": [
          {
            "row_id": "user-12" | "group-9",
            "entity_type": "user" | "group",
            "entity": {...},              # user or group object
            "solution_type": "flag|procedure|both",
            "summary": {
              "flag": {...},
              "procedure": {...},
              "total_score": 0
            },
            "see_more": {
              "correct_solution": {...},
              "attempts": {
                "flag": [...],
                "procedure": [...]
              }
            }
          }
        ]
      }
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        challenge_id = request.data.get("challenge_id")
        if not challenge_id:
            raise ValidationError({"challenge_id": "challenge_id is required."})

        dt_from = parse_iso_dt(request.data.get("from"), "from")
        dt_to = parse_iso_dt(request.data.get("to"), "to")

        challenge = get_object_or_404(
            Challenge.objects.select_related("solution_type", "challenge_score"),
            pk=challenge_id,
        )

        sol_label = get_solution_label(challenge)
        if sol_label not in {"flag", "procedure", "flag and procedure"}:
            # strict validation to avoid “unknown = leak something”
            raise ValidationError({"solution_type": f"Unsupported solution_type.type='{sol_label}'. Expected flag/procedure/both."})

        correct = one_correct_solution(challenge)

        rows = self._build_rows_for_challenge(
            challenge=challenge,
            sol_label=sol_label,
            dt_from=dt_from,
            dt_to=dt_to,
            correct_solution=correct,
        )

        return Response(
            {
                "challenge": {
                    "id": challenge.id,
                    "title": challenge.title,
                    "solution_type": sol_label,
                    "group_only": bool(challenge.group_only),
                },
                "count": len(rows),
                "rows": rows,
            },
            status=status.HTTP_200_OK,
        )

    # -------------------------
    # Unified row builder
    # -------------------------
    def _build_rows_for_challenge(
        self,
        *,
        challenge: Challenge,
        sol_label: str,
        dt_from: Optional[timezone.datetime],
        dt_to: Optional[timezone.datetime],
        correct_solution: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if challenge.group_only:
            return self._build_group_rows(
                challenge=challenge,
                sol_label=sol_label,
                dt_from=dt_from,
                dt_to=dt_to,
                correct_solution=correct_solution,
            )
        return self._build_user_rows(
            challenge=challenge,
            sol_label=sol_label,
            dt_from=dt_from,
            dt_to=dt_to,
            correct_solution=correct_solution,
        )

    # -------------------------
    # USER rows
    # -------------------------
    def _build_user_rows(
        self,
        *,
        challenge: Challenge,
        sol_label: str,
        dt_from: Optional[timezone.datetime],
        dt_to: Optional[timezone.datetime],
        correct_solution: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        # Pull only what challenge accepts (avoid unnecessary reads)
        flag_qs = UserFlagSubmission.objects.none()
        proc_qs = UserTextSubmission.objects.none()

        if sol_label in ("flag", "flag and procedure"):
            flag_qs = UserFlagSubmission.objects.select_related("user", "status").filter(challenge=challenge)
            flag_qs = apply_time_window(flag_qs, dt_from, dt_to)

        if sol_label in ("procedure", "flag and procedure"):
            proc_qs = UserTextSubmission.objects.select_related("user", "status").filter(challenge=challenge)
            proc_qs = apply_time_window(proc_qs, dt_from, dt_to)

        # Bucket by user_id
        buckets: Dict[int, Dict[str, Any]] = {}

        def ensure(uid: int, user_obj) -> Dict[str, Any]:
            if uid not in buckets:
                buckets[uid] = {
                    "entity_type": "user",
                    "entity": to_user_entity(user_obj),
                    "flag_attempts": [],
                    "procedure_attempts": [],
                }
            return buckets[uid]

        for s in flag_qs.order_by("submitted_at"):
            b = ensure(s.user_id, s.user)
            b["flag_attempts"].append(
                {
                    "type": "flag",
                    "submitted_at": s.submitted_at,
                    "status": safe_status_str(s.status),
                    "score": safe_int(getattr(s, "user_score", 0), 0),
                    "submitted_value": s.value,
                    "submitted_content": None,
                }
            )

        for s in proc_qs.order_by("submitted_at"):
            b = ensure(s.user_id, s.user)
            b["procedure_attempts"].append(
                {
                    "type": "procedure",
                    "submitted_at": s.submitted_at,
                    "status": safe_status_str(s.status),
                    "score": safe_int(getattr(s, "user_score", 0), 0),
                    "submitted_value": None,
                    "submitted_content": s.content,
                }
            )

        return self._finalize_rows(
            buckets=buckets,
            sol_label=sol_label,
            correct_solution=correct_solution,
            row_prefix="user",
        )

    # -------------------------
    # GROUP rows
    # -------------------------
    def _build_group_rows(
        self,
        *,
        challenge: Challenge,
        sol_label: str,
        dt_from: Optional[timezone.datetime],
        dt_to: Optional[timezone.datetime],
        correct_solution: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        flag_qs = GroupFlagSubmission.objects.none()
        proc_qs = GroupTextSubmission.objects.none()

        if sol_label in ("flag", "flag and procedure"):
            flag_qs = GroupFlagSubmission.objects.select_related("group", "status", "submitted_by").filter(challenge=challenge)
            flag_qs = apply_time_window(flag_qs, dt_from, dt_to)

        if sol_label in ("procedure", "flag and procedure"):
            proc_qs = GroupTextSubmission.objects.select_related("group", "status", "submitted_by").filter(challenge=challenge)
            proc_qs = apply_time_window(proc_qs, dt_from, dt_to)

        # Bucket by group_id
        buckets: Dict[int, Dict[str, Any]] = {}

        def ensure(gid: int, group_obj) -> Dict[str, Any]:
            if gid not in buckets:
                buckets[gid] = {
                    "entity_type": "group",
                    "entity": to_group_entity(group_obj),
                    "flag_attempts": [],
                    "procedure_attempts": [],
                }
            return buckets[gid]

        for s in flag_qs.order_by("submitted_at"):
            b = ensure(s.group_id, s.group)
            b["flag_attempts"].append(
                {
                    "type": "flag",
                    "submitted_at": s.submitted_at,
                    "status": safe_status_str(s.status),
                    "score": safe_int(getattr(s, "group_score", 0), 0),
                    "submitted_value": s.value,
                    "submitted_content": None,
                    "submitted_by": ({"id": s.submitted_by_id, "username": getattr(s.submitted_by, "username", None)} if s.submitted_by_id else None),
                }
            )

        for s in proc_qs.order_by("submitted_at"):
            b = ensure(s.group_id, s.group)
            b["procedure_attempts"].append(
                {
                    "type": "procedure",
                    "submitted_at": s.submitted_at,
                    "status": safe_status_str(s.status),
                    "score": safe_int(getattr(s, "group_score", 0), 0),
                    "submitted_value": None,
                    "submitted_content": s.content,
                    "submitted_by": ({"id": s.submitted_by_id, "username": getattr(s.submitted_by, "username", None)} if s.submitted_by_id else None),
                }
            )

        return self._finalize_rows(
            buckets=buckets,
            sol_label=sol_label,
            correct_solution=correct_solution,
            row_prefix="group",
        )

    # -------------------------
    # Finalize rows (shared)
    # -------------------------
    def _finalize_rows(
        self,
        *,
        buckets: Dict[int, Dict[str, Any]],
        sol_label: str,
        correct_solution: Dict[str, Any],
        row_prefix: str,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []

        for entity_id, b in buckets.items():
            flag_attempts: List[Dict[str, Any]] = b.get("flag_attempts", [])
            proc_attempts: List[Dict[str, Any]] = b.get("procedure_attempts", [])

            # Best per type
            best_flag = best_score(flag_attempts) if sol_label in ("flag", "flag and procedure") else 0
            best_proc = best_score(proc_attempts) if sol_label in ("procedure", "flag and procedure") else 0

            # Latest per type (so admin can see what happened most recently per channel)
            latest_flag = latest_attempt(flag_attempts) if flag_attempts else None
            latest_proc = latest_attempt(proc_attempts) if proc_attempts else None

            # Compute “overall latest” across both lists for sorting and table date
            overall_latest = None
            candidates = [x for x in [latest_flag, latest_proc] if x is not None]
            if candidates:
                overall_latest = max(candidates, key=lambda a: a.get("submitted_at") or timezone.now())

            total = safe_int(best_flag, 0) + safe_int(best_proc, 0)

            rows.append(
                {
                    "row_id": f"{row_prefix}-{entity_id}",
                    "entity_type": b["entity_type"],
                    "entity": b["entity"],
                    "solution_type": sol_label,
                    # Table-friendly summary (separate scores)
                    "summary": {
                        "flag": {
                            "best_score": best_flag,
                            "latest_status": (latest_flag or {}).get("status"),
                            "latest_submitted_at": (latest_flag or {}).get("submitted_at"),
                        },
                        "procedure": {
                            "best_score": best_proc,
                            "latest_status": (latest_proc or {}).get("status"),
                            "latest_submitted_at": (latest_proc or {}).get("submitted_at"),
                        },
                        "total_score": total,
                        "date": (overall_latest or {}).get("submitted_at"),  # keep one date column for table
                    },
                    # See more: correct + full attempts with per-attempt score
                    "see_more": {
                        "correct_solution": correct_solution,  # ADMIN ONLY
                        "attempts": {
                            "flag": sorted(flag_attempts, key=lambda a: a["submitted_at"], reverse=True),
                            "procedure": sorted(proc_attempts, key=lambda a: a["submitted_at"], reverse=True),
                        },
                    },
                }
            )

        # Sort by overall latest date desc
        rows.sort(key=lambda r: r.get("summary", {}).get("date") or timezone.now(), reverse=True)
        return rows
