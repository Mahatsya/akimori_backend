# coding: utf-8
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError

# --- безопасная транслитерация
try:
    from unidecode import unidecode
except Exception:
    def unidecode(s: str) -> str:
        return s


def unique_slugify(
    instance,
    value: str,
    slug_field: str = "slug",
    extra_filters: dict | None = None,
    max_length: int = 220,
) -> str:
    raw = (value or "").strip()
    translit = unidecode(raw)
    base = slugify(translit, allow_unicode=False)
    if not base or base.isdigit():
        base = "item"
    base = base[:max_length].rstrip("-")
    slug = base or "item"

    Model = instance.__class__

    def exists(s: str) -> bool:
        q = Model.objects.all()
        if getattr(instance, "pk", None):
            q = q.exclude(pk=instance.pk)
        if extra_filters:
            q = q.filter(**extra_filters)
        return q.filter(**{slug_field: s}).exists()

    if not exists(slug):
        return slug

    i = 2
    while True:
        suffix = f"-{i}"
        allowed = max_length - len(suffix)
        candidate = (base[:allowed].rstrip("-")) + suffix
        if not exists(candidate):
            return candidate
        i += 1


# ---------- Справочники ----------

class Translation(models.Model):
    """Озвучка/перевод (Kodik: {id,title,type}) + инфостраница"""
    ext_id = models.PositiveIntegerField(unique=True, db_index=True)
    title = models.CharField(max_length=200)
    TYPE_CHOICES = (("voice", "voice"), ("subtitles", "subtitles"))
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    slug = models.SlugField(max_length=220, unique=True, blank=True)

    # Инфополя для страницы
    poster_url = models.URLField(max_length=1000, blank=True, default="")
    avatar_url = models.URLField(max_length=1000, blank=True, default="")
    banner_url = models.URLField(max_length=1000, blank=True, default="")
    description = models.TextField(blank=True, default="")
    website_url = models.URLField(max_length=1000, blank=True, default="")
    aliases = models.JSONField(default=list, blank=True)
    country = models.ForeignKey(
        "kodik.Country", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="translations"
    )
    founded_year = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["title"]
        indexes = [models.Index(fields=["ext_id"])]

    def __str__(self) -> str:
        return f"{self.title} ({self.type})"

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            self.slug = unique_slugify(self, self.title)
        return super().save(*args, **kwargs)


class Country(models.Model):
    """Страна (ISO-код + имя)."""
    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = unique_slugify(self, self.name)
        return super().save(*args, **kwargs)


