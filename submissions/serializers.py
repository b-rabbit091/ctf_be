from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from challenges.models import Challenge, Contest, FlagSolution, TextSolution
from submissions.llm import call_coach_llm
from submissions.models import (
    GroupFlagSubmission,
    GroupTextSubmission,
    SubmissionStatus,
    UserFlagSubmission,
    UserTextSubmission,
)
from users.models import UserGroup

from . import utils
from .utils import SolutionUtils


class BaseSubmissionSerializer(serializers.ModelSerializer):
    """
    Shared validation logic for both flag and text submissions.
    Handles:
      - challenge_id
      - optional contest_id
      - time window enforcement
      - solution_type constraints
    """

    challenge_id = serializers.IntegerField(write_only=True)
    contest_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    # read-only fields we return to the client
    challenge = serializers.CharField(source="challenge.title", read_only=True)
    submitted_at = serializers.DateTimeField(read_only=True)
    status_display = serializers.CharField(
        source="status.status",  # uses your SubmissionStatus.status
        read_only=True,
    )

    class Meta:
        abstract = True

    def _get_challenge_and_contest(self, attrs):
        # 1. Challenge
        challenge_id = attrs.get("challenge_id")
        challenge = get_object_or_404(Challenge, pk=challenge_id)

        # 2. Optional contest
        contest_id = attrs.get("contest_id")
        contest = None
        now = timezone.now()

        if contest_id is not None:
            contest = get_object_or_404(Contest, pk=contest_id)

            # Ensure challenge is part of this contest
            if not contest.challenges.filter(pk=challenge.pk).exists():
                raise serializers.ValidationError(
                    {"contest_id": "This challenge is not part of the specified contest."})

            # Enforce time window for competition submissions
            if not (contest.start_time <= now <= contest.end_time):
                raise serializers.ValidationError(
                    {"contest_id": "This contest is not accepting submissions at this time."})

        return challenge, contest

    def _get_status_for_result(self, is_correct: bool) -> SubmissionStatus:
        """
        Map correctness to a SubmissionStatus instance.
        Uses your SubmissionStatus(status, description).
        We'll create two default statuses if they don't exist:
          - status="correct"
          - status="incorrect"
        """
        if is_correct:
            status_value = "correct"
            desc = "User submitted a correct solution."
        else:
            status_value = "incorrect"
            desc = "User submitted an incorrect solution."

        status_obj, _ = SubmissionStatus.objects.get_or_create(
            status=status_value,
            defaults={"description": desc},
        )
        return status_obj


class FlagSubmissionSerializer(BaseSubmissionSerializer):
    """
    Serializer for flag submissions.
    """

    value = serializers.CharField(write_only=True)

    class Meta:
        model = UserFlagSubmission
        fields = [
            "id",
            "challenge_id",
            "contest_id",
            "challenge",
            "value",
            "status_display",
            "submitted_at",
        ]
        read_only_fields = ["id", "challenge", "status_display", "submitted_at"]

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        challenge, contest = self._get_challenge_and_contest(attrs)

        # Check that this challenge allows flag submissions
        sol_type = challenge.solution_type  # FK -> SolutionType
        # safer to use the 'type' field: "flag"/"text"/"both"
        sol_label = (getattr(sol_type, "type", "") or "").lower()

        if sol_label not in ("flag", "both"):
            raise serializers.ValidationError({"challenge_id": "This challenge does not accept flag submissions."})

        attrs["challenge_obj"] = challenge
        attrs["contest_obj"] = contest
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        challenge = validated_data.pop("challenge_obj")
        contest = validated_data.pop("contest_obj", None)
        value = validated_data["value"].strip()

        # Evaluate correctness against FlagSolution
        is_correct = FlagSolution.objects.filter(challenges=challenge, value=value).exists()

        status = self._get_status_for_result(is_correct)

        submission = UserFlagSubmission.objects.create(
            user=user,
            challenge=challenge,
            contest=contest,
            value=value,
            status=status,
        )
        return submission

    def to_representation(self, instance):
        base = super().to_representation(instance)

        # Base response (shared for contest + practice)
        response = {
            "id": instance.id,
            "user": {
                "username": instance.user.username,
                "email": instance.user.email,
            },
            "challenge": {
                "title": instance.challenge.title,
            },
            "value": instance.value,
            "content": None,
            "submitted_at": base["submitted_at"],
        }

        #  Only append status for PRACTICE submissions
        if instance.contest_id is None:
            response["status"] = {
                "status": instance.status.status,
            }

        return response


