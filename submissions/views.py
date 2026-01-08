from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from challenges.models import Challenge
from .models import UserFlagSubmission, UserTextSubmission
from rest_framework.views import APIView
from .permissions import IsOwnerOrAdmin

from .serializers import FlagSubmissionSerializer, TextSubmissionSerializer, ChallengeSubmissionSerializer


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


class PreviousSubmissionsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, challenge_id):
        user = request.user
        try:
            challenge = Challenge.objects.get(id=challenge_id)
        except Challenge.DoesNotExist:
            return Response({"detail": "Challenge not found"}, status=404)

        flag_submissions = UserFlagSubmission.objects.filter(user=user, challenge=challenge)
        text_submissions = UserTextSubmission.objects.filter(user=user, challenge=challenge)

        flag_serializer = FlagSubmissionSerializer(flag_submissions, many=True)
        text_serializer = TextSubmissionSerializer(text_submissions, many=True)

        return Response({
            "flag_submissions": flag_serializer.data,
            "text_submissions": text_serializer.data
        })


from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from challenges.models import Challenge


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

        serializer = ChallengeSubmissionSerializer(
            data=request.data,
            context={"request": request, "challenge": challenge},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(result, status=status.HTTP_201_CREATED)


from collections import defaultdict
from django.contrib.auth import get_user_model
from django.db.models import Count, Max
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from challenges.models import Contest
from submissions.models import UserFlagSubmission, UserTextSubmission  # adjust import

User = get_user_model()


class LeaderboardViewSet(APIView):
    """
    GET /api/leaderboard/?mode=practice
    GET /api/leaderboard/?mode=competition&contest_id=1
    GET /api/leaderboard/?mode=competition               -> ALL contests (contest IS NOT NULL)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mode = (request.query_params.get("mode") or "practice").strip().lower()
        contest_id = request.query_params.get("contest_id")
        contest_slug = request.query_params.get("contest_slug")

        if mode not in {"practice", "competition"}:
            return Response({"error": "mode must be 'practice' or 'competition'."}, status=400)

        contest = None
        if contest_id:
            contest = Contest.objects.filter(id=contest_id).first()
            if not contest:
                return Response({"error": "Contest not found."}, status=404)
        elif contest_slug:
            contest = Contest.objects.filter(slug=contest_slug).first()
            if not contest:
                return Response({"error": "Contest not found."}, status=404)

        # ✅ Core rule
        # practice  -> contest IS NULL
        # competition:
        #    - specific contest -> contest = that contest
        #    - ALL contests     -> contest IS NOT NULL
        if mode == "practice":
            contest_filter = {"contest__isnull": True}
        else:
            if contest is not None:
                contest_filter = {"contest": contest}
            else:
                contest_filter = {"contest__isnull": False}  # ALL contests (not practice)

        solved_filter = {
            **contest_filter,
            "status__status__iexact": "solved",
        }

        # We will bucket by (user_id, contest_id) for competition.
        # For practice, contest_id will be None so it's effectively (user_id, None).
        def bucket_key(uid, cid):
            return f"{uid}|{cid if cid is not None else 'null'}"

        # ---- Collect solved pairs (distinct user, contest, challenge) ----
        flag_pairs = (
            UserFlagSubmission.objects.filter(**solved_filter)
            .values_list("user_id", "contest_id", "challenge_id")
            .distinct()
        )
        text_pairs = (
            UserTextSubmission.objects.filter(**solved_filter)
            .values_list("user_id", "contest_id", "challenge_id")
            .distinct()
        )

        solved_by_bucket = defaultdict(set)  # key -> set(challenge_id)
        bucket_meta = {}  # key -> (user_id, contest_id)

        for uid, cid, ch_id in flag_pairs:
            k = bucket_key(uid, cid)
            solved_by_bucket[k].add(ch_id)
            bucket_meta[k] = (uid, cid)

        for uid, cid, ch_id in text_pairs:
            k = bucket_key(uid, cid)
            solved_by_bucket[k].add(ch_id)
            bucket_meta[k] = (uid, cid)

        if not solved_by_bucket:
            return Response({"mode": mode, "contest": _contest_obj(contest), "results": []})

        # ---- Users & contests maps ----
        user_ids = list({bucket_meta[k][0] for k in solved_by_bucket.keys()})
        contest_ids = list({bucket_meta[k][1] for k in solved_by_bucket.keys() if bucket_meta[k][1] is not None})

        users = User.objects.filter(id__in=user_ids).only("id", "username", "email")
        user_map = {u.id: u for u in users}

        contests = Contest.objects.filter(id__in=contest_ids).only("id", "name", "slug")
        contest_map = {c.id: c for c in contests}

        # ---- last_solved_at (tie-breaker) per bucket ----
        # We approximate with Max(submitted_at) among SOLVED submissions for that bucket.
        # (Works well for "last submission" display too.)
        flag_last = (
            UserFlagSubmission.objects.filter(**solved_filter)
            .values("user_id", "contest_id")
            .annotate(last=Max("submitted_at"), flag_submissions=Count("id"))
        )
        text_last = (
            UserTextSubmission.objects.filter(**solved_filter)
            .values("user_id", "contest_id")
            .annotate(last=Max("submitted_at"), text_submissions=Count("id"))
        )

        stats = defaultdict(lambda: {"last_solved_at": None, "flag_submissions": 0, "text_submissions": 0})

        for row in flag_last:
            uid, cid = row["user_id"], row["contest_id"]
            k = bucket_key(uid, cid)
            stats[k]["flag_submissions"] = row["flag_submissions"] or 0
            stats[k]["last_solved_at"] = row["last"]

        for row in text_last:
            uid, cid = row["user_id"], row["contest_id"]
            k = bucket_key(uid, cid)
            stats[k]["text_submissions"] = row["text_submissions"] or 0
            if stats[k]["last_solved_at"] is None or (row["last"] and row["last"] > stats[k]["last_solved_at"]):
                stats[k]["last_solved_at"] = row["last"]

        # ---- Build rows ----
        rows = []
        for k, solved_set in solved_by_bucket.items():
            uid, cid = bucket_meta[k]
            u = user_map.get(uid)
            if not u:
                continue

            c_name = None
            if cid is not None:
                cobj = contest_map.get(cid)
                c_name = (cobj.name if cobj else f"Contest #{cid}")

            rows.append(
                {
                    "user": {"id": u.id, "username": u.username, "email": getattr(u, "email", None)},
                    "contest_id": cid,
                    "contest_name": c_name,
                    "solved": len(solved_set),
                    "flag_submissions": stats[k]["flag_submissions"],
                    "text_submissions": stats[k]["text_submissions"],
                    "last_solved_at": stats[k]["last_solved_at"],
                }
            )

        # ---- Sort & rank ----
        rows.sort(
            key=lambda r: (
                -r["solved"],
                r["last_solved_at"] or "9999-12-31T00:00:00Z",
                (r["user"]["username"] or "").lower(),
            )
        )
        for i, r in enumerate(rows, start=1):
            r["rank"] = i

        return Response({"mode": mode, "contest": _contest_obj(contest), "results": rows})


def _contest_obj(contest):
    if not contest:
        return None
    return {"id": contest.id, "slug": contest.slug, "name": contest.name}
