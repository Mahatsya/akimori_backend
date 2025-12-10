# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.contrib import admin
from django.db import transaction
from django.db.models import Count, Avg
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django import forms

# --- optional сторонние либы: мягкие фоллбэки ---
try:
    from rangefilter.filters import DateRangeFilter, DateTimeRangeFilter
except Exception:  # фоллбэк на стандартный
    DateRangeFilter = admin.DateFieldListFilter
    DateTimeRangeFilter = admin.DateFieldListFilter

try:
    from django_admin_listfilter_dropdown.filters import (
        DropdownFilter, RelatedDropdownFilter, ChoiceDropdownFilter
    )
except Exception:
    # фоллбэки: используем обычные list_filter
    class DropdownFilter: ...
    class RelatedDropdownFilter: ...
    class ChoiceDropdownFilter: ...

try:
    from django_object_actions import DjangoObjectActions
except Exception:
    class DjangoObjectActions:
        change_actions = ()
        def get_change_actions(self, request, object_id, form_url): return ()

try:
    from import_export.admin import ImportExportModelAdmin
    from import_export import resources
except Exception:
    class ImportExportModelAdmin(admin.ModelAdmin): ...
    resources = None

try:
    from admin_inline_paginator.admin import TabularInlinePaginator
except Exception:
    TabularInlinePaginator = admin.TabularInline

try:
    from django_summernote.widgets import SummernoteWidget
except Exception:
    SummernoteWidget = forms.Textarea

from .models import (
    Translation,
    Country,
    Genre,
    Studio,
    LicenseOwner,
    MDLTag,
    Person,
    Material,
    MaterialExtra,
    MaterialVersion,
    Season,
    Episode,
    Credit,
    # === добавлено:
    AkiUserRating,
    MaterialComment,
    MaterialCommentLike,
    MaterialCommentStatus,
)


# ============ Утилиты ============

class ReadonlySlugMixin:
    readonly_fields = getattr(admin.ModelAdmin, "readonly_fields", tuple()) + ("slug",)


def admin_changelist_url(model, **query):
    app_label = model._meta.app_label
    model_name = model._meta.model_name
    url = reverse(f"admin:{app_label}_{model_name}_changelist")
    if query:
        params = "&".join(f"{k}={v}" for k, v in query.items())
        return f"{url}?{params}"
    return url


def admin_change_url(obj):
    meta = obj._meta
    return reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[obj.pk])


# ============ Import-Export ресурсы (если установлен) ============

if resources:
    class MaterialResource(resources.ModelResource):
        class Meta:
            model = Material
            fields = (
                "kodik_id", "title", "type", "year", "quality", "camrip", "lgbt",
                "kinopoisk_id", "imdb_id", "mdl_id", "shikimori_id", "worldart_link",
                "created_at", "updated_at",
            )
            export_order = fields

    class TranslationResource(resources.ModelResource):
        class Meta:
            model = Translation
            fields = ("ext_id", "title", "type", "slug", "website_url", "founded_year")

    class PersonResource(resources.ModelResource):
        class Meta:
            model = Person
            fields = ("name", "slug", "birth_date", "death_date", "imdb_id", "shikimori_id", "kinopoisk_id")


# ============ Формы с Summernote (rich-text) ============

class TranslationForm(forms.ModelForm):
    description = forms.CharField(widget=SummernoteWidget(), required=False)

    class Meta:
        model = Translation
        fields = "__all__"


class PersonForm(forms.ModelForm):
    bio = forms.CharField(widget=SummernoteWidget(), required=False)

    class Meta:
        model = Person
        fields = "__all__"


# ============ Справочники ============