class TextSubmissionSerializer(BaseSubmissionSerializer):
    """
    Serializer for text-based (procedural/written) submissions.
    """

    content = serializers.CharField(write_only=True)

    class Meta:
        model = UserTextSubmission
        fields = [
            "id",
            "challenge_id",
            "contest_id",
            "challenge",
            "content",
            "status_display",
            "submitted_at",
        ]
        read_only_fields = ["id", "challenge", "status_display", "submitted_at"]

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        challenge, contest = self._get_challenge_and_contest(attrs)

        sol_type = challenge.solution_type
        sol_label = (getattr(sol_type, "type", "") or "").lower()

        # "flag" only, "text" only, or "both"
        if sol_label not in ("text", "both"):
            raise serializers.ValidationError({"challenge_id": "This challenge does not accept text submissions."})

        attrs["challenge_obj"] = challenge
        attrs["contest_obj"] = contest
        return attrs

    def _check_text_correct(self, challenge, content: str) -> bool:
        """
        Simple equality check.
        You can swap to __iexact or custom logic if needed.
        """
        normalized = content.strip()
        return TextSolution.objects.filter(challenges=challenge, content=normalized).exists()

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        challenge = validated_data.pop("challenge_obj")
        contest = validated_data.pop("contest_obj", None)
        content = validated_data["content"]

        is_correct = self._check_text_correct(challenge, content)
        status = self._get_status_for_result(is_correct)

        submission = UserTextSubmission.objects.create(
            user=user,
            challenge=challenge,
            contest=contest,
            content=content,
            status=status,
        )
        return submission

    def to_representation(self, instance):
        """
        Return nested JSON for admin/frontend:

        {
          "id": ...,
          "user": { "username": ..., "email": ... },
          "challenge": { "title": ... },
          "status": { "status": ... },
          "value": null,
          "content": "...",
          "submitted_at": "..."
        }
        """
        base = super().to_representation(instance)

        # Base response (shared for contest + practice)
        response = {
            "id": instance.id,
            "user": {
                "username": instance.user.username,
                "email": instance.user.email,
            },
            "challenge": {
                "title": instance.challenge.title,
            },
            "value": None,
            "content": instance.content,
            "submitted_at": base["submitted_at"],
        }

        #  Only append status for PRACTICE submissions
        if instance.contest_id is None:
            response["status"] = {
                "status": instance.status.status,
            }

        return response


