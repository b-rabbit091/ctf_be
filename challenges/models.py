from django.db import models

from users.models import User


class Challenge(models.Model):
    DIFFICULTY_CHOICES = (
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    )
    CATEGORY_CHOICES = (
        ('malware', 'Malware'),
        ('network', 'Network'),
        ('stego', 'Steganography'),
        ('crypto', 'Cryptography'),
    )

    title = models.CharField(max_length=255)
    description = models.TextField()
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    points = models.IntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.title


class Solution(models.Model):
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE)
    stored_solution = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
