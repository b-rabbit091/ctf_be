# dashboard/views.py
from typing import Dict, List, Set

from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from challenges.models import Challenge, Contest
from submissions.models import SubmissionStatus, UserFlagSubmission, UserTextSubmission
from users.models import User


class DashboardOverviewView(APIView):
    """
    Returns a LeetCode-like dashboard summary for the *authenticated* user.

    Security:
      - Requires authentication.
      - Ignores any client-supplied user_id; always uses request.user.
      - Only admins could be extended to view others' dashboards (not enabled here).
    """

    permission_classes = [IsAuthenticated]

    def get_solved_challenge_ids(
        self,
        user: User,
        question_type: str | None = None,
    ) -> Set[int]:
        """
        Return a set of challenge IDs that the user has solved
        (based on SubmissionStatus.status == 'solved').

        If question_type is provided ('practice' or 'competition'),
        limit to challenges of that type.
        """
        base_filter = Q(user=user) & Q(status__status__iexact="solved")
        if question_type:
            base_filter &= Q(challenge__question_type=question_type)

        flag_ids = UserFlagSubmission.objects.filter(base_filter).values_list("challenge_id", flat=True).distinct()
        text_ids = UserTextSubmission.objects.filter(base_filter).values_list("challenge_id", flat=True).distinct()
        return set(flag_ids).union(set(text_ids))

    def get_attempted_challenge_ids(
        self,
        user: User,
        question_type: str | None = None,
    ) -> Set[int]:
        """
        Return a set of challenge IDs that the user has *attempted* (any submission),
        regardless of correctness.
        """
        base_filter = Q(user=user)
        if question_type:
            base_filter &= Q(challenge__question_type=question_type)

        flag_ids = UserFlagSubmission.objects.filter(base_filter).values_list("challenge_id", flat=True).distinct()
        text_ids = UserTextSubmission.objects.filter(base_filter).values_list("challenge_id", flat=True).distinct()
        return set(flag_ids).union(set(text_ids))

    def get_recent_submissions(self, user: User, limit: int = 10) -> List[Dict]:
        """
        Return a unified list of recent submissions (flag + text) for the user,
        sorted by submitted_at desc.

        Each item:
          - id: int
          - type: "flag" | "text"
          - challenge_id
          - challenge_title
          - question_type ("practice" | "competition")
          - contest_id (or None)
          - contest_name (or None)
          - status: e.g. "solved", "wrong", ...
          - submitted_at: ISO timestamp
        """
        flag_qs = UserFlagSubmission.objects.filter(user=user).select_related("challenge", "contest", "status").order_by("-submitted_at")[:limit]
        text_qs = UserTextSubmission.objects.filter(user=user).select_related("challenge", "contest", "status").order_by("-submitted_at")[:limit]

        items: List[Dict] = []

        for s in flag_qs:
            items.append(
                {
                    "id": s.id,
                    "type": "flag",
                    "challenge_id": s.challenge_id,
                    "challenge_title": s.challenge.title if s.challenge else None,
                    "question_type": s.challenge.question_type if s.challenge else None,
                    "contest_id": s.contest_id,
                    "contest_name": s.contest.name if s.contest else None,
                    "status": s.status.status if s.status else None,
                    "submitted_at": s.submitted_at,
                }
            )

        for s in text_qs:
            items.append(
                {
                    "id": s.id,
                    "type": "text",
                    "challenge_id": s.challenge_id,
                    "challenge_title": s.challenge.title if s.challenge else None,
                    "question_type": s.challenge.question_type if s.challenge else None,
                    "contest_id": s.contest_id,
                    "contest_name": s.contest.name if s.contest else None,
                    "status": s.status.status if s.status else None,
                    "submitted_at": s.submitted_at,
                }
            )

        # Sort in Python by submitted_at desc and slice to limit
        items.sort(key=lambda x: x["submitted_at"], reverse=True)
        return items[:limit]

    def get_contest_buckets(self) -> Dict[str, List[Dict]]:
        """
        Return contests grouped as ongoing / upcoming / recent_past.

        This is global, not user-specific (similar to LeetCode showing global contests).
        """
        now = timezone.now()

        ongoing_qs = Contest.objects.filter(
            is_active=True,
            start_time__lte=now,
            end_time__gt=now,
        ).order_by("end_time")

        upcoming_qs = Contest.objects.filter(
            is_active=True,
            start_time__gt=now,
        ).order_by("start_time")[:10]

        recent_past_qs = Contest.objects.filter(
            end_time__lte=now,
        ).order_by("-end_time")[:10]

        def serialize_contest(c: Contest) -> Dict:
            return {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "description": c.description,
                "contest_type": c.contest_type,
                "start_time": c.start_time,
                "end_time": c.end_time,
                "is_active": c.is_active,
            }

        return {
            "ongoing": [serialize_contest(c) for c in ongoing_qs],
            "upcoming": [serialize_contest(c) for c in upcoming_qs],
            "recent_past": [serialize_contest(c) for c in recent_past_qs],
        }

    def get_difficulty_breakdown(
        self,
        challenge_ids: Set[int],
    ) -> Dict[str, int]:
        """
        Return dict like { "Easy": 10, "Medium": 4, "Hard": 2, "Unknown": 1 }
        for the given challenge IDs.
        """
        if not challenge_ids:
            return {
                "Easy": 0,
                "Medium": 0,
                "Hard": 0,
                "Unknown": 0,
            }

        qs = Challenge.objects.filter(id__in=challenge_ids).values(level=F("difficulty__level")).annotate(count=Count("id"))

        result = {
            "Easy": 0,
            "Medium": 0,
            "Hard": 0,
            "Unknown": 0,
        }

        for row in qs:
            level = row["level"] or "Unknown"
            key = level.capitalize()
            if key not in result:
                key = "Unknown"
            result[key] += row["count"]

        return result

    def get_category_breakdown(
        self,
        solved_ids: Set[int],
    ) -> List[Dict]:
        """
        Return list of { category: "Arrays", solved_count: 5 } for solved challenges.
        """
        if not solved_ids:
            return []

        qs = (
            Challenge.objects.filter(id__in=solved_ids)
            .values("category__id", "category__name")
            .annotate(solved_count=Count("id"))
            .order_by("-solved_count")
        )

        return [
            {
                "category_id": row["category__id"],
                "category": row["category__name"],
                "solved_count": row["solved_count"],
            }
            for row in qs
        ]

    def get(self, request, *args, **kwargs):
        user: User = request.user  # always from auth; never from client input

        # --- USER BASICS ---
        user_payload = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.name if user.role else None,
            "is_admin": bool(getattr(user, "is_admin", lambda: False)()),
            "is_student": bool(getattr(user, "is_student", lambda: False)()),
            "date_joined": user.date_joined,
        }

        # --- SOLVED / ATTEMPTED CHALLENGES ---
        practice_solved_ids = self.get_solved_challenge_ids(user, question_type="practice")
        competition_solved_ids = self.get_solved_challenge_ids(user, question_type="competition")
        all_solved_ids = practice_solved_ids.union(competition_solved_ids)

        practice_attempted_ids = self.get_attempted_challenge_ids(user, question_type="practice")
        competition_attempted_ids = self.get_attempted_challenge_ids(user, question_type="competition")
        all_attempted_ids = practice_attempted_ids.union(competition_attempted_ids)

        # --- DIFFICULTY BREAKDOWN ---
        practice_difficulty = self.get_difficulty_breakdown(practice_solved_ids)
        competition_difficulty = self.get_difficulty_breakdown(competition_solved_ids)

        # --- CATEGORY BREAKDOWN (all solved) ---
        category_breakdown = self.get_category_breakdown(all_solved_ids)

        # --- RECENT SUBMISSIONS ---
        recent_submissions = self.get_recent_submissions(user, limit=12)

        # --- CONTEST BUCKETS ---
        contests = self.get_contest_buckets()

        # --- FINAL PAYLOAD ---
        payload = {
            "user": user_payload,
            "practice_stats": {
                "total_solved": len(practice_solved_ids),
                "total_attempted": len(practice_attempted_ids),
                "difficulty": practice_difficulty,
                "solved_challenge_ids": list(practice_solved_ids),
            },
            "competition_stats": {
                "total_solved": len(competition_solved_ids),
                "total_attempted": len(competition_attempted_ids),
                "difficulty": competition_difficulty,
                "solved_challenge_ids": list(competition_solved_ids),
            },
            "overall_stats": {
                "total_solved": len(all_solved_ids),
                "total_attempted": len(all_attempted_ids),
                "category_breakdown": category_breakdown,
            },
            "recent_submissions": [
                {
                    "id": s["id"],
                    "type": s["type"],
                    "challenge_id": s["challenge_id"],
                    "challenge_title": s["challenge_title"],
                    "question_type": s["question_type"],
                    "contest_id": s["contest_id"],
                    "contest_name": s["contest_name"],
                    "status": s["status"],
                    "submitted_at": s["submitted_at"],
                }
                for s in recent_submissions
            ],
            "contests": contests,
        }

        return Response(payload, status=status.HTTP_200_OK)


