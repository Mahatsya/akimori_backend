from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from django.core.paginator import Paginator, EmptyPage


from .models import Conversation, Message, Participant
from .serializers import (
    ConversationListSerializer,
    ConversationDetailSerializer,
    ConversationCreateSerializer,
    MessageSerializer,
    UserShortSerializer,
)

User = get_user_model()


class ConversationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    # GET /api/chats/conversations/
    @action(detail=False, methods=["get"], url_path="conversations")
    def conversations(self, request):
        qs = Conversation.objects.filter(participants=request.user).distinct()
        ser = ConversationListSerializer(qs, many=True)
        return Response(ser.data)

    # GET /api/chats/users/?q=...
    @action(detail=False, methods=["get"], url_path="users")
    def users(self, request):
        q = request.query_params.get("q", "")
        qs = User.objects.exclude(pk=request.user.pk)
        if q:
            qs = qs.filter(username__icontains=q)
        ser = UserShortSerializer(qs[:20], many=True)
        return Response(ser.data)

    # POST /api/chats/open_or_create/
    @action(detail=False, methods=["post"], url_path="open_or_create")
    def open_or_create(self, request):
        uid = request.data.get("user_id")
        other = get_object_or_404(User, pk=uid)
        conv = (
            Conversation.objects.filter(participants=request.user)
            .filter(participants=other)
            .first()
        )
        if not conv:
            conv = Conversation.objects.create(title="")
            Participant.objects.create(conversation=conv, user=request.user)
            Participant.objects.create(conversation=conv, user=other)
        ser = ConversationDetailSerializer(conv)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    # GET /api/chats/<uuid>/messages/
    @action(detail=True, methods=["get"], url_path="messages")
    def messages(self, request, pk=None):
        conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
        page = int(request.query_params.get("page", "1") or "1")
        page_size = int(request.query_params.get("page_size", "30") or "30")
        # храним в БД по возрастанию; для истории берём старые, но клиенту удобнее по возрастанию
        qs = conv.messages.order_by("created_at")
        paginator = Paginator(qs, page_size)
        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            return Response({"results": [], "page": page, "pages": paginator.num_pages})
        ser = MessageSerializer(page_obj.object_list, many=True)
        return Response({
            "results": ser.data,
            "page": page,
            "pages": paginator.num_pages,
            "count": paginator.count,
        })

    # POST /api/chats/<uuid>/send/
    @action(detail=True, methods=["post"], url_path="send")
    def send(self, request, pk=None):
        conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "empty"}, status=400)
        msg = Message.objects.create(conversation=conv, sender=request.user, text=text)
        ser = MessageSerializer(msg)
        return Response(ser.data, status=201)
