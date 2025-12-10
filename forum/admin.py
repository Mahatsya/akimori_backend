from django.contrib import admin
from .models import (
    ThreadKind, Category, Tag, Thread, ThreadPublisher,
    TranslatorWork, ThreadAttachment, Comment
)

@admin.register(ThreadKind)
class ThreadKindAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_active", "order",
                    "allow_anime", "allow_manga", "allow_publish_as_team")
    list_filter = ("is_active", "allow_anime", "allow_manga", "allow_publish_as_team")
    search_fields = ("title", "slug")
    ordering = ("order", "title")
    prepopulated_fields = {"slug": ("title",)}

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("title", "slug")
    ordering = ("order", "title")
    prepopulated_fields = {"slug": ("title",)}

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("title", "slug")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}

class ThreadPublisherInline(admin.TabularInline):
    model = ThreadPublisher
    extra = 0
    autocomplete_fields = ("publisher",)

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "kind", "author", "publish_as_team",
                    "comments_count", "is_locked", "is_pinned", "last_activity_at")
    list_filter  = ("category", "kind", "is_locked", "is_pinned", "tags")
    search_fields = ("title", "slug", "content")
    ordering = ("-is_pinned", "-last_activity_at", "-created_at")
    autocomplete_fields = ("category", "kind", "author", "publish_as_team", "anime", "manga", "tags")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ThreadPublisherInline]
    readonly_fields = ("comments_count", "last_activity_at")

@admin.register(ThreadPublisher)
class ThreadPublisherAdmin(admin.ModelAdmin):
    list_display = ("thread", "publisher", "role", "note", "created_at")
    list_filter = ("role",)
    search_fields = ("thread__title", "publisher__name", "note")
    autocomplete_fields = ("thread", "publisher")

@admin.register(TranslatorWork)
class TranslatorWorkAdmin(admin.ModelAdmin):
    list_display = ("translator", "kind", "anime", "manga", "role", "note", "created_at")
    list_filter = ("kind", "role")
    search_fields = ("translator__name", "note")
    autocomplete_fields = ("translator", "anime", "manga")

@admin.register(ThreadAttachment)
class ThreadAttachmentAdmin(admin.ModelAdmin):
    list_display = ("thread", "kind", "title", "file", "url", "created_at")
    list_filter = ("kind",)
    search_fields = ("title", "thread__title")
    autocomplete_fields = ("thread",)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "thread", "author", "status", "is_deleted", "is_pinned",
                    "likes_count", "replies_count", "parent", "created_at")
    list_filter = ("status", "is_deleted", "is_pinned")
    search_fields = ("content", "thread__title", "author__username")
    autocomplete_fields = ("thread", "author", "publish_as_team", "parent")
    ordering = ("-created_at",)
