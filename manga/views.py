# coding: utf-8
from __future__ import annotations

import io
import os
import re
import zipfile
from django.db import transaction
from django.core.files.base import ContentFile

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response

from .models import Manga, TranslatorPublisher, Edition, Chapter, ChapterPage
from .serializers import (
    MangaListSerializer,
    MangaDetailSerializer,
    MangaDetailWithChaptersSerializer,
    TranslatorSerializer,
    TranslatorDetailSerializer,
    EditionDetailSerializer,
    ChapterSerializer,
    ChapterPageSerializer,
)
from .filters import MangaFilter
from .permissions import IsTranslatorMemberCanPublish


ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _alphanum_key(s: str):
    """Естественная сортировка: 1,2,10 вместо 1,10,2."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"([0-9]+)", s)]


def _next_order_for(chapter: Chapter) -> int:
    last = chapter.pages.order_by("-order").first()
    return (last.order + 1) if last else 1


# ---------- MANGA ----------
class MangaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/manga/                   — список (фильтры/order)
    /api/manga/{slug}/            — карточка без глав
    /api/manga/{slug}/full/       — карточка + издания с главами
    /api/manga/{slug}/editions/   — только издания (опц. include=chapters)
    """
    queryset = (
        Manga.objects
        .all()
        .prefetch_related("genres", "categories", "editions__translator")
    )
    lookup_field = "slug"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = MangaFilter
    ordering_fields = ("created_at", "updated_at", "year", "title_ru")
    ordering = ("-updated_at",)

    def get_serializer_class(self):
        return MangaDetailSerializer if self.action == "retrieve" else MangaListSerializer

    @action(detail=True, methods=["get"], url_path="full")
    def full(self, request, slug=None):
        manga = self.get_object()
        manga = (
            Manga.objects.prefetch_related(
                "genres",
                "categories",
                "editions__translator",
                "editions__chapters",
            )
            .get(pk=manga.pk)
        )
        ser = MangaDetailWithChaptersSerializer(manga, context={"request": request})
        return Response(ser.data)

    @action(detail=True, methods=["get"], url_path="editions")
    def editions(self, request, slug=None):
        include = request.query_params.get("include")
        manga = self.get_object()
        qs = Edition.objects.filter(manga=manga).select_related("translator")
        if include == "chapters":
            qs = qs.prefetch_related("chapters")
            ser = EditionDetailSerializer(qs, many=True, context={"request": request})
        else:
            ser = EditionDetailSerializer(qs, many=True, context={"request": request, "no_chapters": True})
        return Response(ser.data)


