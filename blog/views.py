# coding: utf-8
from __future__ import annotations

import os
from datetime import datetime

from django.conf import settings
from django.db.models import Count
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from rest_framework import viewsets, permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import Post, Category, Tag
from .serializers import (
    PostListSerializer,
    PostDetailSerializer,
    CategorySerializer,
    TagSerializer,
)
from .filters import PostFilter


class DefaultPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 200


class PostViewSet(viewsets.ModelViewSet):
    queryset = (
        Post.objects.select_related("author")
        .prefetch_related("categories", "tags")
        .all()
    )
    lookup_field = "slug"
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
    pagination_class = DefaultPagination
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = PostFilter
    search_fields = ("title", "excerpt", "content_html")
    ordering_fields = (
        "pinned",
        "published_at",
        "created_at",
        "updated_at",
        "title",
        "status",
    )
    ordering = ("-pinned", "-published_at", "-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return PostListSerializer
        return PostDetailSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.annotate(posts_count=Count("posts"))
    serializer_class = CategorySerializer
    permission_classes = (permissions.AllowAny,)


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.annotate(posts_count=Count("posts"))
    serializer_class = TagSerializer
    permission_classes = (permissions.AllowAny,)


# ====== TinyMCE image upload (бесплатный, без DRF) ======

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


@csrf_exempt  # если используете cookie+CSRF — уберите exempt и обеспечьте CSRF токен на форме
def tinymce_image_upload(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST")

    f = request.FILES.get("file")
    if not f:
        return HttpResponseBadRequest("No file")

    name, ext = os.path.splitext(f.name.lower())
    if ext not in ALLOWED_IMAGE_EXTS:
        return HttpResponseBadRequest("Unsupported file type")

    now = datetime.now()
    subdir = f"tinymce/{now:%Y/%m}"
    filename = default_storage.get_available_name(os.path.join(subdir, f.name))
    saved_path = default_storage.save(filename, ContentFile(f.read()))
    file_url = settings.MEDIA_URL + saved_path
    return JsonResponse({"location": file_url})
