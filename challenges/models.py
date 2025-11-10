from django.db import models
from django.contrib.auth import get_user_model

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


class SolutionType(models.Model):
    type = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.type


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
    files = models.JSONField(blank=True, null=True, help_text="List of file URLs or paths")
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='practice')
    solution_type = models.ForeignKey(SolutionType, default=3, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

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
