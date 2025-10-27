from django.db import models
from users.models import User
from challenges.models import Challenge

class Submission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE)
    user_solution = models.TextField()
    feedback = models.TextField(blank=True, null=True)  # placeholder for AI feedback
    score = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)
