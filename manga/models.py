from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.conf import settings
from django.db.models import UniqueConstraint
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
import os


# ===== Универсальный таймстамп =====
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ===== Справочники =====
class Category(TimeStampedModel):
    title = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=160, unique=True, db_index=True)

    class Meta:
        ordering = ("title",)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:160]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Genre(TimeStampedModel):
    title = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=160, unique=True, db_index=True)

    class Meta:
        ordering = ("title",)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:160]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class TranslatorPublisher(TimeStampedModel):
    """Группа переводчиков / паблишер."""
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, db_index=True)
    avatar_url = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    followers_count = models.PositiveIntegerField(default=0)
    manga_count = models.PositiveIntegerField(default=0)

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="TranslatorMember",
        related_name="translator_groups",
        blank=True,
    )

    class Meta:
        ordering = ("name",)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:220]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TranslatorMember(TimeStampedModel):
    """Участник группы переводчиков/паблишера с ролью."""
    class Role(models.TextChoices):
        OWNER = "owner", "Владелец"
        MODERATOR = "moderator", "Модератор"
        PUBLISHER = "publisher", "Паблишер"
        MEMBER = "member", "Участник"

    translator = models.ForeignKey(
        TranslatorPublisher,
        on_delete=models.CASCADE,
        related_name="translatormember_set",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="translator_membership",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    title = models.CharField(max_length=120, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("translator__name", "user_id")
        constraints = [
            models.UniqueConstraint(fields=["translator", "user"], name="uniq_translator_user"),
        ]
        indexes = [
            models.Index(fields=["translator", "role"]),
            models.Index(fields=["user", "role"]),
        ]

    def __str__(self):
        return f"{self.translator.name}: {self.user} ({self.role})"

    @property
    def can_moderate(self) -> bool:
        return self.role in {self.Role.OWNER, self.Role.MODERATOR}

    @property
    def can_publish(self) -> bool:
        return self.role in {self.Role.OWNER, self.Role.MODERATOR, self.Role.PUBLISHER}


# ===== Manga =====

def poster_upload_to(instance, filename):
    # media/manga/<slug>/poster.<ext>
    base, ext = os.path.splitext(filename)
    ext = (ext or ".jpg").lower()
    return f"manga/{instance.slug or 'manga'}/poster{ext}"


def banner_upload_to(instance, filename):
    # media/manga/<slug>/banner.<ext>
    base, ext = os.path.splitext(filename)
    ext = (ext or ".jpg").lower()
    return f"manga/{instance.slug or 'manga'}/banner{ext}"


class Manga(TimeStampedModel):
    class MangaType(models.TextChoices):
        MANGA = "manga", "Манга"
        MANHWA = "manhwa", "Манхва"
        MANHUA = "manhua", "Маньхуа"
        ONE_SHOT = "one-shot", "Ваншот"
        DOUJINSHI = "doujinshi", "Додзинси"
        OTHER = "other", "Другое"

    class WorkStatus(models.TextChoices):
        ONGOING = "ongoing", "Онгоинг"
        COMPLETED = "completed", "Завершено"
        HIATUS = "hiatus", "Пауза"
        FROZEN = "frozen", "Заморожено"
        ANNOUNCED = "announced", "Анонс"

    # Основные поля
    title_ru = models.CharField(max_length=255, db_index=True)
    title_en = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    alt_titles = models.JSONField(default=list, blank=True)

    slug = models.SlugField(max_length=260, unique=True, db_index=True)

    type = models.CharField(max_length=20, choices=MangaType.choices, default=MangaType.MANGA)
    age_rating = models.CharField(max_length=4, blank=True, null=True)
    year = models.PositiveIntegerField(blank=True, null=True,
                                       validators=[MinValueValidator(1900), MaxValueValidator(2100)])

    # ⬇️ теперь файлы (вместо URL-полей)
    poster = models.ImageField(
        upload_to=poster_upload_to,
        blank=True, null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
        help_text="Постер манги (jpg/png/webp)",
    )
    banner = models.ImageField(
        upload_to=banner_upload_to,
        blank=True, null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
        help_text="Шапка/баннер (jpg/png/webp)",
    )

    description = models.TextField(blank=True, null=True)

    work_status = models.CharField(max_length=20, choices=WorkStatus.choices, default=WorkStatus.ONGOING)

    # Классификация
    categories = models.ManyToManyField(Category, related_name="manga", blank=True)
    genres = models.ManyToManyField(Genre, related_name="manga", blank=True)

    # Внешние ссылки (массив объектов {title,url})
    links = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["title_ru"]),
            models.Index(fields=["title_en"]),
            models.Index(fields=["type"]),
            models.Index(fields=["work_status"]),
            models.Index(fields=["year"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = self.title_ru or self.title_en or "manga"
            self.slug = slugify(base)[:240]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title_ru or self.title_en or f"Manga #{self.pk}"

    # совместимость для фронта:
    @property
    def poster_url(self):
        try:
            return self.poster.url if self.poster else None
        except ValueError:
            return None

    @property
    def banner_url(self):
        try:
            return self.banner.url if self.banner else None
        except ValueError:
            return None


# ===== Издания/главы/страницы =====
class Edition(TimeStampedModel):
    """Издание для конкретной манги у конкретного переводчика/паблишера."""
    class TranslationStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", "Перевод идёт"
        COMPLETED = "completed", "Перевод завершён"
        DROPPED = "dropped", "Брошено"

    manga = models.ForeignKey(Manga, on_delete=models.CASCADE, related_name="editions")
    translator = models.ForeignKey(TranslatorPublisher, on_delete=models.CASCADE, related_name="editions")
    translation_status = models.CharField(max_length=20, choices=TranslationStatus.choices,
                                          default=TranslationStatus.IN_PROGRESS)

    class Meta:
        unique_together = (("manga", "translator"),)
        ordering = ("translator__name",)
        indexes = [models.Index(fields=["manga", "translator"])]

    def __str__(self):
        return f"{self.manga} — {self.translator}"


def page_upload_to(instance, filename):
    # media/manga/{manga_slug}/{edition_id}/ch_{chapter_id}/{order}.{ext}
    base, ext = os.path.splitext(filename)
    ext = ext.lower()
    return (
        f"manga/{instance.chapter.edition.manga.slug}/"
        f"{instance.chapter.edition_id}/"
        f"ch_{instance.chapter_id}/"
        f"{instance.order:04d}{ext}"
    )


class Chapter(TimeStampedModel):
    """Глава внутри издания."""
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="chapters")
    number = models.DecimalField(max_digits=5, decimal_places=2)  # 000.00 … 999.99
    name = models.CharField(max_length=255, blank=True, null=True)
    volume = models.PositiveIntegerField(blank=True, null=True)
    pages_count = models.PositiveIntegerField(blank=True, null=True)

    published_at = models.DateTimeField(db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="uploaded_chapters"
    )

    class Meta:
        ordering = ("-number",)
        unique_together = (("edition", "number"),)
        indexes = [
            models.Index(fields=["edition", "number"]),
            models.Index(fields=["published_at"]),
        ]

    def __str__(self):
        return f"{self.edition} — ch.{self.number}"

    def recalc_pages_count(self):
        cnt = self.pages.count()
        if self.pages_count != cnt:
            self.pages_count = cnt
            self.save(update_fields=["pages_count", "updated_at"])


class ChapterPage(TimeStampedModel):
    """Изображение одной страницы главы."""
    class ImageType(models.TextChoices):
        PAGE = "page", "Страница"

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="pages")
    image = models.ImageField(upload_to=page_upload_to)
    order = models.PositiveIntegerField(default=1, db_index=True)
    type = models.CharField(max_length=16, choices=ImageType.choices, default=ImageType.PAGE)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="uploaded_pages"
    )

    class Meta:
        ordering = ("order",)
        unique_together = (("chapter", "order"),)
        indexes = [models.Index(fields=["chapter", "order"])]

    def __str__(self):
        return f"{self.chapter} #{self.order}"


# ===== Сигналы: удаляем старые файлы при замене/удалении =====
def _delete_file(fieldfile):
    try:
        storage = fieldfile.storage
        name = fieldfile.name
        if name and storage.exists(name):
            storage.delete(name)
    except Exception:
        pass

@receiver(pre_save, sender=Manga)
def cleanup_old_media_on_change(sender, instance: Manga, **kwargs):
    if not instance.pk:
        return
    try:
        prev = Manga.objects.get(pk=instance.pk)
    except Manga.DoesNotExist:
        return
    if prev.poster and instance.poster and prev.poster.name != instance.poster.name:
        _delete_file(prev.poster)
    if prev.banner and instance.banner and prev.banner.name != instance.banner.name:
        _delete_file(prev.banner)

@receiver(post_delete, sender=Manga)
def cleanup_media_on_delete(sender, instance: Manga, **kwargs):
    if instance.poster:
        _delete_file(instance.poster)
    if instance.banner:
        _delete_file(instance.banner)
