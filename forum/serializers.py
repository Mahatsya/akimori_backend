# coding: utf-8
from __future__ import annotations

from rest_framework import serializers

from .models import (
    Category, ThreadKind, Tag, Thread, ThreadAttachment,
    Comment, ThreadPublisher, TranslatorWork
)

# ── внешние сериализаторы (оставил как у тебя) ──
from kodik.serializers import MaterialListSerializer, TranslationShortSerializer
from manga.serializers import MangaListSerializer, TranslatorMiniSerializer
# Если нужна запись по id, раскомментируй импорт модели Translator и поле publisher_id ниже:
# from manga.models import Translator


# ---------- Базовые ----------
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "id", "title", "slug", "is_active", "order",
            "created_at", "updated_at"
        )


class ThreadKindSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThreadKind
        fields = (
            "id", "title", "slug", "description", "is_active", "order",
            "allow_anime", "allow_manga", "allow_publish_as_team",
            "created_at", "updated_at"
        )


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "title", "slug", "created_at", "updated_at")


# ---------- Вложения ----------
class ThreadAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ThreadAttachment
        fields = (
            "id", "kind", "title", "file", "file_url", "url",
            "created_at", "updated_at"
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_file_url(self, obj):
        # безопасно отдаём URL файла, если он есть и доступен
        try:
            return obj.file.url if obj.file else None
        except Exception:
            return None


# ---------- Связь тема ↔ команда (publisher) ----------
class ThreadPublisherSerializer(serializers.ModelSerializer):
    # Вложенный объект переводчика/команды в виде мини-карточки
    publisher = TranslatorMiniSerializer(read_only=True)

    # === (опционально) запись по id вместо вложенного объекта ===
    # publisher_id = serializers.PrimaryKeyRelatedField(
    #     source="publisher",
    #     queryset=Translator.objects.all(),
    #     write_only=True,
    #     required=False,
    # )

    class Meta:
        model = ThreadPublisher
        fields = (
            "id",
            "publisher",          # -> { id, slug, name, avatar_url, ... }
            # "publisher_id",     # раскомментируй при необходимости записи
            "role", "note",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


# ---------- Список тем ----------
class ThreadListSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    poster_url = serializers.ReadOnlyField()
    category_title = serializers.CharField(source="category.title", read_only=True)
    kind_slug = serializers.CharField(source="kind.slug", read_only=True)

    # Для совместимости со старым фронтом
    thread_type = serializers.CharField(source="kind.slug", read_only=True)

    # Вложенные компактные карточки
    anime_obj = MaterialListSerializer(source="anime", read_only=True)
    manga_obj = MangaListSerializer(source="manga", read_only=True)

    class Meta:
        model = Thread
        fields = (
            "id", "slug", "title",
            "kind", "kind_slug", "thread_type",
            "category", "category_title",
            "author", "author_username",
            "anime", "manga",
            "anime_obj", "manga_obj",
            "poster_url",
            "comments_count", "last_activity_at",
            "is_locked", "is_pinned",
            "created_at", "updated_at"
        )
        read_only_fields = ("id", "created_at", "updated_at")


# ---------- Деталь темы ----------
class ThreadDetailSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    poster_url = serializers.ReadOnlyField()
    kind_slug = serializers.CharField(source="kind.slug", read_only=True)
    thread_type = serializers.CharField(source="kind.slug", read_only=True)

    attachments = ThreadAttachmentSerializer(many=True, read_only=True)
    thread_publishers = ThreadPublisherSerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    # Вложенные компактные карточки
    anime_obj = MaterialListSerializer(source="anime", read_only=True)
    manga_obj = MangaListSerializer(source="manga", read_only=True)

    class Meta:
        model = Thread
        fields = (
            "id", "slug", "title", "content",
            "kind", "kind_slug", "thread_type",
            "category",
            "author", "author_username",
            "publish_as_team",
            "anime", "manga",
            "anime_obj", "manga_obj",
            "poster_url", "extra",
            "tags",
            "attachments",
            "thread_publishers",
            "comments_count", "last_activity_at",
            "is_locked", "is_pinned",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


# ---------- Создание/обновление темы ----------
class ThreadWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Thread
        fields = (
            "id", "title", "slug", "content",
            "kind", "category", "publish_as_team",
            "anime", "manga",
            "poster", "extra", "tags",
            "is_locked", "is_pinned",
        )


# ---------- Комментарии ----------
class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Comment
        fields = (
            "id", "thread", "author", "author_username",
            "publish_as_team",
            "content",
            "parent",
            "status", "is_deleted", "is_pinned",
            "likes_count", "replies_count",
            "created_at", "updated_at"
        )
        read_only_fields = ("id", "created_at", "updated_at")


# ---------- Работы переводчика ----------
class TranslatorWorkSerializer(serializers.ModelSerializer):
    translator_name = serializers.CharField(source="translator.name", read_only=True)

    class Meta:
        model = TranslatorWork
        fields = (
            "id", "translator", "translator_name",
            "kind", "anime", "manga",
            "role", "note",
            "created_at", "updated_at"
        )
        read_only_fields = ("id", "created_at", "updated_at")
