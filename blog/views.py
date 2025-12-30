# coding: utf-8
from __future__ import annotations

import os
from uuid import uuid4
from datetime import datetime

from django.conf import settings
from django.db.models import Count
from django.core.files.storage import default_storage
from django.http import JsonResponse, HttpResponseBadRequest
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from PIL import Image, UnidentifiedImageError

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


# ====== TinyMCE image upload (закрытый, безопасный) ======

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


@login_required
@require_POST
@csrf_protect
def tinymce_image_upload(request):
    # Доступ только staff или роли moderator/admin
    role = getattr(request.user, "role", "")
    if not (request.user.is_staff or role in ("moderator", "admin")):
        raise PermissionDenied("Not allowed")

    f = request.FILES.get("file")
    if not f:
        return HttpResponseBadRequest("No file")

    # лимит веса
    max_bytes = getattr(settings, "TINYMCE_IMAGE_MAX_BYTES", 5 * 1024 * 1024)  # 5MB
    if getattr(f, "size", 0) > max_bytes:
        return HttpResponseBadRequest(f"File too large (max {max_bytes} bytes)")

    # расширение
    _, ext = os.path.splitext(f.name.lower())
    if ext not in ALLOWED_IMAGE_EXTS:
        return HttpResponseBadRequest("Unsupported file type")

    # проверка: файл реально картинка + лимит на размер по пикселям
    max_side = getattr(settings, "TINYMCE_IMAGE_MAX_SIDE_PX", 6000)
    try:
        f.seek(0)
        img = Image.open(f)
        img.verify()

        f.seek(0)
        img2 = Image.open(f)
        w, h = img2.size
        if w > max_side or h > max_side:
            return HttpResponseBadRequest(f"Image too large (max side {max_side}px)")
    except (UnidentifiedImageError, OSError):
        return HttpResponseBadRequest("Invalid image file")
    finally:
        try:
            f.seek(0)
        except Exception:
            pass

    # безопасное имя файла (не сохраняем оригинал)
    now = datetime.now()
    subdir = f"tinymce/{now:%Y/%m}"
    safe_name = f"{uuid4().hex}{ext}"
    filename = default_storage.get_available_name(os.path.join(subdir, safe_name))
    saved_path = default_storage.save(filename, f)

    file_url = settings.MEDIA_URL + saved_path
    return JsonResponse({"location": file_url})