class Genre(models.Model):
    """Жанр с источником: kp|shikimori|mdl|all."""
    SOURCE_CHOICES = (
        ("kp", "KinoPoisk"),
        ("shikimori", "Shikimori"),
        ("mdl", "MyDramaList"),
        ("all", "All sources"),
    )
    name = models.CharField(max_length=120)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="all")
    slug = models.SlugField(max_length=160, blank=True)

    class Meta:
        unique_together = (("slug", "source"),)
        ordering = ["name"]
        indexes = [
            models.Index(fields=["source", "slug"]),
            models.Index(fields=["source", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.source}]"

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = unique_slugify(self, self.name, extra_filters={"source": self.source})
        return super().save(*args, **kwargs)


class Studio(models.Model):
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = unique_slugify(self, self.name)
        return super().save(*args, **kwargs)


class LicenseOwner(models.Model):
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = unique_slugify(self, self.name)
        return super().save(*args, **kwargs)


class MDLTag(models.Model):
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = unique_slugify(self, self.name)
        return super().save(*args, **kwargs)


class Person(models.Model):
    """Персоны + инфостраница."""
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)

    # Инфополя
    avatar_url = models.URLField(max_length=1000, blank=True, default="")
    photo_url = models.URLField(max_length=1000, blank=True, default="")
    banner_url = models.URLField(max_length=1000, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    death_date = models.DateField(null=True, blank=True)
    country = models.ForeignKey(
        "kodik.Country", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="people"
    )

    # Внешние ID
    imdb_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    shikimori_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    kinopoisk_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    socials = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = unique_slugify(self, self.name)
        return super().save(*args, **kwargs)


# ---------- Основная сущность ----------

SERIAL_TYPES = {
    "cartoon-serial", "documentary-serial", "russian-serial",
    "foreign-serial", "anime-serial", "multi-part-film"
}

class Material(models.Model):
    """Материал Kodik (фильм/сериал/аниме). pk = kodik_id."""
    kodik_id = models.CharField(max_length=64, primary_key=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True, db_index=True)

    TYPE_MAX = 64
    type = models.CharField(max_length=TYPE_MAX, db_index=True)
    link = models.URLField(max_length=1000, blank=True, default="")
    title = models.CharField(max_length=300)
    title_orig = models.CharField(max_length=300, blank=True, default="")
    other_title = models.CharField(max_length=300, blank=True, default="")

    translation = models.ForeignKey(
        Translation, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="materials_legacy"
    )

    year = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    quality = models.CharField(max_length=120, blank=True, default="")
    camrip = models.BooleanField(null=True, blank=True)
    lgbt = models.BooleanField(null=True, blank=True)

    kinopoisk_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    imdb_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    mdl_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    worldart_link = models.URLField(max_length=1000, blank=True, default="")
    shikimori_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    last_season = models.PositiveIntegerField(null=True, blank=True)
    last_episode = models.PositiveIntegerField(null=True, blank=True)
    episodes_count = models.PositiveIntegerField(null=True, blank=True)

    blocked_countries = models.ManyToManyField(
        Country, blank=True, related_name="blocked_materials"
    )
    production_countries = models.ManyToManyField(
        Country, blank=True, related_name="materials"
    )

    genres = models.ManyToManyField(Genre, blank=True, related_name="materials")
    studios = models.ManyToManyField(Studio, blank=True, related_name="materials")
    license_owners = models.ManyToManyField(LicenseOwner, blank=True, related_name="materials")
    mdl_tags = models.ManyToManyField(MDLTag, blank=True, related_name="materials")

    screenshots = models.JSONField(default=list, blank=True)
    poster_url = models.URLField(max_length=1000, blank=True, default="")

    blocked_seasons = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["type", "updated_at"]),
            models.Index(fields=["year"]),
            models.Index(fields=["kinopoisk_id"]),
            models.Index(fields=["imdb_id"]),
            models.Index(fields=["shikimori_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.kodik_id})"

    @property
    def is_serial(self) -> bool:
        return self.type in SERIAL_TYPES or self.last_season is not None

    @property
    def is_movie(self) -> bool:
        return not self.is_serial

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            self.slug = unique_slugify(self, self.title)
        if not self.created_at:
            self.created_at = timezone.now()
        if not self.updated_at:
            self.updated_at = timezone.now()
        return super().save(*args, **kwargs)


# ---------- Расширенные данные ----------

class MaterialExtra(models.Model):
    material = models.OneToOneField(Material, on_delete=models.CASCADE, related_name="extra")

    # Названия
    title = models.CharField(max_length=300, blank=True, default="")
    anime_title = models.CharField(max_length=300, blank=True, default="")
    title_en = models.CharField(max_length=300, blank=True, default="")

    other_titles = models.JSONField(default=list, blank=True)
    other_titles_en = models.JSONField(default=list, blank=True)
    other_titles_jp = models.JSONField(default=list, blank=True)

    # Лицензии/типы
    anime_license_name = models.CharField(max_length=200, blank=True, default="")
    anime_kind = models.CharField(max_length=40, blank=True, default="")

    # Статусы
    all_status = models.CharField(max_length=40, blank=True, default="")
    anime_status = models.CharField(max_length=40, blank=True, default="")
    drama_status = models.CharField(max_length=40, blank=True, default="")

    # Описания/слоган
    tagline = models.CharField(max_length=400, blank=True, default="")
    description = models.TextField(blank=True, default="")
    anime_description = models.TextField(blank=True, default="")

    # Постеры
    poster_url = models.URLField(max_length=1000, blank=True, default="")
    anime_poster_url = models.URLField(max_length=1000, blank=True, default="")
    drama_poster_url = models.URLField(max_length=1000, blank=True, default="")

    # Продолжительность
    duration = models.PositiveIntegerField(null=True, blank=True)

    # Рейтинги и голоса
    kinopoisk_rating = models.FloatField(null=True, blank=True)
    kinopoisk_votes = models.PositiveIntegerField(null=True, blank=True)
    imdb_rating = models.FloatField(null=True, blank=True)
    imdb_votes = models.PositiveIntegerField(null=True, blank=True)
    shikimori_rating = models.FloatField(null=True, blank=True)
    shikimori_votes = models.PositiveIntegerField(null=True, blank=True)
    mydramalist_rating = models.FloatField(null=True, blank=True)
    mydramalist_votes = models.PositiveIntegerField(null=True, blank=True)

    # Премьеры/эфиры
    premiere_ru = models.DateField(null=True, blank=True)
    premiere_world = models.DateField(null=True, blank=True)
    aired_at = models.DateField(null=True, blank=True)
    released_at = models.DateField(null=True, blank=True)
    next_episode_at = models.DateTimeField(null=True, blank=True)

    # Возраст/MPAA/эпизоды
    rating_mpaa = models.CharField(max_length=16, blank=True, default="")
    minimal_age = models.PositiveSmallIntegerField(null=True, blank=True)
    episodes_total = models.PositiveIntegerField(null=True, blank=True)
    episodes_aired = models.PositiveIntegerField(null=True, blank=True)

    # --- Агрегаты Akimori
    comments_count = models.PositiveIntegerField(default=0, db_index=True)
    aki_votes = models.PositiveIntegerField(default=0, db_index=True)
    aki_rating = models.DecimalField(
        max_digits=3, decimal_places=1,
        null=True, blank=True, db_index=True
    )

    # --- Кол-во просмотров
    views_count = models.PositiveIntegerField(default=0, db_index=True)

    def __str__(self) -> str:
        return f"Extra for {self.material_id}"

    class Meta:
        indexes = [
            models.Index(fields=["comments_count"]),
            models.Index(fields=["aki_votes"]),
            models.Index(fields=["aki_rating"]),
            models.Index(fields=["views_count"]),
        ]


# ---------- Версии (переводы) ----------

class MaterialVersion(models.Model):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="versions")
    translation = models.ForeignKey(Translation, on_delete=models.CASCADE, related_name="versions")
    movie_link = models.URLField(max_length=1000, blank=True, default="")

    class Meta:
        unique_together = (("material", "translation"),)
        indexes = [
            models.Index(fields=["material", "translation"]),
            models.Index(fields=["material"]),
        ]
        ordering = ["material_id"]

    def __str__(self):
        return f"{self.material_id} [{self.translation.title}]"


# ---------- Кредиты ----------

class Credit(models.Model):
    ROLE_CHOICES = (
        ("actor", "actor"),
        ("director", "director"),
        ("producer", "producer"),
        ("writer", "writer"),
        ("composer", "composer"),
        ("editor", "editor"),
        ("designer", "designer"),
        ("operator", "operator"),
    )
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="credits")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="credits")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, db_index=True)

    character_name = models.CharField(max_length=160, blank=True, default="")
    order = models.PositiveIntegerField(default=0, db_index=True)
    note = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        unique_together = (("material", "person", "role"),)
        indexes = [
            models.Index(fields=["material", "role", "order"]),
            models.Index(fields=["person", "role"]),
        ]
        ordering = ["material", "role", "order"]

    def __str__(self) -> str:
        base = f"{self.material_id} - {self.role}: {self.person.name}"
        if self.character_name:
            base += f" as {self.character_name}"
        return base


