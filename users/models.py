# users/models.py
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True)
    is_active = models.BooleanField(default=False)
    email = models.EmailField(unique=True)

    def is_admin(self):
        return self.role and self.role.name == 'admin'

    def is_student(self):
        return self.role and self.role.name == 'student'


class EmailVerificationToken(models.Model):
    """
    Stores token for both student and admin verification.
    Backend determines role from this token.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at
