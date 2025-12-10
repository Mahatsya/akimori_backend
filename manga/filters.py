from django.db.models import Q
from django_filters import rest_framework as filters
from .models import Manga


class MangaFilter(filters.FilterSet):
    q = filters.CharFilter(method="filter_q")
    type = filters.CharFilter(field_name="type", lookup_expr="iexact")
    year = filters.NumberFilter(field_name="year")
    work_status = filters.CharFilter(field_name="work_status", lookup_expr="iexact")
    genre = filters.CharFilter(method="filter_genre")
    category = filters.CharFilter(method="filter_category")

    class Meta:
        model = Manga
        fields = ["type", "year", "work_status"]

    def filter_q(self, queryset, name, value):
        if not value:
            return queryset
        value = value.strip()
        return queryset.filter(
            Q(title_ru__icontains=value) |
            Q(title_en__icontains=value) |
            Q(alt_titles__icontains=value)
        )

    def filter_genre(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(genres__slug=value)

    def filter_category(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(categories__slug=value)
