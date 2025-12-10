# coding: utf-8
from __future__ import annotations

from django.contrib import admin
from django.db import models
from tinymce.widgets import TinyMCE

from .models import Post, Category, Tag


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "pinned", "published_at", "created_at")
    list_filter = ("status", "pinned", "categories", "tags")
    search_fields = ("title", "excerpt", "content_html")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("categories", "tags")
    readonly_fields = ("created_at", "updated_at")
    formfield_overrides = {
        models.TextField: {"widget": TinyMCE()},
    }


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    prepopulated_fields = {"slug": ("name",)}
