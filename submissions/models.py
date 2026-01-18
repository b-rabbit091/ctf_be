from django.conf import settings
from django.db import models


class SubmissionStatus(models.Model):
    status = models.CharField(max_length=255, default="solved", help_text="Name of the status")
    description = models.CharField(max_length=255, help_text="Name of the description")

    def __str__(self):
        return self.status


class BaseUserSubmission(models.Model):
    """
    Common fields for both flag and text submissions.
    Practice submissions: contest is NULL.
    Competition submissions: contest is set.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_submissions",
    )
    challenge = models.ForeignKey(
        "challenges.Challenge",
        on_delete=models.CASCADE,
        related_name="%(class)s_submissions",
    )
    contest = models.ForeignKey(
        "challenges.Contest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="%(class)s_submissions",
        help_text="Null for practice submissions; set for competition.",
    )
    status = models.ForeignKey("SubmissionStatus", on_delete=models.CASCADE)
    user_score = models.IntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["challenge", "user"]),
            models.Index(fields=["contest", "challenge", "user"]),
        ]


class UserFlagSubmission(BaseUserSubmission):
    """
    One flag submission for a single challenge (and optionally a contest).
    """

    value = models.CharField(
        max_length=255,
        help_text="User flag value",
    )

    def __str__(self):
        return f"{self.user} :: {self.challenge_id} :: {self.value[:40]}"


class UserTextSubmission(BaseUserSubmission):
    """
    One text submission for a single challenge (and optionally a contest).
    """

    content = models.TextField(help_text="User text solution")

    def __str__(self):
        # truncate for readability
        return f"{self.user} :: {self.challenge_id} :: {self.content[:50]}{'...' if len(self.content) > 50 else ''}"


# submissions/models.py

from django.conf import settings
from django.db import models

from users.models import Group  # adjust import to your app

# or from .models import Group if in same app


class BaseGroupSubmission(models.Model):
    """
    Common fields for group submissions.
    Practice: contest NULL
    Competition: contest set
    """

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="%(class)s_submissions",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_group_submissions",
        help_text="Which member submitted on behalf of the group.",
    )
    challenge = models.ForeignKey(
        "challenges.Challenge",
        on_delete=models.CASCADE,
        related_name="%(class)s_group_submissions",
    )
    contest = models.ForeignKey(
        "challenges.Contest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="%(class)s_group_submissions",
        help_text="Null for practice submissions; set for competition.",
    )
    status = models.ForeignKey("submissions.SubmissionStatus", on_delete=models.CASCADE)
    group_score = models.IntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["challenge", "group"]),
            models.Index(fields=["contest", "challenge", "group"]),
        ]


class GroupFlagSubmission(BaseGroupSubmission):
    value = models.CharField(max_length=255, help_text="Group flag value")

    def __str__(self):
        return f"{self.group_id} :: {self.challenge_id} :: {self.value[:40]}"


class GroupTextSubmission(BaseGroupSubmission):
    content = models.TextField(help_text="Group text solution")

    def __str__(self):
        return f"{self.group_id} :: {self.challenge_id} :: {self.content[:50]}{'...' if len(self.content) > 50 else ''}"
