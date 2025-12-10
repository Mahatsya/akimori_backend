from django_filters import rest_framework as filters
from django.db import models
from .models import Post

class PostFilter(filters.FilterSet):
    q = filters.CharFilter(method="filter_q")
    category = filters.CharFilter(field_name="categories__slug")
    tag = filters.CharFilter(field_name="tags__slug")
    status = filters.CharFilter(field_name="status")
    pinned = filters.BooleanFilter(field_name="pinned")
    is_closed = filters.BooleanFilter(field_name="is_closed")
    date_from = filters.IsoDateTimeFilter(field_name="published_at", lookup_expr="gte")
    date_to = filters.IsoDateTimeFilter(field_name="published_at", lookup_expr="lte")

    class Meta:
        model = Post
        fields = ["q", "category", "tag", "status", "pinned", "is_closed", "date_from", "date_to"]

    def filter_q(self, qs, name, value):
        return qs.filter(
            models.Q(title__icontains=value) |
            models.Q(excerpt__icontains=value) |
            models.Q(content_html__icontains=value)
        )
