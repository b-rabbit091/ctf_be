from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings

from challenges.utils import challenge_file_upload_path

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Difficulty(models.Model):
    level = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.level


# challenges/models.py
class SolutionType(models.Model):
    FLAG = "flag"
    PROCEDURE = "procedure"
    BOTH = "both"

    TYPE_CHOICES = (
        (FLAG, "Flag"),
        (PROCEDURE, "Procedure"),
        (BOTH, "Flag and Procedure"),
    )

    type = models.CharField(max_length=50, unique=True, choices=TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.get_type_display()


class Challenge(models.Model):
    QUESTION_TYPE_CHOICES = (
        ('practice', 'Practice'),
        ('competition', 'Competition'),
    )

    title = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='challenges')
    difficulty = models.ForeignKey(Difficulty, on_delete=models.SET_NULL, null=True, related_name='difficulty')
    description = models.TextField()
    constraints = models.TextField(blank=True, null=True)
    input_format = models.TextField(blank=True, null=True)
    output_format = models.TextField(blank=True, null=True)
    sample_input = models.TextField(blank=True, null=True)
    sample_output = models.TextField(blank=True, null=True)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='practice')
    solution_type = models.ForeignKey(SolutionType, default=3, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    group_only = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} ({self.question_type})"


class FlagSolution(models.Model):
    """
    Correct flags for one or more challenges.
    """
    value = models.CharField(max_length=255, unique=True, help_text="flag_value")
    challenges = models.ManyToManyField(Challenge, related_name="flag_solutions")

    def __str__(self):
        return self.value


class TextSolution(models.Model):
    """
    Correct writing solutions for one or more challenges.
    """
    content = models.TextField(help_text="Correct text solution")
    challenges = models.ManyToManyField(Challenge, related_name="text_solutions")

    def __str__(self):
        # truncate for readability
        return f"{self.content[:50]}{'...' if len(self.content) > 50 else ''}"


class ChallengeFile(models.Model):
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="files",
    )
    file = models.FileField(upload_to=challenge_file_upload_path)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    size = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return self.original_name


class Contest(models.Model):
    CONTEST_TYPE_CHOICES = (
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("custom", "Custom"),
    )

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    contest_type = models.CharField(
        max_length=20, choices=CONTEST_TYPE_CHOICES, default="custom"
    )

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    challenges = models.ManyToManyField("challenges.Challenge", related_name="contests")

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