# ---------- TRANSLATOR ----------
class TranslatorViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/translators/                  — список
    /api/translators/{slug}/           — детальная инфа (в т.ч. состав)
    /api/translators/{slug}/members/   — только состав команды
    """
    queryset = TranslatorPublisher.objects.all()
    lookup_field = "slug"
    filter_backends = (OrderingFilter,)
    ordering_fields = ("name", "followers_count", "manga_count")
    ordering = ("name",)

    def get_serializer_class(self):
        return TranslatorDetailSerializer if self.action == "retrieve" else TranslatorSerializer

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, slug=None):
        translator = self.get_object()
        data = TranslatorDetailSerializer(translator, context={"request": request}).data
        return Response(data.get("members", []))


# ---------- CHAPTER ----------
class ChapterViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    /api/chapters/?edition=<id>             — список глав
    /api/chapters/ (POST)                   — создать главу (role: owner/moderator/publisher)
    /api/chapters/{id}/                     — получить/изменить/удалить
    /api/chapters/{id}/images/ (POST)       — загрузить 1..N изображений (files[])
    /api/chapters/{id}/images-zip/ (POST)   — загрузить ZIP/CBZ (ключ: file|zip|archive)
    /api/chapters/{id}/reorder/ (PATCH)     — переупорядочить страницы [{id,order}]
    """
    queryset = Chapter.objects.all().select_related(
        "edition", "edition__translator", "edition__manga"
    )
    serializer_class = ChapterSerializer
    permission_classes = [IsTranslatorMemberCanPublish]
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_fields = ("edition",)
    ordering_fields = ("number", "published_at", "created_at")
    ordering = ("-number",)

    # Принимаем JSON (create/update) и multipart (загрузки)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_permissions(self):
        if self.action in (
            "create",
            "update",
            "partial_update",
            "destroy",
            "images",
            "images_zip",
            "reorder",
        ):
            return [IsTranslatorMemberCanPublish()]
        return super().get_permissions()

    # ------- IMAGES: 1..N файлов -------
    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="images")
    def images(self, request, pk=None):
        chapter: Chapter = self.get_object()
        self.check_object_permissions(request, chapter)

        files = request.FILES.getlist("files") or []
        if not files:
            f = request.FILES.get("files")
            if f:
                files = [f]
        if not files:
            return Response(
                {
                    "detail": "Не найдены файлы. Ожидаю поле 'files' (можно несколько).",
                    "received_files_keys": list(request.FILES.keys()),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        order = _next_order_for(chapter)
        for f in files:
            ext = os.path.splitext(f.name.lower())[1]
            if ext not in ALLOWED_IMAGE_EXT:
                return Response(
                    {"detail": f"Файл {f.name} имеет неподдерживаемый формат."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            page = ChapterPage.objects.create(
                chapter=chapter,
                image=f,
                order=order,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
            created.append(page)
            order += 1

        chapter.recalc_pages_count()
        return Response(
            ChapterPageSerializer(created, many=True, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ------- IMAGES ZIP / CBZ -------
    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="images-zip")
    def images_zip(self, request, pk=None):
        """
        Загрузка ZIP/CBZ (ключ в FormData: file|zip|archive).
        Устойчиво к UploadedFile: seek(0), при фейле — читаем в BytesIO.
        """
        chapter: Chapter = self.get_object()
        self.check_object_permissions(request, chapter)

        upfile = (
            request.FILES.get("file")
            or request.FILES.get("zip")
            or request.FILES.get("archive")
        )
        if not upfile:
            return Response(
                {
                    "detail": "ZIP-файл не найден (ожидаю 'file' или 'zip' или 'archive').",
                    "received_files_keys": list(request.FILES.keys()),
                    "received_data_keys": list(request.data.keys()),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if getattr(upfile, "size", None) in (0, "0"):
                return Response({"detail": "Файл не выбран."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            pass

        # Попробуем открыть напрямую
        try:
            try:
                upfile.seek(0)
            except Exception:
                pass
            zf = zipfile.ZipFile(upfile)
        except zipfile.BadZipFile:
            # Второй шанс: прочитаем в память
            try:
                try:
                    upfile.seek(0)
                except Exception:
                    pass
                raw = upfile.read()
                if not raw or raw[:2] != b"PK":
                    return Response(
                        {"detail": "Не ZIP-архив (нет сигнатуры PK)."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                zf = zipfile.ZipFile(io.BytesIO(raw))
            except zipfile.BadZipFile:
                return Response(
                    {"detail": "Повреждённый или неподдерживаемый ZIP."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        names = [n for n in zf.namelist() if not n.endswith("/")]
        names.sort(key=_alphanum_key)

        created = []
        order = _next_order_for(chapter)

        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext not in ALLOWED_IMAGE_EXT:
                continue
            try:
                data = zf.read(name)
            except Exception:
                continue
            if not data:
                continue
            cf = ContentFile(data, name=os.path.basename(name))
            page = ChapterPage.objects.create(
                chapter=chapter,
                image=cf,
                order=order,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
            created.append(page)
            order += 1

        zf.close()
        chapter.recalc_pages_count()

        return Response(
            ChapterPageSerializer(created, many=True, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ------- REORDER -------
    @transaction.atomic
    @action(detail=True, methods=["patch"], url_path="reorder")
    def reorder(self, request, pk=None):
        """
        Переупорядочить страницы:
        JSON: [{"id": <page_id>, "order": <int>}, ...]
        """
        chapter: Chapter = self.get_object()
        self.check_object_permissions(request, chapter)

        data = request.data
        if not isinstance(data, list) or not data:
            return Response(
                {"detail": "Ожидается массив объектов {id, order}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pages_map = {p.id: p for p in chapter.pages.all()}
        to_update = []
        for item in data:
            pid = item.get("id")
            order_val = item.get("order")
            if pid not in pages_map or not isinstance(order_val, int) or order_val < 1:
                return Response(
                    {"detail": f"Неверные данные: {item}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            page = pages_map[pid]
            if page.order != order_val:
                page.order = order_val
                to_update.append(page)

        if to_update:
            ChapterPage.objects.bulk_update(to_update, ["order"])

        chapter.recalc_pages_count()
        return Response({"detail": "ok"})
