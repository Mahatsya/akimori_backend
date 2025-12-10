# coding: utf-8
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify as dj_slugify
from tinymce.models import HTMLField

# Попробуем использовать python-slugify для качественной транслитерации
# pip install python-slugify Unidecode
try:
    from slugify import slugify as py_slugify
except ImportError:
    py_slugify = None


def make_slug(source: str, *, fallback: str = "novost", max_len: int = 60) -> str:
    """
    Делает слаг из произвольной строки (в т.ч. кириллицы).
    - Сначала пытается python-slugify (лучше транслитерирует),
    - если пакета нет — использует стандартный django.slugify.
    - Если всё равно пусто — возвращает fallback.
    """
    text = (source or "").strip()
    if py_slugify:
        s = py_slugify(text, lowercase=True, max_length=max_len)
    else:
        s = dj_slugify(text)[:max_len]
    return s or fallback


class Category(models.Model):
    name = models.CharField("Название", max_length=120, unique=True)
    slug = models.SlugField("Слаг", max_length=140, unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name, max_len=140)
        super().save(*args, **kwargs)


class Tag(models.Model):
    name = models.CharField("Тег", max_length=80, unique=True)
    slug = models.SlugField("Слаг", max_length=100, unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Тег"
        verbose_name_plural = "Теги"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name, max_len=100)
        super().save(*args, **kwargs)


class Post(models.Model):
    STATUS = (
        ("draft", "Черновик"),
        ("published", "Опубликовано"),
        ("archived", "Архив"),
    )

    title = models.CharField("Заголовок", max_length=200)
    slug = models.SlugField("Слаг", max_length=220, unique=True, blank=True)

    content_html = HTMLField("Содержимое")
    excerpt = models.TextField("Короткое описание", blank=True)

    poster = models.ImageField(
        "Постер", upload_to="blog/posters/%Y/%m/", blank=True, null=True
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
    )

    categories = models.ManyToManyField(
        "Category", verbose_name="Категории", related_name="posts", blank=True
    )
    tags = models.ManyToManyField(
        "Tag", verbose_name="Теги", related_name="posts", blank=True
    )

    pinned = models.BooleanField("Закрепить", default=False)
    is_closed = models.BooleanField("Закрыт (комменты/обсуждение)", default=False)

    status = models.CharField("Статус", max_length=12, choices=STATUS, default="draft")
    published_at = models.DateTimeField("Опубликовано", blank=True, null=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-pinned", "-published_at", "-created_at"]
        verbose_name = "Новость/Пост"
        verbose_name_plural = "Новости/Посты"
        indexes = [
            models.Index(fields=["status", "pinned"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["-published_at"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Генерим slug только если он ещё пуст (чтобы не ломать ссылки при редактировании)
        if not self.slug:
            base = make_slug(self.title, fallback="novost", max_len=60)
            candidate, i = base, 2
            # Уникализируем: base, base-2, base-3, ...
            while (
                Post.objects.filter(slug=candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                candidate = f"{base}-{i}"
                i += 1
            self.slug = candidate

        # auto published_at
        if self.status == "published" and not self.published_at:
            self.published_at = timezone.now()

        # excerpt auto из HTML, если пустой
        if not self.excerpt and self.content_html:
            import re

            txt = re.sub("<[^>]+>", " ", self.content_html or "")
            txt = " ".join(txt.split())
            self.excerpt = txt[:200]

        super().save(*args, **kwargs)
