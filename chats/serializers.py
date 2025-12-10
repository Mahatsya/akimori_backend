from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Conversation, Participant, Message

User = get_user_model()


class UserShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")


class MessageSerializer(serializers.ModelSerializer):
    sender = UserShortSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ("id", "text", "created_at", "edited_at", "sender")


class ConversationListSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    participants = UserShortSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ("id", "title", "updated_at", "participants", "last_message")

    def get_last_message(self, obj):
        m = obj.messages.order_by("-created_at").first()
        return MessageSerializer(m).data if m else None


class ConversationDetailSerializer(serializers.ModelSerializer):
    participants = UserShortSerializer(many=True, read_only=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ("id", "title", "participants", "messages", "created_at", "updated_at")


class ConversationCreateSerializer(serializers.ModelSerializer):
    participant_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True
    )

    class Meta:
        model = Conversation
        fields = ("title", "participant_ids")

    def create(self, validated_data):
        user = self.context["request"].user
        ids = validated_data.pop("participant_ids", [])
        conv = Conversation.objects.create(**validated_data)
        Participant.objects.create(conversation=conv, user=user, is_admin=True)
        for uid in ids:
            if uid != user.id:
                Participant.objects.get_or_create(conversation=conv, user_id=uid)
        return conv
