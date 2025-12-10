import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Conversation, Participant, Message


def room_name(conv_id: str) -> str:
    return f"chat_{conv_id}"


@database_sync_to_async
def is_participant(conv_id, user) -> bool:
    from django.contrib.auth.models import AnonymousUser  # импортим тут
    if not user or not user.is_authenticated or isinstance(user, AnonymousUser):
        return False
    return Participant.objects.filter(conversation_id=conv_id, user=user).exists()


@database_sync_to_async
def save_message(conv_id, user, text):
    msg = Message.objects.create(conversation_id=conv_id, sender=user, text=text)
    Conversation.objects.filter(pk=conv_id).update(updated_at=msg.created_at)
    return {
        "id": msg.id,
        "text": msg.text,
        "created_at": msg.created_at.isoformat(),
        "sender": {"id": user.id, "username": user.get_username()},
    }


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    Протокол (JSON):
    -> {"action":"send_message","text":"Привет!"}
    <- {"type":"message","payload":{id, text, created_at, sender:{...}}}

    Дополнительно:
    -> {"action":"typing","value":true}
    <- {"type":"typing","payload":{"user_id":...,"value":true}}
    """

    async def connect(self):
        from django.contrib.auth.models import AnonymousUser  # и тут
        self.conv_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        user = self.scope.get("user", AnonymousUser())

        if not await is_participant(self.conv_id, user):
            await self.close(code=4403)  # Forbidden
            return

        self.group = room_name(self.conv_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        from django.contrib.auth.models import AnonymousUser  # на всякий случай и тут
        action = content.get("action")
        user = self.scope.get("user", AnonymousUser())

        if action == "send_message":
            text = (content.get("text") or "").strip()
            if not text:
                return
            data = await save_message(self.conv_id, user, text)
            await self.channel_layer.group_send(
                self.group,
                {"type": "chat.message", "payload": data}
            )

        elif action == "typing":
            value = bool(content.get("value", False))
            await self.channel_layer.group_send(
                self.group,
                {
                    "type": "chat.typing",
                    "payload": {"user_id": getattr(user, "id", None), "value": value}
                }
            )

    # Handlers для group_send
    async def chat_message(self, event):
        await self.send_json({"type": "message", "payload": event["payload"]})

    async def chat_typing(self, event):
        await self.send_json({"type": "typing", "payload": event["payload"]})