# dashboard/views.py
from django.contrib.auth import get_user_model
from rest_framework.views import APIView

from .permissions import IsAdminOnly

User = get_user_model()


class AdminDashboardTotalsView(APIView):
    """
    Admin-only overview of global totals for dashboard cards.
    Read-only, safe to expose to admin frontend.
    """

    permission_classes = [IsAdminOnly]

    def get(self, request, *args, **kwargs):
        now = timezone.now()

        # --- Users ---
        total_users = User.objects.count()
        total_students = User.objects.filter(role__name__iexact="student").count()
        total_admins = User.objects.filter(role__name__iexact="admin").count()

        # --- Challenges ---
        total_challenges = Challenge.objects.count()
        total_practice_challenges = Challenge.objects.filter(question_type="practice").count()
        total_competition_challenges = Challenge.objects.filter(question_type="competition").count()

        # --- Contests ---
        total_contests = Contest.objects.count()
        active_contests = Contest.objects.filter(
            is_active=True,
            start_time__lte=now,
            end_time__gt=now,
        ).count()
        upcoming_contests = Contest.objects.filter(
            is_active=True,
            start_time__gt=now,
        ).count()
        ended_contests = Contest.objects.filter(Q(is_active=False) | Q(end_time__lte=now)).count()

        # --- Submissions ---
        total_flag_submissions = UserFlagSubmission.objects.count()
        total_text_submissions = UserTextSubmission.objects.count()
        total_submissions = total_flag_submissions + total_text_submissions

        solved_status = SubmissionStatus.objects.filter(status__iexact="solved").first()
        if solved_status:
            solved_flag = UserFlagSubmission.objects.filter(status=solved_status).count()
            solved_text = UserTextSubmission.objects.filter(status=solved_status).count()
            solved_submissions = solved_flag + solved_text
        else:
            solved_submissions = 0

        distinct_submitters = (
            UserFlagSubmission.objects.values("user_id").distinct().count() + UserTextSubmission.objects.values("user_id").distinct().count()
        )

        payload = {
            "users": {
                "total_users": total_users,
                "total_students": total_students,
                "total_admins": total_admins,
            },
            "challenges": {
                "total_challenges": total_challenges,
                "total_practice_challenges": total_practice_challenges,
                "total_competition_challenges": total_competition_challenges,
            },
            "contests": {
                "total_contests": total_contests,
                "active_contests": active_contests,
                "upcoming_contests": upcoming_contests,
                "ended_contests": ended_contests,
            },
            "submissions": {
                "total_submissions": total_submissions,
                "total_flag_submissions": total_flag_submissions,
                "total_text_submissions": total_text_submissions,
                "solved_submissions": solved_submissions,
                "distinct_submitters": distinct_submitters,
            },
        }

        return Response(payload, status=status.HTTP_200_OK)
