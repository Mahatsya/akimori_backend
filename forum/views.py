# coding: utf-8
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    Category, ThreadKind, Tag, Thread, ThreadAttachment, Comment
)
from .serializers import (
    CategorySerializer, ThreadKindSerializer, TagSerializer,
    ThreadListSerializer, ThreadDetailSerializer, ThreadWriteSerializer,
    ThreadAttachmentSerializer, CommentSerializer
)

# --------- базовые ---------
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all().order_by("order", "title")
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "slug"]
    ordering_fields = ["order", "title", "created_at"]

class ThreadKindViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ThreadKind.objects.filter(is_active=True).order_by("order", "title")
    serializer_class = ThreadKindSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "slug"]
    ordering_fields = ["order", "title", "created_at"]

class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all().order_by("title")
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "slug"]
    ordering_fields = ["title", "created_at"]

# --------- threads ---------
class ThreadViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        "category": ["exact"],
        "kind": ["exact"],
        "slug": ["exact"],
        "anime": ["exact", "isnull"],
        "manga": ["exact", "isnull"],
        "is_pinned": ["exact"],
        "is_locked": ["exact"],
    }
    search_fields = ["title", "content", "slug"]
    ordering_fields = ["created_at", "last_activity_at", "comments_count", "id"]
    ordering = ["-created_at"]

    # lookup по slug
    lookup_field = "slug"
    # если бывают точки — раскомментируй
    # lookup_value_regex = r"[-a-zA-Z0-9_.]+"

    def get_queryset(self):
        qs = (
            Thread.objects
            .select_related("author", "category", "kind", "anime", "manga")
            .prefetch_related(
                "attachments",
                "tags",
                "thread_publishers__publisher",
                "manga__editions__translator",
            )
            .all()
        )

        thread_type = self.request.query_params.get("thread_type")
        if thread_type:
            qs = qs.filter(kind__slug=thread_type)

        kind_slug = self.request.query_params.get("kind_slug")
        if kind_slug:
            qs = qs.filter(kind__slug=kind_slug)

        cat = self.request.query_params.get("category")
        if cat:
            if cat.isdigit():
                qs = qs.filter(category_id=int(cat))
            else:
                qs = qs.filter(category__slug=cat)

        return qs

    # поддержка и /threads/<id>/ и /threads/<slug>/ (на будущее)
    def get_object(self):
        value = self.kwargs.get(self.lookup_field)
        qs = self.get_queryset()
        if value.isdigit():
            return get_object_or_404(qs, pk=int(value))
        return get_object_or_404(qs, slug=value)

    def get_serializer_class(self):
        if self.action == "list":
            return ThreadListSerializer
        if self.action == "retrieve":
            return ThreadDetailSerializer
        return ThreadWriteSerializer

# --------- вложения ---------
class ThreadAttachmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = ThreadAttachmentSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {"thread": ["exact"], "kind": ["exact"]}
    ordering_fields = ["created_at", "id"]
    ordering = ["created_at"]

    def get_queryset(self):
        return ThreadAttachment.objects.select_related("thread").all()

# --------- комментарии ---------
class CommentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = CommentSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        "thread": ["exact"],
        "parent": ["exact", "isnull"],
        "status": ["exact"],
        "is_deleted": ["exact"],
    }
    ordering_fields = ["created_at", "id"]
    ordering = ["created_at"]

    def get_queryset(self):
        return (
            Comment.objects
            .select_related("thread", "author", "publish_as_team")
            .all()
        )
