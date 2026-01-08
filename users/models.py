# users/models.py
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.conf import settings


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


class Group(models.Model):
    """
    Logical grouping of users (e.g., class, team, section).
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    min_members = models.PositiveIntegerField(default=1)
    max_members = models.PositiveIntegerField()

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        return self.members.count()

    def is_full(self):
        return self.member_count >= self.max_members


class UserGroup(models.Model):
    """
    Actual membership. One user can belong to exactly one group at a time.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='group_membership'
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='members'
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} -> {self.group.name}"


class GroupInvitation(models.Model):
    """
    Invitation for a user to join a group.
    Tracks whether the user accepted or not.
    """
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_EXPIRED = 'expired'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_DECLINED, 'Declined'),
        (STATUS_EXPIRED, 'Expired'),
    )

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='invitations'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='group_invitations'
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_group_invitations'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('group', 'user')  # one invite per group-user pair

    def __str__(self):
        return f"Invitation: {self.user.username} -> {self.group.name} ({self.status})"
