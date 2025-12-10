from django.contrib import admin
from .models import HeaderMaterialContent


@admin.register(HeaderMaterialContent)
class HeaderMaterialContentAdmin(admin.ModelAdmin):
    list_display = ("id", "material", "is_active", "position", "created_at")
    list_filter = ("is_active",)
    search_fields = ("material__title", "material__slug", "material__kodik_id")
    ordering = ("position", "-created_at")
    raw_id_fields = ("material",)
