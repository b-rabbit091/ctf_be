# challenges/serializers.py

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers

from submissions.models import UserFlagSubmission, UserTextSubmission
from users.models import UserGroup

from .models import (
    Category,
    Challenge,
    ChallengeFile,
    Contest,
    Difficulty,
    SolutionType, ChallengeScore,
)
from .utils import validate_uploaded_file


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description"]


class DifficultySerializer(serializers.ModelSerializer):
    class Meta:
        model = Difficulty
        fields = ["id", "level", "description"]


class SolutionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolutionType
        fields = ["id", "type", "description"]


class ContestSerializer(serializers.ModelSerializer):
    challenges = serializers.PrimaryKeyRelatedField(many=True, queryset=Challenge.objects.all(), required=False)

    class Meta:
        model = Contest
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "contest_type",
            "start_time",
            "end_time",
            "publish_result",
            "challenges",
            "group_only"
        ]


class ContestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contest
        fields = ["name", "slug", "description", "contest_type", "start_time", "end_time", "publish_result",
                  "group_only"]


class ChallengeFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ChallengeFile
        fields = [
            "id",
            "url",
            "original_name",
            "mime_type",
            "size",
            "uploaded_at",
        ]

    def get_url(self, obj):
        return obj.file.url if obj.file else None


class ChallengeListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    difficulty = DifficultySerializer(read_only=True)
    active_contest = serializers.SerializerMethodField()
    can_participate = serializers.SerializerMethodField()
    user_submission_status = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = ["id", "title", "description", "category", "difficulty", "question_type", "active_contest",
                  "can_participate", "user_submission_status"]

    def get_active_contest(self, obj):
        now = timezone.now()
        active = (
            obj.contests.filter(
                start_time__lte=now,
                end_time__gte=now,
                is_active=True,
            )
            .order_by("start_time")
            .first()
        )

        if active:
            return ContestSerializer(active).data

        upcoming = (
            obj.contests.filter(
                start_time__gt=now,
                is_active=True,
            )
            .order_by("start_time")
            .first()
        )

        if upcoming:
            return ContestSerializer(upcoming).data

        return None

    def get_can_participate(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        # If challenge is not group-only → everyone can participate
        if obj.contests.filter(group_only=False).exists():
            return True

        # group_only == True → user must be in a group of minimum 2
        min_members = 2
        ug = UserGroup.objects.select_related("group").filter(user=request.user).first()

        if not ug:
            return False

        return ug.group.members.count() >= min_members

    def get_user_submission_status(self, obj):
        """
        Returns one of:
          - "solved"
          - "partially_solved"
          - "attempted"
          - "not_attempted"
        Rules you asked:
          - flag solved => solved
          - procedure solved => solved
          - flag_and_procedure with only one solved => partially_solved
          - if there are wrong answers on anything => attempted
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return "not_attempted"

        user = request.user

        # decide which contest context to use:
        # - if an active contest exists, evaluate submissions inside it
        # - else evaluate practice submissions (contest is NULL)

        # Your solution_type naming may differ; normalize to a string key
        st = ""
        if getattr(obj, "solution_type", None):
            st = getattr(obj.solution_type, "key", None) or getattr(obj.solution_type, "slug", None) or getattr(
                obj.solution_type, "name", "") or ""
        st = str(st).strip().lower()

        needs_flag = st in {"flag", "flag_and_procedure", "flag_and_procedure"}  # ok if duplicated
        needs_text = st in {"procedure", "flag_and_procedure"}

        # pull submissions
        flag_qs = UserFlagSubmission.objects.filter(user=user, challenge=obj)
        text_qs = UserTextSubmission.objects.filter(user=user, challenge=obj)

        # detect any activity
        any_attempt = flag_qs.exists() or text_qs.exists()
        if not any_attempt:
            return "not_attempted"

        # solved flags/text: status.status == "solved"
        flag_solved = flag_qs.filter(status__status__iexact="correct").exists()
        text_solved = text_qs.filter(status__status__iexact="correct").exists()

        # "wrong answers on anything => attempted"
        # treat ANY non-solved submission as "wrong/attempted"
        flag_wrong = flag_qs.exclude(status__status__iexact="correct").exists()
        text_wrong = text_qs.exclude(status__status__iexact="correct").exists()
        if flag_wrong or text_wrong:
            return "attempted"

        # no wrong attempts exist beyond this point
        if needs_flag and needs_text:
            if flag_solved and text_solved:
                return "solved"
            if flag_solved or text_solved:
                return "partially_solved"
            return "attempted"

        if needs_flag:
            return "solved" if flag_solved else "attempted"

        if needs_text:
            return "solved" if text_solved else "attempted"

        # fallback (if solution_type is missing/unknown)
        if flag_solved or text_solved:
            return "solved"
        return "attempted"


class ChallengeDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    difficulty = DifficultySerializer()
    solution_type = SolutionTypeSerializer()
    files = ChallengeFileSerializer(many=True, read_only=True)
    active_contest = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = [
            "id",
            "title",
            "description",
            "constraints",
            "input_format",
            "output_format",
            "sample_input",
            "sample_output",
            "question_type",
            "files",
            "category",
            "difficulty",
            "solution_type",
            "active_contest",
        ]

    def get_active_contest(self, obj):
        """
        Returns the currently running contest for this challenge if any.
        If none is running, optionally returns the next upcoming one.
        Otherwise returns None.

        This matches the frontend expectation: challenge.active_contest
        """
        now = timezone.now()

        # 1) contest currently running: start_time <= now <= end_time
        running_qs = obj.contests.filter(start_time__lte=now, end_time__gte=now).order_by("start_time")
        contest = running_qs.first()

        # 2) if none running, you can optionally expose the next upcoming one
        if contest is None:
            upcoming_qs = obj.contests.filter(start_time__gt=now).order_by("start_time")
            contest = upcoming_qs.first()

        if not contest:
            return None

        return ContestSerializer(contest).data


class ChallengeUpdateSerializer(serializers.ModelSerializer):
    """
    Used for create / update (practice & competition).

    - For **practice**: behaves as before, ignores contest fields.
    - For **competition**: can also create a Contest (in the same request)
      and attach the new challenge to it.
    """

    # FK fields as PKs
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)
    difficulty = serializers.PrimaryKeyRelatedField(queryset=Difficulty.objects.all(), required=False, allow_null=True)
    solution_type = serializers.PrimaryKeyRelatedField(queryset=SolutionType.objects.all(), required=False,
                                                       allow_null=True)

    # practice / competition
    question_type = serializers.ChoiceField(
        choices=Challenge.QUESTION_TYPE_CHOICES,
        required=False,
    )

    # Multiple uploaded files
    uploaded_files = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False, max_length=None),
        write_only=True,
        required=False,
        help_text="Multiple image/zip files to attach to this challenge.",
    )

    # ---- Contest (competition-only) fields: write-only & optional ----
    contest_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    contest_slug = serializers.SlugField(write_only=True, required=False, allow_blank=True)
    contest_description = serializers.CharField(write_only=True, required=False, allow_blank=True)
    contest_type = serializers.ChoiceField(
        write_only=True,
        required=False,
        choices=Contest.CONTEST_TYPE_CHOICES,
    )
    contest_start_time = serializers.DateTimeField(write_only=True, required=False)
    contest_end_time = serializers.DateTimeField(write_only=True, required=False)
    active_contest = serializers.SerializerMethodField()

    flag_score = serializers.IntegerField(write_only=True, required=False, min_value=0)
    procedure_score = serializers.IntegerField(write_only=True, required=False, min_value=0)

    class Meta:
        model = Challenge
        fields = [
            "title",
            "description",
            "constraints",
            "input_format",
            "output_format",
            "sample_input",
            "sample_output",
            "question_type",
            "category",
            "difficulty",
            "solution_type",
            "uploaded_files",
            # contest fields (write-only)
            "contest_name",
            "contest_slug",
            "contest_description",
            "contest_type",
            "contest_start_time",
            "contest_end_time",
            "active_contest",
            "flag_score",
            "procedure_score",

        ]

    def get_active_contest(self, obj):
        """
        Return ONE contest related to this challenge:
        - If now is within [start_time, end_time] → running contest
        - Else, the next upcoming contest (start_time > now)
        - Else None
        """
        now = timezone.now()

        running = (
            obj.contests.filter(
                start_time__lte=now,
                end_time__gte=now,
            )
            .order_by("start_time")
            .first()
        )
        if running:
            return ContestSerializer(running).data

        upcoming = obj.contests.filter(start_time__gt=now).order_by("start_time").first()
        if upcoming:
            return ContestSerializer(upcoming).data

        return None

    # ---------- Field-level validation ----------

    def validate_uploaded_files(self, files):
        for f in files:
            validate_uploaded_file(f)  # your server-side MIME/size checks
        return files

    # ---------- Object-level validation ----------

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        qtype = attrs.get("question_type")
        # If updating and no question_type passed, use existing
        if instance and qtype is None:
            qtype = instance.question_type

        # Collect contest fields passed in this request
        contest_fields = {
            key: attrs.get(key)
            for key in [
                "contest_name",
                "contest_slug",
                "contest_description",
                "contest_type",
                "contest_start_time",
                "contest_end_time",
            ]
        }
        any_contest_field = any(v is not None and v != "" for v in contest_fields.values())

        # 1) PRACTICE: contest fields should NOT be sent
        if ((qtype or attrs.get("question_type")) == "practice") and any_contest_field:
            raise serializers.ValidationError(
                {"contest": "Contest fields are only allowed for competition challenges."})

        # 2) COMPETITION: if contest data is provided, validate it
        if (qtype == "competition") and any_contest_field and not instance:
            name = contest_fields.get("contest_name")
            start = contest_fields.get("contest_start_time")
            end = contest_fields.get("contest_end_time")

            if not name:
                raise serializers.ValidationError(
                    {"contest_name": "Contest name is required for competition challenges."})
            if not start or not end:
                raise serializers.ValidationError(
                    {"contest_time": "Both contest_start_time and contest_end_time are required."})
            if end <= start:
                raise serializers.ValidationError(
                    {"contest_time": "contest_end_time must be after contest_start_time."})

            # Slug: generate if empty
            slug = contest_fields.get("contest_slug") or slugify(name)
            if Contest.objects.filter(slug=slug).exists():
                raise serializers.ValidationError(
                    {"contest_slug": "Contest slug already exists. Please choose another one."})
            attrs["contest_slug"] = slug

        # 3) Prevent changing question_type on challenges already in contests
        if instance and "question_type" in attrs:
            new_qtype = attrs["question_type"]
            if new_qtype != instance.question_type and instance.contests.exists():
                raise serializers.ValidationError(
                    {"question_type": "Cannot change question_type for a challenge already used in contests."})

        return attrs

    # ---------- internal helpers ----------

    def _save_files(self, challenge, files):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        for f in files:
            ChallengeFile.objects.create(
                challenge=challenge,
                file=f,
                original_name=f.name,
                mime_type=getattr(f, "content_type", None),
                size=f.size,
                uploaded_by=user if user and user.is_authenticated else None,
            )

    # ---------- create / update ----------

    @transaction.atomic
    def create(self, validated_data):
        """
        Create Challenge; if question_type='competition' and contest fields are present,
        also create Contest and link this challenge.
        """
        files = validated_data.pop("uploaded_files", [])

        # Extract contest data (if any)
        contest_name = validated_data.pop("contest_name", None)
        contest_slug = validated_data.pop("contest_slug", None)
        contest_description = validated_data.pop("contest_description", "")
        contest_type = validated_data.pop("contest_type", "custom")
        contest_start_time = validated_data.pop("contest_start_time", None)
        contest_end_time = validated_data.pop("contest_end_time", None)
        flag_score = validated_data.pop("flag_score", None)
        procedure_score = validated_data.pop("procedure_score", None)

        qtype = validated_data.get("question_type") or "practice"
        validated_data["question_type"] = qtype


        # If scores were provided, create ChallengeScore and attach it
        if flag_score is not None or procedure_score is not None:
            score_obj = ChallengeScore.objects.create(
                flag_score=flag_score or 0,
                procedure_score=procedure_score or 0,
            )
            validated_data["challenge_score"] = score_obj

        # 1) Create challenge
        challenge = super().create(validated_data)

        # 2) Create contest ONLY for competition + when contest data exists
        if qtype == "competition" and contest_name and contest_start_time and contest_end_time:
            contest = Contest.objects.create(
                name=contest_name,
                slug=contest_slug,  # already validated or auto-generated
                description=contest_description or "",
                contest_type=contest_type or "custom",
                start_time=contest_start_time,
                end_time=contest_end_time,
                is_active=True,
            )
            contest.challenges.add(challenge)

        # 3) Save files (if any)
        if files:
            self._save_files(challenge, files)

        return challenge

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Update Challenge + (optionally) update an associated Contest for competition challenges.
        """
        files = validated_data.pop("uploaded_files", [])

        # Extract contest fields (if any)
        contest_name = validated_data.pop("contest_name", None)
        contest_slug = validated_data.pop("contest_slug", None)
        contest_description = validated_data.pop("contest_description", None)
        contest_type = validated_data.pop("contest_type", None)
        contest_start_time = validated_data.pop("contest_start_time", None)
        contest_end_time = validated_data.pop("contest_end_time", None)
        flag_score = validated_data.pop("flag_score", None)
        procedure_score = validated_data.pop("procedure_score", None)

        any_contest_field = any(
            v is not None and v != ""
            for v in [
                contest_name,
                contest_slug,
                contest_description,
                contest_type,
                contest_start_time,
                contest_end_time,
            ]
        )

        # 1) Update challenge fields
        challenge = super().update(instance, validated_data)

        # Update or create ChallengeScore if scores were provided
        if flag_score is not None or procedure_score is not None:
            score_obj = challenge.challenge_score
            if score_obj is None:
                score_obj = ChallengeScore.objects.create(
                    flag_score=flag_score or 0,
                    procedure_score=procedure_score or 0,
                )
                challenge.challenge_score = score_obj
                challenge.save(update_fields=["challenge_score"])
            else:
                if flag_score is not None:
                    score_obj.flag_score = flag_score
                if procedure_score is not None:
                    score_obj.procedure_score = procedure_score
                score_obj.save()

        # 2) Update contest (only if competition + contest data was provided)
        if challenge.question_type == "competition" and any_contest_field:
            # Find contest

            contest = challenge.contests.order_by("-start_time").first()
            if not contest:
                raise serializers.ValidationError({"contest": "No contest is linked to this challenge to update."})

            # Validate/update times (only if any time is provided)
            if contest_start_time is not None or contest_end_time is not None:
                new_start = contest_start_time if contest_start_time is not None else contest.start_time
                new_end = contest_end_time if contest_end_time is not None else contest.end_time
                if new_end <= new_start:
                    raise serializers.ValidationError(
                        {"contest_time": "contest_end_time must be after contest_start_time."})
                contest.start_time = new_start
                contest.end_time = new_end

            new_slug = None
            if contest_slug is not None:
                if contest_slug == "":
                    # if they explicitly send empty slug, generate from name if available
                    if contest_name:
                        new_slug = slugify(contest_name)
                else:
                    new_slug = contest_slug
            elif contest_name:
                new_slug = slugify(contest_name)

            if new_slug and new_slug != contest.slug:
                if Contest.objects.filter(slug=new_slug).exclude(pk=contest.pk).exists():
                    raise serializers.ValidationError(
                        {"contest_slug": "Contest slug already exists. Please choose another one."})
                contest.slug = new_slug

            # Apply other fields only if provided
            if contest_name is not None:
                contest.name = contest_name
            if contest_description is not None:
                contest.description = contest_description
            if contest_type is not None:
                contest.contest_type = contest_type

            contest.save()

        # 3) Save files
        if files:
            self._save_files(challenge, files)

        return challenge
