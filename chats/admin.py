from django.contrib import admin
from .models import Conversation, Participant, Message

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "created_at", "updated_at")
    search_fields = ("title", "id")

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "user", "is_admin", "joined_at")
    search_fields = ("conversation__id", "user__username")

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "created_at", "short_text")
    search_fields = ("text", "conversation__id", "sender__username")

    def short_text(self, obj):
        return (obj.text or "")[:60]
