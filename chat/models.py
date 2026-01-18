# Create your models here.
# chat/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone


class ChatThread(models.Model):
    """
    One thread per user+challenge (or multiple if you want; we keep it simple).
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_threads")
    challenge_id = models.PositiveIntegerField(db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "challenge_id")
        indexes = [
            models.Index(fields=["user", "challenge_id"]),
        ]

    def touch(self):
        self.updated_at = timezone.now()
        self.save(update_fields=["updated_at"])

    def __str__(self):
        return f"Thread u={self.user_id} ch={self.challenge_id}"


class ChatTurn(models.Model):
    ROLE_CHOICES = (
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    )

    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="turns")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Optional metadata (percent, model info, etc.)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["thread", "created_at"]),
        ]

    def __str__(self):
        return f"{self.role} @{self.created_at.isoformat()}"