class ChallengeSubmissionSerializer(serializers.Serializer):
    """
    POST /api/submission/<challenge_id>/
    Payload:
      { "value": "...", "content": "..." }

    - user comes from request.user
    - contest is derived from DB (not provided by client)
    - correctness validated against FlagSolution/TextSolution
    """

    value = serializers.CharField(required=False, allow_blank=False)
    content = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        request = self.context["request"]
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise PermissionDenied("Authentication required.")

        if not attrs.get("value") and not attrs.get("content"):
            raise serializers.ValidationError("Provide at least one of: value or content.")

        challenge: Challenge = self.context.get("challenge")
        if not challenge:
            raise serializers.ValidationError("Challenge context missing.")

        # Determine allowed types by SolutionType.type
        sol_type = getattr(challenge, "solution_type", None)
        sol_label = (getattr(sol_type, "type", "") or "").strip().lower()

        allowed = set()
        if sol_label == "flag":
            allowed = {"flag"}
        elif sol_label == "procedure":
            allowed = {"procedure"}
        elif sol_label == "flag and procedure":
            allowed = {"flag", "procedure"}
        else:
            # safest: deny unknown types
            raise PermissionDenied("Challenge solution_type.type must be one of: flag, text, both.")

        if attrs.get("value") and "flag" not in allowed:
            raise serializers.ValidationError({"value": "This challenge does not accept flag submissions."})

        if attrs.get("content") and "procedure" not in allowed:
            raise serializers.ValidationError({"content": "This challenge does not accept procedure submissions."})

        return attrs

    def _get_status_for_result(self, is_correct: bool) -> SubmissionStatus:
        if is_correct:
            status_value = "correct"
        elif is_correct == "incorrect":
            status_value = "incorrect"
        else:
            status_value = "pending"

        status_obj = SubmissionStatus.objects.get(status=status_value)
        return status_obj

    def _get_contest_for_challenge(self, challenge: Challenge):
        """
        Client does NOT send contest id.
        If competition -> contest must be exactly one and must be active in time window.
        If practice -> contest is None.
        """
        if challenge.question_type != "competition":
            return None

        contests_qs = Contest.objects.filter(challenges=challenge)
        count = contests_qs.count()

        if count == 0:
            raise PermissionDenied("Competition challenge is not linked to any contest.")
        if count > 1:
            raise PermissionDenied("Challenge is linked to multiple contests. Fix data integrity.")

        contest = contests_qs.first()
        now = timezone.now()

        if not contest.is_active:
            raise PermissionDenied("Contest is not active.")
        if not (contest.start_time <= now <= contest.end_time):
            raise PermissionDenied("Contest is not accepting submissions at this time.")

        return contest

    def _check_flag_correct(self, challenge: Challenge, value: str) -> bool:
        normalized = value.strip()
        return FlagSolution.objects.filter(challenges=challenge, value=normalized).exists()

    def _check_procedure_correct(self, challenge: Challenge, content: str) -> bool:
        normalized = content.strip()
        return TextSolution.objects.filter(challenges=challenge, content=normalized).exists()

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        challenge: Challenge = self.context["challenge"]

        contest = self._get_contest_for_challenge(challenge)

        challenge = Challenge.objects.select_related("challenge_score").get(id=challenge.id)

        response = {
            "challenge_id": challenge.id,
            "question_type": challenge.question_type,
            "results": [],
        }

        # FLAG
        if "value" in validated_data:
            value = validated_data["value"].strip()
            is_correct = self._check_flag_correct(challenge, value)
            status_obj = self._get_status_for_result(is_correct)
            flag_score = challenge.challenge_score.flag_score
            if not flag_score:
                flag_score = 1
            user_score = 0
            if is_correct:
                user_score = flag_score

            obj = UserFlagSubmission.objects.create(user=user, challenge=challenge, contest=contest, value=value,
                                                    status=status_obj, user_score=user_score)

            response["results"].append(
                {
                    "type": "flag",
                    "correct": is_correct,
                    "status": obj.status.status,
                    "submitted_at": obj.submitted_at,
                    "submitted_value": value,
                    "score": user_score,
                }
            )

        # PROCEDURE
        if "content" in validated_data:
            content = validated_data["content"]
            is_correct = self._check_procedure_correct(challenge, content)
            text_solution = SolutionUtils.get_text_solution_for_challenge(challenge)
            procedure_score = challenge.challenge_score.procedure_score
            if not procedure_score:
                procedure_score = 1

            score_analyser = None

            exact_val = text_solution.get("value", None)

            if exact_val is not None and content:
                try:
                    score_analyser = call_coach_llm(
                        user_solution=str(content),
                        challenge=utils.get_challenge_blob(challenge) if challenge is not None else {},
                        exact_solution=str(exact_val),
                        max_score=int(procedure_score or 0),
                    )
                except Exception:
                    score_analyser = None

            try:
                user_score = getattr(score_analyser, "score", None)
                if user_score is None:
                    user_score = 0
            except Exception:
                user_score = 0

            user_submission_status = getattr(score_analyser, "status", None)
            status_obj = self._get_status_for_result(user_submission_status)

            try:
                obj = UserTextSubmission.objects.create(
                    user=user,
                    challenge=challenge,
                    contest=contest,
                    content=content,
                    status=status_obj,
                    user_score=int(user_score) if user_score is not None else 0,
                )
            except Exception:
                obj = None

            response["results"].append(
                {
                    "type": "procedure",
                    "correct": user_submission_status,
                    "status": status_obj,
                    "submitted_at": obj.submitted_at,
                    "submitted_content": content,
                    "user_score": user_score,
                }
            )

        return response


