from __future__ import annotations
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class Conversation(models.Model):
    """
    Диалог/групповой чат.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    participants = models.ManyToManyField(User, through="Participant", related_name="conversations")

    class Meta:
        ordering = ["-updated_at", "-created_at"]

    def __str__(self) -> str:
        return self.title or str(self.id)

class Participant(models.Model):
    """
    Участник чата.
    """
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="membership")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_memberships")
    joined_at = models.DateTimeField(default=timezone.now)
    is_admin = models.BooleanField(default=False)

    class Meta:
        unique_together = (("conversation", "user"),)
        indexes = [models.Index(fields=["conversation", "user"])]

    def __str__(self):
        return f"{self.user_id} in {self.conversation_id}"

class Message(models.Model):
    """
    Сообщение.
    """
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_messages")
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    read_by = models.ManyToManyField(User, related_name="read_messages", blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"{self.sender_id}: {self.text[:30]}"
