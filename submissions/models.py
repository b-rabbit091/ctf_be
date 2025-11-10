from django.db import models
from users.models import User
from challenges.models import Challenge


class SubmissionStatus(models.Model):
    status = models.CharField(max_length=255, default="solved",unique=True, help_text="Name of the status")
    description = models.CharField(max_length=255, unique=True, help_text="Name of the description")

    def __str__(self):
        return self.status


class UserFlagSubmission(models.Model):
    """
    Correct flags for one or more challenges.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    value = models.CharField(max_length=255, unique=True, help_text="User flag value")
    challenges = models.ManyToManyField(Challenge, related_name="user_flag_solutions")
    status = models.ForeignKey(SubmissionStatus, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.value


class UserTextSubmission(models.Model):
    """
    Correct writing solutions for one or more challenges.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(help_text="User text solution")
    challenges = models.ManyToManyField(Challenge, related_name="user_text_solutions")
    status = models.ForeignKey(SubmissionStatus, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # truncate for readability
        return f"{self.content[:50]}{'...' if len(self.content) > 50 else ''}"
