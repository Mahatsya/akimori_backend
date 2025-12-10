# forum/models.py
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils import timezone

# внешние приложения
from manga.models import Manga, TranslatorPublisher, TranslatorMember
from kodik.models import Material


# --------------------------------- базовая метка времени ---------------------------------

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("Создано", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        abstract = True


# --------------------------------- Тип темы (настраиваемый) ---------------------------------

class ThreadKind(TimeStampedModel):
    title = models.CharField("Название типа", max_length=100, unique=True)
    slug = models.SlugField("Слаг", max_length=120, unique=True)
    description = models.TextField("Описание", blank=True)
    is_active = models.BooleanField("Активен", default=True)
    order = models.PositiveIntegerField("Порядок", default=100)

    # какие привязки разрешены
    allow_anime = models.BooleanField("Разрешить привязку к аниме", default=False)
    allow_manga = models.BooleanField("Разрешить привязку к манге", default=False)
    allow_publish_as_team = models.BooleanField("Разрешить публиковать от имени команды", default=True)

    class Meta:
        verbose_name = "Тип темы"
        verbose_name_plural = "Типы тем"
        ordering = ("order", "title")

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:120]
        super().save(*args, **kwargs)


# --------------------------------- Категории ---------------------------------

class Category(TimeStampedModel):
    title = models.CharField("Название", max_length=120, unique=True)
    slug = models.SlugField("Слаг", max_length=140, unique=True)
    is_active = models.BooleanField("Активна", default=True)
    order = models.PositiveIntegerField("Порядок", default=100)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ("order", "title")

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:140]
        super().save(*args, **kwargs)


# --------------------------------- Теги (опционально) ---------------------------------

class Tag(TimeStampedModel):
    title = models.CharField("Тег", max_length=64, unique=True)
    slug = models.SlugField("Слаг", max_length=72, unique=True)

    class Meta:
        verbose_name = "Тег"
        verbose_name_plural = "Теги"
        ordering = ("title",)

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:72]
        super().save(*args, **kwargs)


# --------------------------------- Тема форума ---------------------------------