@admin.register(Translation)
class TranslationAdmin(ReadonlySlugMixin, ImportExportModelAdmin, DjangoObjectActions):
    form = TranslationForm
    list_display = ("id", "ext_id", "title", "type", "country_badge", "materials_count", "site_link")
    list_filter = (
        ("type", ChoiceDropdownFilter) if ChoiceDropdownFilter else "type",
        ("country", RelatedDropdownFilter) if RelatedDropdownFilter else "country",
    )
    search_fields = ("title", "ext_id", "aliases")
    ordering = ("title",)
    list_per_page = 50

    if resources:
        resource_classes = [TranslationResource]

    change_actions = ("open_site", "open_public_api")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_materials=Count("versions", distinct=True))
            .select_related("country")
        )

    @admin.display(description="Материалов", ordering="_materials")
    def materials_count(self, obj: Translation):
        url = admin_changelist_url(MaterialVersion, translation__id=obj.id)
        return format_html('<a href="{}">{}</a>', url, obj._materials)

    @admin.display(description="Страна", ordering="country__name")
    def country_badge(self, obj: Translation):
        if not obj.country:
            return "—"
        return format_html(
            '<span style="padding:2px 6px;border-radius:10px;background:#eef;">{}</span>',
            f"{obj.country.name} ({obj.country.code})"
        )

    @admin.display(description="Сайт")
    def site_link(self, obj: Translation):
        if not obj.website_url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">перейти</a>', obj.website_url)

    # Object actions
    def open_site(self, request, obj: Translation):
        if obj.website_url:
            return format_html('<a class="button" href="{}" target="_blank">Открыть сайт</a>', obj.website_url)
        return mark_safe('<span class="button disabled">Сайт не указан</span>')

    open_site.label = "Открыть сайт"
    open_site.short_description = "Открыть внешний сайт (новая вкладка)"

    def open_public_api(self, request, obj: Translation):
        # пример «внутреннего» API (подправь путь под свой проект)
        url = f"/api/translations/{obj.slug}/"
        return format_html('<a class="button" href="{}" target="_blank">Открыть API</a>', url)

    open_public_api.label = "Открыть API"
    open_public_api.short_description = "Открыть публичное API этой озвучки"


@admin.register(Country)
class CountryAdmin(ReadonlySlugMixin, admin.ModelAdmin):
    list_display = ("id", "code", "name", "slug")
    search_fields = ("code", "name")
    ordering = ("name",)
    list_per_page = 50


@admin.register(Genre)
class GenreAdmin(ReadonlySlugMixin, admin.ModelAdmin):
    list_display = ("id", "name", "source", "slug")
    list_filter = (("source", ChoiceDropdownFilter) if ChoiceDropdownFilter else "source",)
    search_fields = ("name", "slug")
    ordering = ("name",)
    list_per_page = 50


