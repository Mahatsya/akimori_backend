# kodik/filters.py
from __future__ import annotations

from django.db import models
import django_filters as df

from .models import Material
from .filters_any import AnyFieldFilterSet


_ALLOWED_STATUS = {"anons", "ongoing", "released"}


class MaterialFilter(AnyFieldFilterSet):
    """
    Фильтры каталога (django-filters).

    ВАЖНО:
    - Поиск по названию теперь делается через DRF SearchFilter (в views.py) по параметру ?q=...
    - Поэтому здесь НЕТ q=df.CharFilter(...) и НЕТ filter_q(...)
    """

    # --- Алиасы для года по year_effective (а не по «сырому» year) ---
    year = df.NumberFilter(method="filter_year_effective")
    year_from = df.NumberFilter(method="filter_year_from_effective")
    year_to = df.NumberFilter(method="filter_year_to_effective")

    # --- Диапазон по aired_at (если нужен именно источник aired_at) ---
    aired_from = df.DateFilter(field_name="extra__aired_at", lookup_expr="gte")
    aired_to = df.DateFilter(field_name="extra__aired_at", lookup_expr="lte")

    # --- Диапазон по updated_at (для «за сегодня» / «за неделю») ---
    updated_at_from = df.DateFilter(field_name="updated_at", lookup_expr="gte")
    updated_at_to = df.DateFilter(field_name="updated_at", lookup_expr="lte")

    # --- Таксономии и простые алиасы ---
    type = df.CharFilter(method="filter_type")
    country = df.CharFilter(method="filter_country")
    genre = df.CharFilter(method="filter_genre")
    studio = df.CharFilter(method="filter_studio")

    # --- MPAA ---
    rating_mpaa = df.CharFilter(method="filter_rating_mpaa")

    # --- Статусы ---
    all_status = df.CharFilter(method="filter_all_status")
    anime_status = df.CharFilter(method="filter_anime_status")
    drama_status = df.CharFilter(method="filter_drama_status")

    class Meta:
        model = Material
        fields = []

    # ✅ чтобы динамический AnyFieldFilterSet не трогал эти ключи
    DYN_RESERVED_KEYS = ("page", "per_page", "ordering", "sort", "page_size", "q", "search")

    # Разрешённые поля для динамического миксина
    DYN_ALLOWED_FIELDS = [
        # прямые
        "slug", "type", "title", "title_orig", "other_title",
        "year", "quality", "camrip", "lgbt",
        "kinopoisk_id", "imdb_id", "mdl_id", "shikimori_id",
        "created_at", "updated_at",

        # extra (one-to-one)
        "extra__title", "extra__anime_title", "extra__title_en",
        "extra__anime_kind",
        "extra__all_status", "extra__anime_status", "extra__drama_status",
        "extra__aired_at", "extra__released_at", "extra__premiere_ru", "extra__premiere_world",
        "extra__kinopoisk_rating", "extra__imdb_rating", "extra__shikimori_rating",

        # 🔥 Akimori + будущие эпизоды + просмотры
        "extra__aki_rating",
        "extra__aki_votes",
        "extra__next_episode_at",
        "extra__views_count",

        # связи
        "genres__name", "genres__slug",
        "studios__name",
        "production_countries__code", "production_countries__name",
        "blocked_countries__code",
        "license_owners__name",
        "mdl_tags__name", "mdl_tags__slug",
    ]

    # --------------- Хелперы ---------------
    @staticmethod
    def _split_list(value: str) -> list[str]:
        return [part.strip() for part in (value or "").split(",") if part.strip()]

    # --------------- Тип/страна/жанр/студия ---------------
    def filter_type(self, qs, name, value):
        items = [i.lower() for i in self._split_list(value)]
        return qs if not items else qs.filter(type__in=items)

    def filter_country(self, qs, name, value):
        items = [s.upper() for s in self._split_list(value)]
        return qs if not items else qs.filter(production_countries__code__in=items).distinct()

    def filter_genre(self, qs, name, value):
        """
        Жёстко используем Shikimori-жанры: slug + source='shikimori'
        """
        slugs = [s.strip().lower() for s in self._split_list(value)]
        if not slugs:
            return qs

        return qs.filter(
            genres__slug__in=slugs,
            genres__source="shikimori",
        ).distinct()

    def filter_studio(self, qs, name, value):
        items = self._split_list(value)
        if not items:
            return qs
        q = models.Q()
        for s in items:
            q |= models.Q(studios__name__icontains=s)
        return qs.filter(q).distinct()

    # --------------- MPAA ---------------
    def filter_rating_mpaa(self, qs, name, value):
        items = [s.upper() for s in self._split_list(value)]
        return qs if not items else qs.filter(extra__rating_mpaa__in=items)

    # --------------- Статусы ---------------
    def _status_in(self, qs, db_field: str, value: str):
        vals = [v for v in self._split_list(value) if v in _ALLOWED_STATUS]
        return qs if not vals else qs.filter(**{f"{db_field}__in": vals})

    def filter_all_status(self, qs, name, value):
        return self._status_in(qs, "extra__all_status", value)

    def filter_anime_status(self, qs, name, value):
        return self._status_in(qs, "extra__anime_status", value)

    def filter_drama_status(self, qs, name, value):
        return self._status_in(qs, "extra__drama_status", value)

    # --------------- Годы по year_effective ---------------
    def filter_year_effective(self, qs, name, value):
        if value in (None, ""):
            return qs
        return qs.filter(year_effective=value)

    def filter_year_from_effective(self, qs, name, value):
        if value in (None, ""):
            return qs
        return qs.filter(year_effective__gte=value)

    def filter_year_to_effective(self, qs, name, value):
        if value in (None, ""):
            return qs
        return qs.filter(year_effective__lte=value)