class Thread(TimeStampedModel):
    category = models.ForeignKey(
        Category, verbose_name="Категория",
        on_delete=models.PROTECT, related_name="threads"
    )

    # кастомный тип
    kind = models.ForeignKey(
        ThreadKind, verbose_name="Тип темы",
        on_delete=models.PROTECT, related_name="threads"
    )

    # кто создал
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Автор",
        on_delete=models.PROTECT, related_name="forum_threads"
    )

    # опционально публикация от имени команды
    publish_as_team = models.ForeignKey(
        TranslatorPublisher,
        verbose_name="От имени команды",
        on_delete=models.PROTECT, null=True, blank=True,
        related_name="forum_threads",
        help_text="Если заполнено — пост отображается от имени команды."
    )

    title = models.CharField("Заголовок", max_length=200)
    slug  = models.SlugField("Слаг", max_length=220, unique=True, db_index=True)
    content = models.TextField("Контент")

    # привязки по типу
    anime = models.ForeignKey(
        Material, verbose_name="Аниме (Kodik)",
        null=True, blank=True, on_delete=models.PROTECT, related_name="forum_threads"
    )
    manga = models.ForeignKey(
        Manga, verbose_name="Манга",
        null=True, blank=True, on_delete=models.PROTECT, related_name="forum_threads"
    )

    # постер и мета
    poster = models.ImageField("Постер", upload_to="forum/posters/%Y/%m/", null=True, blank=True)
    extra = models.JSONField("Доп.мета", default=dict, blank=True)

    # теги
    tags = models.ManyToManyField(Tag, verbose_name="Теги", blank=True, related_name="threads")

    # набор связанных команд (через through с ролью)
    publishers = models.ManyToManyField(
        TranslatorPublisher, through="ThreadPublisher", blank=True, related_name="related_threads",
        verbose_name="Команды переводчиков (связанные с темой)"
    )

    # метрики
    comments_count = models.PositiveIntegerField("Комментариев", default=0)
    last_activity_at = models.DateTimeField("Последняя активность", default=timezone.now, db_index=True)
    is_locked = models.BooleanField("Закрыта", default=False)
    is_pinned = models.BooleanField("Закреплена", default=False)

    class Meta:
        verbose_name = "Тема"
        verbose_name_plural = "Темы"
        ordering = ("-is_pinned", "-last_activity_at", "-created_at")
        indexes = [
            models.Index(fields=["kind", "last_activity_at"]),
            models.Index(fields=["category", "last_activity_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def clean(self):
        # ограничения по kind
        if self.anime and not self.kind.allow_anime:
            raise ValidationError("Выбранный тип темы не позволяет привязывать аниме.")
        if self.manga and not self.kind.allow_manga:
            raise ValidationError("Выбранный тип темы не позволяет привязывать мангу.")
        if self.publish_as_team and not self.kind.allow_publish_as_team:
            raise ValidationError("Выбранный тип темы не позволяет публиковать от имени команды.")

        # автор должен быть в команде если publish_as_team задан
        if self.publish_as_team:
            is_member = TranslatorMember.objects.filter(
                translator=self.publish_as_team, user=self.author, is_active=True
            ).exists()
            if not is_member:
                raise ValidationError("Автор должен быть активным участником выбранной команды.")

        # строгое взаимоисключение (по желанию можно закомментить)
        # if self.anime and self.manga:
        #     raise ValidationError("Нельзя одновременно привязать и аниме, и мангу.")

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "thread"
            self.slug = base[:210]
            i = 2
            Model = self.__class__
            while Model.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                suf = f"-{i}"
                self.slug = (base[:210 - len(suf)]) + suf
                i += 1
        if not self.last_activity_at:
            self.last_activity_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def poster_url(self) -> str | None:
        return self.poster.url if self.poster else None


# --------------------------------- Связь тема ↔ команда ---------------------------------

class ThreadPublisher(TimeStampedModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Основной релиз"
        PARTNER = "partner", "Партнёр"
        SOURCE  = "source",  "Источник"
        OTHER   = "other",   "Другое"

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="thread_publishers")
    publisher = models.ForeignKey(TranslatorPublisher, on_delete=models.PROTECT, related_name="thread_links")
    role = models.CharField("Роль", max_length=16, choices=Role.choices, default=Role.PRIMARY)
    note = models.CharField("Примечание", max_length=200, blank=True)

    class Meta:
        verbose_name = "Связь темы с командой"
        verbose_name_plural = "Связи темы с командами"
        unique_together = (("thread", "publisher", "role"),)

    def __str__(self) -> str:
        return f"{self.thread_id} ↔ {self.publisher_id} ({self.role})"


# --------------------------------- Работы переводчика (аниме/манга) ---------------------------------

class TranslatorWork(TimeStampedModel):
    """
    Универсальная привязка «команда работала над аниме/мангой» с ролью.
    """
    class ContentKind(models.TextChoices):
        ANIME = "anime", "Аниме"
        MANGA = "manga", "Манга"

    class Role(models.TextChoices):
        SUBS  = "subs",  "Субтитры"
        DUB   = "dub",   "Озвучка"
        EDIT  = "edit",  "Редактура"
        RAW   = "raw",   "Raw/Сырые"
        OTHER = "other", "Другое"

    translator = models.ForeignKey(
        TranslatorPublisher, on_delete=models.PROTECT, related_name="works"
    )
    kind  = models.CharField(max_length=16, choices=ContentKind.choices, db_index=True)

    anime = models.ForeignKey(
        Material, null=True, blank=True, on_delete=models.CASCADE, related_name="translator_works"
    )
    manga = models.ForeignKey(
        Manga, null=True, blank=True, on_delete=models.CASCADE, related_name="translator_works"
    )

    role  = models.CharField(max_length=16, choices=Role.choices, default=Role.SUBS)
    note  = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Работа переводчика"
        verbose_name_plural = "Работы переводчиков"
        indexes = [
            models.Index(fields=["kind", "translator"]),
        ]
        constraints = [
            # согласованность kind и целей (ровно одна ветка)
            models.CheckConstraint(
                name="tw_kind_consistency",
                check=(
                    models.Q(kind="anime", anime__isnull=False, manga__isnull=True) |
                    models.Q(kind="manga", manga__isnull=False, anime__isnull=True)
                ),
            ),
        ]

    def clean(self):
        # доп.валидация до БД
        if self.kind == self.ContentKind.ANIME:
            if not self.anime or self.manga:
                raise ValidationError("Для kind=anime укажите только anime (manga пустым).")
        elif self.kind == self.ContentKind.MANGA:
            if not self.manga or self.anime:
                raise ValidationError("Для kind=manga укажите только manga (anime пустым).")

    def __str__(self) -> str:
        target = f"a{self.anime_id}" if self.anime_id else f"m{self.manga_id}"
        return f"{self.get_kind_display()} {target}: {self.translator} [{self.get_role_display()}]"


# --------------------------------- Вложения к теме ---------------------------------

class ThreadAttachment(TimeStampedModel):
    class Kind(models.TextChoices):
        IMAGE = "image", "Картинка"
        FILE  = "file",  "Файл"
        LINK  = "link",  "Ссылка"

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="attachments")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.IMAGE)
    title = models.CharField(max_length=200, blank=True)

    file = models.FileField(upload_to="forum/attachments/%Y/%m/", null=True, blank=True)
    url  = models.URLField(blank=True)

    class Meta:
        verbose_name = "Вложение"
        verbose_name_plural = "Вложения"
        ordering = ("created_at",)

    def clean(self):
        if self.kind in (self.Kind.IMAGE, self.Kind.FILE) and not self.file:
            raise ValidationError("Для файла/картинки нужно приложить file.")
        if self.kind == self.Kind.LINK and not self.url:
            raise ValidationError("Для ссылки нужно указать url.")


# --------------------------------- Комментарии ---------------------------------

class CommentStatus(models.TextChoices):
    PUBLISHED = "published", "Опубликован"
    PENDING   = "pending",   "На модерации"
    HIDDEN    = "hidden",    "Скрыт"


class Comment(TimeStampedModel):
    thread = models.ForeignKey(
        "forum.Thread", on_delete=models.CASCADE, related_name="comments", verbose_name="Тема"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="forum_comments", verbose_name="Автор"
    )

    publish_as_team = models.ForeignKey(
        TranslatorPublisher,
        verbose_name="От имени команды",
        on_delete=models.PROTECT, null=True, blank=True, related_name="forum_comments"
    )

    content = models.TextField("Контент")

    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies", verbose_name="Ответ на"
    )

    status = models.CharField(max_length=16, choices=CommentStatus.choices,
                              default=CommentStatus.PUBLISHED, db_index=True)
    is_deleted = models.BooleanField("Удалён", default=False, db_index=True)
    is_pinned  = models.BooleanField("Закреплён", default=False, db_index=True)

    likes_count   = models.PositiveIntegerField(default=0)
    replies_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["thread", "status", "is_deleted", "created_at"]),
            models.Index(fields=["parent", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"forum c{self.pk} in t{self.thread_id} by u{self.author_id}"

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])

    def clean(self):
        # нельзя писать в закрытую тему
        if self.thread and getattr(self.thread, "is_locked", False):
            raise ValidationError("Тема закрыта.")

        # публикация от имени команды — только если автор член команды
        if self.publish_as_team:
            is_member = TranslatorMember.objects.filter(
                translator=self.publish_as_team, user=self.author, is_active=True
            ).exists()
            if not is_member:
                raise ValidationError("Автор должен быть активным участником выбранной команды.")

        # ответ только в рамках одной темы
        if self.parent_id and self.parent and self.parent.thread_id != self.thread_id:
            raise ValidationError("Нельзя отвечать на комментарий из другой темы.")

        # пустой контент
        if not self.content or not str(self.content).strip():
            raise ValidationError("Текст комментария пуст.")