@admin.register(Studio)
class StudioAdmin(ReadonlySlugMixin, admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    search_fields = ("name", "slug")
    ordering = ("name",)
    list_per_page = 50


@admin.register(LicenseOwner)
class LicenseOwnerAdmin(ReadonlySlugMixin, admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    search_fields = ("name", "slug")
    ordering = ("name",)
    list_per_page = 50


@admin.register(MDLTag)
class MDLTagAdmin(ReadonlySlugMixin, admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    search_fields = ("name", "slug")
    ordering = ("name",)
    list_per_page = 50


@admin.register(Person)
class PersonAdmin(ReadonlySlugMixin, ImportExportModelAdmin, DjangoObjectActions):
    form = PersonForm
    list_display = ("id", "avatar_thumb", "name", "slug", "country", "birth_date", "death_date", "credits_count")
    search_fields = ("name", "slug", "bio", "imdb_id", "shikimori_id", "kinopoisk_id")
    ordering = ("name",)
    list_per_page = 50
    list_filter = (
        ("country", RelatedDropdownFilter) if RelatedDropdownFilter else "country",
        ("birth_date", DateRangeFilter),
        ("death_date", DateRangeFilter),
    )

    if resources:
        resource_classes = [PersonResource]

    fieldsets = (
        (None, {"fields": ("name", "slug", "country")}),
        ("Витрина", {"fields": ("avatar_url", "photo_url", "banner_url")}),
        ("Биография", {"fields": ("bio",)}),
        ("Даты", {"fields": ("birth_date", "death_date")}),
        ("Внешние ID/соцсети", {"fields": ("imdb_id", "shikimori_id", "kinopoisk_id", "socials")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_credits=Count("credits")).select_related("country")

    @admin.display(description="Кредитов", ordering="_credits")
    def credits_count(self, obj: Person):
        url = admin_changelist_url(Credit, person__id=obj.id)
        return format_html('<a href="{}">{}</a>', url, obj._credits)

    @admin.display(description="")
    def avatar_thumb(self, obj: Person):
        url = obj.avatar_url or obj.photo_url
        if not url:
            return "—"
        return format_html('<img src="{}" style="height:36px;border-radius:50%;" />', url)


# ============ INLINES ============

class MaterialExtraInline(admin.StackedInline):
    model = MaterialExtra
    can_delete = False
    max_num = 1
    extra = 0
    formfield_overrides = {
        MaterialExtra._meta.get_field("description").__class__: {"widget": SummernoteWidget()},
        MaterialExtra._meta.get_field("anime_description").__class__: {"widget": SummernoteWidget()},
    }
    fieldsets = (
        ("Названия", {"fields": ("title", "anime_title", "title_en")}),
        ("Альтернативные названия", {"fields": ("other_titles", "other_titles_en", "other_titles_jp")}),
        ("Лицензии и типы", {"fields": ("anime_license_name", "anime_kind")}),
        ("Статусы", {"fields": ("all_status", "anime_status", "drama_status")}),
        ("Описание", {"fields": ("tagline", "description", "anime_description")}),
        ("Постеры", {"fields": ("poster_url", "anime_poster_url", "drama_poster_url")}),
        ("Даты/продолжительность", {"fields": ("duration", "premiere_ru", "premiere_world", "aired_at", "released_at", "next_episode_at")}),
        ("Возраст/рейтинги/эпизоды", {
            "fields": (
                "rating_mpaa", "minimal_age",
                "kinopoisk_rating", "kinopoisk_votes",
                "imdb_rating", "imdb_votes",
                "shikimori_rating", "shikimori_votes",
                "mydramalist_rating", "mydramalist_votes",
                "episodes_total", "episodes_aired",
            )
        }),
        ("Агрегаты Akimori / просмотры", {
            "fields": ("comments_count", "aki_votes", "aki_rating", "views_count"),
        }),
    )


class EpisodeInline(TabularInlinePaginator):
    model = Episode
    per_page = 20
    extra = 0
    fields = ("number", "title", "link_short")
    readonly_fields = ("link_short",)

    @admin.display(description="Ссылка")
    def link_short(self, obj: Episode):
        if not obj.link:
            return "—"
        text = obj.link[:70] + ("…" if len(obj.link) > 70 else "")
        return format_html('<a href="{0}" target="_blank" rel="noopener noreferrer">{1}</a>', obj.link, text)


class SeasonInline(admin.TabularInline):
    model = Season
    extra = 0
    fields = ("number", "link", "episodes_count", "open_episodes")
    readonly_fields = ("episodes_count", "open_episodes")
    show_change_link = True

    @admin.display(description="Серий")
    def episodes_count(self, obj: Season):
        return obj.episodes.count()

    @admin.display(description="Открыть серии")
    def open_episodes(self, obj: Season):
        url = admin_changelist_url(Episode, season__id=obj.id)
        return format_html('<a class="button" href="{}">Открыть</a>', url)


# ============ MATERIAL ============

@admin.register(Material)
class MaterialAdmin(ReadonlySlugMixin, ImportExportModelAdmin, DjangoObjectActions):
    save_on_top = True
    list_select_related = ("translation", "extra")
    list_per_page = 50

    list_display = (
        "thumb",
        "title",
        "type",
        "year",
        "translation",
        "has_kp",
        "has_imdb",
        "has_mdl",
        "has_shiki",
        "comments_count_col",
        "aki_rating_col",
        "aki_votes_col",
        "views_count_col",
        "updated_at",
        "versions_count",
        "seasons_total",
        "episodes_total",
        "open_public_api",
    )
    list_display_links = ("title",)
    list_filter = (
        ("type", ChoiceDropdownFilter) if ChoiceDropdownFilter else "type",
        ("year", ChoiceDropdownFilter) if ChoiceDropdownFilter else "year",
        ("translation__type", ChoiceDropdownFilter) if ChoiceDropdownFilter else "translation__type",
        ("updated_at", DateTimeRangeFilter),
        ("created_at", DateTimeRangeFilter),
        ("camrip", ChoiceDropdownFilter) if ChoiceDropdownFilter else "camrip",
        ("lgbt", ChoiceDropdownFilter) if ChoiceDropdownFilter else "lgbt",
    )
    search_fields = (
        "title",
        "title_orig",
        "other_title",
        "kodik_id",
        "kinopoisk_id",
        "imdb_id",
        "mdl_id",
        "shikimori_id",
    )
    ordering = ("-updated_at", "-created_at")

    readonly_fields = ("kodik_id", "created_at", "updated_at", "poster_preview", "slug")

    autocomplete_fields = (
        "translation",
        "genres",
        "studios",
        "license_owners",
        "mdl_tags",
        "production_countries",
        "blocked_countries",
    )

    inlines = (MaterialExtraInline,)

    # Экшены
    actions = ("recalc_material_aggregates",)

    fieldsets = (
        ("Идентификаторы", {"fields": ("kodik_id", "slug")}),
        ("Основное", {"fields": ("title", "title_orig", "other_title", "type", "year", "link", "translation", "quality", "camrip", "lgbt")}),
        ("Внешние ID", {"fields": ("kinopoisk_id", "imdb_id", "mdl_id", "shikimori_id", "worldart_link")}),
        ("Постер", {"fields": ("poster_url", "poster_preview")}),
        ("Страны", {"fields": ("production_countries", "blocked_countries")}),
        ("Жанры/Студии/Лицензии/MDL-теги", {"fields": ("genres", "studios", "license_owners", "mdl_tags")}),
        ("Сериал агрегаты", {"fields": ("last_season", "last_episode", "episodes_count", "blocked_seasons")}),
        ("Время", {"fields": ("created_at", "updated_at")}),
    )

    if resources:
        resource_classes = [MaterialResource]

    # агрегаты
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            _versions=Count("versions", distinct=True),
            _seasons=Count("versions__seasons", distinct=True),
            _episodes=Count("versions__seasons__episodes", distinct=True),
        )
        return qs

    @admin.display(description="", ordering=None)
    def thumb(self, obj: Material):
        url = obj.poster_url or (getattr(obj, "extra", None).poster_url if getattr(obj, "extra", None) else "")
        if not url:
            return "—"
        return format_html('<img src="{}" style="height:40px; border-radius:4px;" />', url)

    @admin.display(description="Постер", ordering=None)
    def poster_preview(self, obj: Material):
        url = obj.poster_url or (getattr(obj, "extra", None).poster_url if getattr(obj, "extra", None) else "")
        if not url:
            return "—"
        return format_html('<img src="{}" style="max-height:240px; border:1px solid #ddd; border-radius:8px;" />', url)

    @admin.display(boolean=True, description="KP")
    def has_kp(self, obj: Material):
        return bool(obj.kinopoisk_id)

    @admin.display(boolean=True, description="IMDb")
    def has_imdb(self, obj: Material):
        return bool(obj.imdb_id)

    @admin.display(boolean=True, description="MDL")
    def has_mdl(self, obj: Material):
        return bool(obj.mdl_id)

    @admin.display(boolean=True, description="Shiki")
    def has_shiki(self, obj: Material):
        return bool(obj.shikimori_id)

    @admin.display(description="Версий", ordering="_versions")
    def versions_count(self, obj: Material):
        url = admin_changelist_url(MaterialVersion, material__kodik_id=obj.pk)
        return format_html('<a href="{}">{}</a>', url, obj._versions)

    @admin.display(description="Сезонов", ordering="_seasons")
    def seasons_total(self, obj: Material):
        url = admin_changelist_url(Season, version__material__kodik_id=obj.pk)
        return format_html('<a href="{}">{}</a>', url, obj._seasons)

    @admin.display(description="Серий", ordering="_episodes")
    def episodes_total(self, obj: Material):
        url = admin_changelist_url(Episode, season__version__material__kodik_id=obj.pk)
        return format_html('<a href="{}">{}</a>', url, obj._episodes)

    # агрегаты Extra в list_display
    @admin.display(description="Комм.", ordering="extra__comments_count")
    def comments_count_col(self, obj: Material):
        extra = getattr(obj, "extra", None)
        return extra.comments_count if extra else 0

    @admin.display(description="AKI ★", ordering="extra__aki_rating")
    def aki_rating_col(self, obj: Material):
        extra = getattr(obj, "extra", None)
        return extra.aki_rating if extra and extra.aki_rating is not None else "—"

    @admin.display(description="AKI голосов", ordering="extra__aki_votes")
    def aki_votes_col(self, obj: Material):
        extra = getattr(obj, "extra", None)
        return extra.aki_votes if extra else 0

    @admin.display(description="Просмотры", ordering="extra__views_count")
    def views_count_col(self, obj: Material):
        extra = getattr(obj, "extra", None)
        return extra.views_count if extra else 0

    # object action (кнопка)
    def open_public_api(self, obj: Material):
        # путь совпадает с твоим роутером: /api/kodik/materials/<slug>/
        url = f"/api/kodik/materials/{obj.slug}/"
        return format_html('<a class="button" href="{}" target="_blank">API</a>', url)

    open_public_api.short_description = "Открыть API"

    # ===== Внутренний хелпер округления
    def _round_to_tenth(self, x):
        if x is None:
            return None
        return Decimal(str(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    # ===== Экшен пересчёта агрегатов по выбранным материалам
    @admin.action(description="Пересчитать агрегаты (comments_count / aki_votes / aki_rating)")
    def recalc_material_aggregates(self, request, queryset):
        mids = list(queryset.values_list("pk", flat=True))

        # comments_count (published & not deleted)
        comments = (
            MaterialComment.objects
            .filter(material_id__in=mids, is_deleted=False, status=MaterialCommentStatus.PUBLISHED)
            .values("material_id")
            .annotate(cnt=Count("id"))
        )
        by_mid_comments = {row["material_id"]: row["cnt"] for row in comments}

        # aki (avg/votes)
        ratings = (
            AkiUserRating.objects
            .filter(material_id__in=mids)
            .values("material_id")
            .annotate(votes=Count("id"), avg=Avg("score"))
        )
        by_mid_ratings = {row["material_id"]: row for row in ratings}

        with transaction.atomic():
            mats = Material.objects.in_bulk(mids)
            for mid in mids:
                m = mats.get(mid)
                if not m:
                    continue
                extra = getattr(m, "extra", None) or MaterialExtra.objects.create(material=m)
                extra.comments_count = by_mid_comments.get(mid, 0)
                r = by_mid_ratings.get(mid)
                extra.aki_votes = (r or {}).get("votes", 0) or 0
                avg = (r or {}).get("avg")
                extra.aki_rating = self._round_to_tenth(avg) if avg is not None else None
                extra.save(update_fields=["comments_count", "aki_votes", "aki_rating"])

        self.message_user(request, f"Агрегаты пересчитаны для {len(mids)} материалов")


# ============ MATERIAL VERSION (переводы) ============

@admin.register(MaterialVersion)
class MaterialVersionAdmin(admin.ModelAdmin):
    save_on_top = True
    list_select_related = ("material", "translation")
    list_per_page = 50

    list_display = ("id", "material_link", "translation", "movie_link_short", "seasons_count", "episodes_count")
    list_filter = (
        ("translation", RelatedDropdownFilter) if RelatedDropdownFilter else "translation",
        ("translation__type", ChoiceDropdownFilter) if ChoiceDropdownFilter else "translation__type",
    )
    search_fields = ("material__title", "translation__title", "material__kodik_id")
    ordering = ("-id",)

    autocomplete_fields = ("material", "translation")
    inlines = (SeasonInline,)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_seasons=Count("seasons", distinct=True), _episodes=Count("seasons__episodes", distinct=True))
        )

    @admin.display(description="Материал", ordering="material__title")
    def material_link(self, obj: MaterialVersion):
        url = admin_change_url(obj.material)
        return format_html('<a href="{}">{}</a>', url, obj.material.title)

    @admin.display(description="Сезонов", ordering="_seasons")
    def seasons_count(self, obj: MaterialVersion):
        url = admin_changelist_url(Season, version__id=obj.id)
        return format_html('<a href="{}">{}</a>', url, obj._seasons)

    @admin.display(description="Серий", ordering="_episodes")
    def episodes_count(self, obj: MaterialVersion):
        url = admin_changelist_url(Episode, season__version__id=obj.id)
        return format_html('<a href="{}">{}</a>', url, obj._episodes)

    @admin.display(description="Ссылка (фильм)")
    def movie_link_short(self, obj: MaterialVersion):
        link = getattr(obj, "movie_link", "") or ""
        if not link:
            return "—"
        txt = link[:60] + ("…" if len(link) > 60 else "")
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', link, txt)


# ============ SEASON ============

@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    save_on_top = True
    list_select_related = ("version", "version__material", "version__translation")
    list_per_page = 50

    list_display = ("id", "material_title", "translation_title", "number", "link", "episodes_count", "open_episodes")
    list_filter = (
        ("version__translation", RelatedDropdownFilter) if RelatedDropdownFilter else "version__translation",
    )
    search_fields = ("version__material__title", "version__material__kodik_id")
    ordering = ("version__material__title", "number")

    autocomplete_fields = ("version",)
    inlines = (EpisodeInline,)

    @admin.display(description="Материал", ordering="version__material__title")
    def material_title(self, obj: Season):
        url = admin_change_url(obj.version.material)
        return format_html('<a href="{}">{}</a>', url, obj.version.material.title)

    @admin.display(description="Перевод", ordering="version__translation__title")
    def translation_title(self, obj: Season):
        return obj.version.translation.title

    @admin.display(description="Серий")
    def episodes_count(self, obj: Season):
        return obj.episodes.count()

    @admin.display(description="Открыть серии")
    def open_episodes(self, obj: Season):
        url = admin_changelist_url(Episode, season__id=obj.id)
        return format_html('<a class="button" href="{}">Открыть</a>', url)


# ============ EPISODE ============

@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    save_on_top = True
    list_select_related = ("season", "season__version", "season__version__material", "season__version__translation")
    list_per_page = 50

    list_display = ("id", "material_title", "translation_title", "season_number", "number", "title", "link_short")
    list_filter = (
        ("season__version__translation", RelatedDropdownFilter) if RelatedDropdownFilter else "season__version__translation",
        ("season", RelatedDropdownFilter) if RelatedDropdownFilter else "season",
    )
    search_fields = ("title", "season__version__material__title", "season__version__material__kodik_id")
    ordering = ("season__version__material__title", "season__number", "number")

    autocomplete_fields = ("season",)

    @admin.display(description="Материал", ordering="season__version__material__title")
    def material_title(self, obj: Episode):
        m = obj.season.version.material
        return format_html('<a href="{}">{}</a>', admin_change_url(m), m.title)

    @admin.display(description="Перевод", ordering="season__version__translation__title")
    def translation_title(self, obj: Episode):
        return obj.season.version.translation.title

    @admin.display(description="Сезон", ordering="season__number")
    def season_number(self, obj: Episode):
        return obj.season.number

    @admin.display(description="Ссылка")
    def link_short(self, obj: Episode):
        if not obj.link:
            return "—"
        text = obj.link[:70] + ("…" if len(obj.link) > 70 else "")
        return format_html('<a href="{0}" target="_blank" rel="noopener noreferrer">{1}</a>', obj.link, text)


# ============ CREDIT ============

@admin.register(Credit)
class CreditAdmin(admin.ModelAdmin):
    save_on_top = True
    list_select_related = ("material", "person")
    list_per_page = 50

    list_display = ("id", "material_link", "role", "person_link")
    list_filter = (("role", ChoiceDropdownFilter) if ChoiceDropdownFilter else "role",)
    search_fields = ("material__title", "person__name")
    ordering = ("material__title", "role", "person__name")

    autocomplete_fields = ("material", "person")

    @admin.display(description="Материал", ordering="material__title")
    def material_link(self, obj: Credit):
        return format_html('<a href="{}">{}</a>', admin_change_url(obj.material), obj.material.title)

    @admin.display(description="Персона", ordering="person__name")
    def person_link(self, obj: Credit):
        return format_html('<a href="{}">{}</a>', admin_change_url(obj.person), obj.person.name)


# ===================== ДОП. РЕГИСТРАЦИИ =====================

# (1) MaterialExtra — отдельно (read-only просмотр)
@admin.register(MaterialExtra)
class MaterialExtraAdmin(admin.ModelAdmin):
    list_select_related = ("material",)
    list_display = ("id", "material_link", "comments_count", "aki_votes", "aki_rating", "views_count")
    search_fields = ("material__title", "material__kodik_id")
    readonly_fields = [f.name for f in MaterialExtra._meta.fields]

    @admin.display(description="Материал", ordering="material__title")
    def material_link(self, obj: MaterialExtra):
        return format_html('<a href="{}">{}</a>', admin_change_url(obj.material), obj.material.title)


# (2) AkiUserRating
@admin.register(AkiUserRating)
class AkiUserRatingAdmin(admin.ModelAdmin):
    list_select_related = ("material", "user")
    list_per_page = 50
    date_hierarchy = "created_at"

    list_display = ("id", "material_link", "user_link", "score", "created_at", "updated_at")
    search_fields = ("material__title", "material__kodik_id", "user__username", "user__email")
    ordering = ("-created_at",)
    list_filter = (
        ("material", RelatedDropdownFilter) if RelatedDropdownFilter else "material",
    )

    @admin.display(description="Материал", ordering="material__title")
    def material_link(self, obj: AkiUserRating):
        return format_html('<a href="{}">{}</a>', admin_change_url(obj.material), obj.material.title)

    @admin.display(description="Пользователь", ordering="user__username")
    def user_link(self, obj: AkiUserRating):
        return format_html('<a href="{}">{}</a>', admin_change_url(obj.user), obj.user)


# (3) MaterialComment
@admin.register(MaterialComment)
class MaterialCommentAdmin(admin.ModelAdmin):
    list_select_related = ("material", "user", "parent")
    list_per_page = 50
    date_hierarchy = "created_at"

    def _content_short(self, obj: "MaterialComment"):
        text = (obj.content or "").strip()
        return (text[:80] + "…") if len(text) > 80 else (text or "—")

    @admin.display(description="Комментарий")
    def content_short(self, obj: "MaterialComment"):
        return self._content_short(obj)

    @admin.display(description="Материал", ordering="material__title")
    def material_link(self, obj: "MaterialComment"):
        return format_html('<a href="{}">{}</a>', admin_change_url(obj.material), obj.material.title)

    @admin.display(description="Автор", ordering="user__username")
    def user_link(self, obj: "MaterialComment"):
        return format_html('<a href="{}">{}</a>', admin_change_url(obj.user), obj.user)

    @admin.display(description="Родитель")
    def parent_link(self, obj: "MaterialComment"):
        if not obj.parent_id:
            return "—"
        return format_html('<a href="{}">#{}</a>', admin_change_url(obj.parent), obj.parent_id)

    list_display = (
        "id",
        "material_link",
        "user_link",
        "parent_link",
        "content_short",
        "status",
        "is_deleted",
        "is_pinned",
        "likes_count",
        "replies_count",
        "created_at",
    )
    list_display_links = ("id", "content_short")
    search_fields = ("content", "user__username", "material__title", "material__kodik_id")
    ordering = ("-created_at",)

    list_filter = (
        ("material", RelatedDropdownFilter) if RelatedDropdownFilter else "material",
        ("user", RelatedDropdownFilter) if RelatedDropdownFilter else "user",
        ("status", ChoiceDropdownFilter) if ChoiceDropdownFilter else "status",
        "is_deleted",
        "is_pinned",
        ("created_at", DateTimeRangeFilter),
    )

    actions = (
        "action_publish",
        "action_hide",
        "action_soft_delete",
        "action_restore",
        "action_pin",
        "action_unpin",
    )

    @admin.action(description="Опубликовать")
    def action_publish(self, request, queryset):
        updated = queryset.update(status=MaterialCommentStatus.PUBLISHED)
        self.message_user(request, f"Опубликовано: {updated}")

    @admin.action(description="Скрыть")
    def action_hide(self, request, queryset):
        updated = queryset.update(status=MaterialCommentStatus.HIDDEN)
        self.message_user(request, f"Скрыто: {updated}")

    @admin.action(description="Мягко удалить (is_deleted=True)")
    def action_soft_delete(self, request, queryset):
        n = 0
        for obj in queryset:
            obj.is_deleted = True
            obj.save(update_fields=["is_deleted"])
            n += 1
        self.message_user(request, f"Помечено удалённым: {n}")

    @admin.action(description="Восстановить (is_deleted=False)")
    def action_restore(self, request, queryset):
        updated = queryset.update(is_deleted=False)
        self.message_user(request, f"Восстановлено: {updated}")

    @admin.action(description="Закрепить (is_pinned=True)")
    def action_pin(self, request, queryset):
        updated = queryset.update(is_pinned=True)
        self.message_user(request, f"Закреплено: {updated}")

    @admin.action(description="Открепить (is_pinned=False)")
    def action_unpin(self, request, queryset):
        updated = queryset.update(is_pinned=False)
        self.message_user(request, f"Откреплено: {updated}")


# (4) MaterialCommentLike
@admin.register(MaterialCommentLike)
class MaterialCommentLikeAdmin(admin.ModelAdmin):
    list_select_related = ("comment", "comment__material", "user")
    list_per_page = 50
    date_hierarchy = "created_at"

    list_display = ("id", "comment_link", "material_link", "user_link", "created_at")
    search_fields = ("comment__content", "comment__material__title", "user__username", "user__email")
    ordering = ("-created_at",)
    list_filter = (
        ("comment__material", RelatedDropdownFilter) if RelatedDropdownFilter else "comment__material",
        ("created_at", DateRangeFilter),
    )

    @admin.display(description="Комментарий", ordering="comment_id")
    def comment_link(self, obj: MaterialCommentLike):
        txt = (obj.comment.content or "").strip()
        short = (txt[:60] + "…") if len(txt) > 60 else (txt or "—")
        return format_html('<a href="{}">#{}</a> — {}', admin_change_url(obj.comment), obj.comment_id, short)

    @admin.display(description="Материал", ordering="comment__material__title")
    def material_link(self, obj: MaterialCommentLike):
        m = obj.comment.material
        return format_html('<a href="{}">{}</a>', admin_change_url(m), m.title)

    @admin.display(description="Пользователь", ordering="user__username")
    def user_link(self, obj: MaterialCommentLike):
        return format_html('<a href="{}">{}</a>', admin_change_url(obj.user), obj.user)