# ---------- Сезоны/Серии ----------

class Season(models.Model):
    version = models.ForeignKey(MaterialVersion, on_delete=models.CASCADE, related_name="seasons")
    number = models.PositiveIntegerField()
    link = models.URLField(max_length=1000, blank=True, default="")

    class Meta:
        unique_together = (("version", "number"),)
        ordering = ["version", "number"]
        indexes = [models.Index(fields=["version", "number"])]

    def __str__(self) -> str:
        return f"{self.version.material_id} [{self.version.translation.title}] S{self.number}"


class Episode(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="episodes")
    number = models.PositiveIntegerField()
    link = models.URLField(max_length=1000)
    title = models.CharField(max_length=300, blank=True, default="")
    screenshots = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = (("season", "number"),)
        ordering = ["season", "number"]
        indexes = [models.Index(fields=["season", "number"])]

    def __str__(self) -> str:
        return f"{self.season} E{self.number}"


# ---------- Рейтинг Akimori ----------

class AkiUserRating(models.Model):
    material = models.ForeignKey("kodik.Material", on_delete=models.CASCADE, related_name="aki_user_ratings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="aki_ratings")
    score = models.DecimalField(max_digits=3, decimal_places=1)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("material", "user"),)
        indexes = [
            models.Index(fields=["material", "user"]),
            models.Index(fields=["material", "score"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(score__gte=0) & Q(score__lte=10),
                                   name="aki_score_range_0_10"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.material_id} • {self.user_id} = {self.score}"


# ---------- Комментарии и лайки ----------

class MaterialCommentStatus(models.TextChoices):
    PUBLISHED = "published", "published"
    PENDING   = "pending",   "pending"
    HIDDEN    = "hidden",    "hidden"


class MaterialComment(models.Model):
    material = models.ForeignKey(
        "kodik.Material", on_delete=models.CASCADE, related_name="comments"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="material_comments"
    )

    content = models.TextField()

    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )

    status = models.CharField(
        max_length=16, choices=MaterialCommentStatus.choices,
        default=MaterialCommentStatus.PUBLISHED, db_index=True
    )

    is_deleted = models.BooleanField(default=False, db_index=True)
    is_pinned  = models.BooleanField(default=False, db_index=True)

    likes_count   = models.PositiveIntegerField(default=0)
    replies_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["material", "status", "is_deleted", "created_at"]),
            models.Index(fields=["parent", "created_at"]),
        ]
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"kodik c{self.pk} in m{self.material_id} by u{self.user_id}"

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])

    def clean(self):
        if self.parent_id and self.parent and self.parent.material_id != self.material_id:
            raise ValidationError("Parent belongs to another material.")
        if not self.content or not str(self.content).strip():
            raise ValidationError("Body is empty.")


class MaterialCommentLike(models.Model):
    comment = models.ForeignKey("kodik.MaterialComment", on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comment_likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("comment", "user"),)
        indexes = [
            models.Index(fields=["comment", "user"]),
            models.Index(fields=["comment"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"like c{self.comment_id} by u{self.user_id}"