class GroupChallengeSubmissionSerializer(serializers.Serializer):
    value = serializers.CharField(required=False, allow_blank=False)
    content = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        request = self.context["request"]
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise PermissionDenied("Authentication required.")

        if not attrs.get("value") and not attrs.get("content"):
            raise serializers.ValidationError("Provide at least one of: value or content.")

        challenge: Challenge = self.context.get("challenge")
        if not challenge:
            raise serializers.ValidationError("Challenge context missing.")

        if not challenge.contests.filter(group_only=True).exists():
            raise PermissionDenied("This challenge is not a group-only challenge.")

        try:
            membership = user.group_membership  # related_name='group_membership'
        except Exception:
            membership = None
        if not membership or not membership.group_id:
            raise PermissionDenied("You must join a group to submit this challenge.")

        sol_type = getattr(challenge, "solution_type", None)
        sol_label = (getattr(sol_type, "type", "") or "").strip().lower()

        allowed = set()
        if sol_label == "flag":
            allowed = {"flag"}
        elif sol_label == "procedure":
            allowed = {"procedure"}
        elif sol_label == "flag and procedure":
            allowed = {"flag", "procedure"}
        else:
            raise PermissionDenied("Challenge solution_type.type must be one of: flag, procedure, both.")

        if attrs.get("value") and "flag" not in allowed:
            raise serializers.ValidationError({"value": "This challenge does not accept flag submissions."})
        if attrs.get("content") and "procedure" not in allowed:
            raise serializers.ValidationError({"content": "This challenge does not accept procedure submissions."})

        return attrs

    def _get_status_for_result(self, is_correct: bool) -> SubmissionStatus:
        if is_correct:
            status_value = "correct"
        elif is_correct == "incorrect":
            status_value = "incorrect"
        else:
            status_value = "pending"

        status_obj = SubmissionStatus.objects.get(status=status_value)
        return status_obj

    def _get_contest_for_challenge(self, challenge: Challenge):
        if challenge.question_type != "competition":
            return None

        contests_qs = Contest.objects.filter(challenges=challenge)
        count = contests_qs.count()
        if count == 0:
            raise PermissionDenied("Competition challenge is not linked to any contest.")
        if count > 1:
            raise PermissionDenied("Challenge is linked to multiple contests. Fix data integrity.")

        contest = contests_qs.first()
        now = timezone.now()
        if not contest.is_active:
            raise PermissionDenied("Contest is not active.")
        if not (contest.start_time <= now <= contest.end_time):
            raise PermissionDenied("Contest is not accepting submissions at this time.")

        return contest

    def _check_flag_correct(self, challenge: Challenge, value: str) -> bool:
        normalized = value.strip()
        return FlagSolution.objects.filter(challenges=challenge, value=normalized).exists()

    def _check_procedure_correct(self, challenge: Challenge, content: str) -> bool:
        normalized = content.strip()
        return TextSolution.objects.filter(challenges=challenge, content=normalized).exists()

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        challenge: Challenge = self.context["challenge"]

        # group resolved from membership
        membership: UserGroup = user.group_membership
        group = membership.group

        contest = self._get_contest_for_challenge(challenge)

        challenge = Challenge.objects.select_related("challenge_score").get(id=challenge.id)

        response = {
            "challenge_id": challenge.id,
            "question_type": challenge.question_type,
            "results": [],
        }

        # FLAG
        if "value" in validated_data:
            value = validated_data["value"].strip()
            is_correct = self._check_flag_correct(challenge, value)
            status_obj = self._get_status_for_result(is_correct)

            flag_score = getattr(challenge.challenge_score, "flag_score", 0) or 0
            group_score = int(flag_score) if is_correct else 0

            obj = GroupFlagSubmission.objects.create(
                group=group,
                submitted_by=user,
                challenge=challenge,
                contest=contest,
                value=value,
                status=status_obj,
                group_score=group_score,
            )

            response["results"].append(
                {
                    "type": "flag",
                    "submitted_at": obj.submitted_at,
                    "submitted_value": value,
                }
            )

        # PROCEDURE
        if "content" in validated_data:
            content = validated_data["content"]

            procedure_score = getattr(challenge.challenge_score, "procedure_score", 0) or 0

            score_analyser = None
            try:
                text_solution = SolutionUtils.get_text_solution_for_challenge(challenge)
                exact_val = text_solution.get("value", None) if isinstance(text_solution, dict) else None
            except Exception:
                exact_val = None

            if exact_val is not None and content:
                try:
                    score_analyser = call_coach_llm(
                        user_solution=str(content),
                        challenge=utils.get_challenge_blob(challenge) if challenge is not None else {},
                        exact_solution=str(exact_val),
                        max_score=int(procedure_score or 0),
                    )
                except Exception:
                    score_analyser = None

            try:
                group_score = getattr(score_analyser, "score", None)
                group_score = int(group_score) if group_score is not None else 0

            except Exception:
                group_score = 0
            user_submission_status = getattr(score_analyser, "status", None)
            status_obj = self._get_status_for_result(user_submission_status)

            obj = GroupTextSubmission.objects.create(
                group=group,
                submitted_by=user,
                challenge=challenge,
                contest=contest,
                content=content,
                status=status_obj,
                group_score=group_score,
            )

            response["results"].append(
                {
                    "type": "procedure",
                    "submitted_at": obj.submitted_at,
                    "submitted_content": content,
                }
            )

        return response


class GroupFlagSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupFlagSubmission
        fields = ["id", "submitted_at", "value"]


class GroupTextSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupTextSubmission
        fields = ["id", "submitted_at", "content"]


class LeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    total_score = serializers.IntegerField()


class LeaderboardResponseSerializer(serializers.Serializer):
    type = serializers.CharField()
    contest = serializers.CharField(allow_null=True)
    results = LeaderboardEntrySerializer(many=True)
