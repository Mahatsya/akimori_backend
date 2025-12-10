from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Manga, Category, Genre,
    TranslatorPublisher, TranslatorMember,
    Edition, Chapter, ChapterPage
)


class TranslatorMemberInline(admin.TabularInline):
    model = TranslatorMember
    extra = 0
    autocomplete_fields = ("user",)
    fields = ("user", "role", "title", "is_active", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TranslatorPublisher)
class TranslatorPublisherAdmin(admin.ModelAdmin):
    list_display = ("name", "manga_count", "followers_count", "updated_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TranslatorMemberInline]


class ChapterPageInline(admin.TabularInline):
    model = ChapterPage
    extra = 0
    fields = ("order", "image", "uploaded_by", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("order",)


class ChapterAdmin(admin.ModelAdmin):
    list_display = ("edition", "number", "name", "volume", "pages_count", "published_at", "uploaded_by", "updated_at")
    list_filter = ("edition__translator", "edition__manga")
    search_fields = ("edition__manga__title_ru", "edition__translator__name")
    inlines = [ChapterPageInline]


class EditionInline(admin.TabularInline):
    model = Edition
    extra = 0


@admin.register(Manga)
class MangaAdmin(admin.ModelAdmin):
    list_display = ("title_ru", "type", "year", "work_status", "poster_thumb", "updated_at")
    list_filter = ("type", "work_status", "year", "genres", "categories")
    search_fields = ("title_ru", "title_en", "alt_titles")
    prepopulated_fields = {"slug": ("title_ru",)}
    inlines = [EditionInline]
    filter_horizontal = ("genres", "categories")

    readonly_fields = ("poster_preview", "banner_preview")
    fieldsets = (
        (None, {
            "fields": ("title_ru", "title_en", "alt_titles", "slug",
                       ("type", "age_rating", "year"),
                       "description", "work_status")
        }),
        ("Медиа", {
            "fields": (("poster", "poster_preview"),
                       ("banner", "banner_preview"))
        }),
        ("Классификация", {"fields": ("categories", "genres")}),
        ("Ссылки", {"fields": ("links",)}),
    )

    def poster_thumb(self, obj):
        if obj.poster_url:
            return format_html('<img src="{}" style="height:40px;border-radius:4px;" />', obj.poster_url)
        return "—"
    poster_thumb.short_description = "Постер"

    def poster_preview(self, obj):
        if obj.poster_url:
            return format_html('<img src="{}" style="max-width:240px;border-radius:6px;" />', obj.poster_url)
        return "—"
    poster_preview.short_description = "Постер (превью)"

    def banner_preview(self, obj):
        if obj.banner_url:
            return format_html('<img src="{}" style="max-width:480px;border-radius:6px;" />', obj.banner_url)
        return "—"
    banner_preview.short_description = "Шапка (превью)"


@admin.register(Edition)
class EditionAdmin(admin.ModelAdmin):
    list_display = ("manga", "translator", "translation_status", "updated_at")
    list_filter = ("translation_status",)
    search_fields = ("manga__title_ru", "translator__name")


@admin.register(Chapter)
class ChapterAdminBound(ChapterAdmin):
    pass


admin.site.register(Category)
admin.site.register(Genre)
