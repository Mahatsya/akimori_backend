from django.contrib.auth.models import AbstractUser
from django.db import models, transaction, IntegrityError
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.crypto import get_random_string
from datetime import timedelta
from PIL import Image

from .leveling import (
    MAX_LEVEL,
    xp_for_level,
    total_xp_for_level,
    level_for_xp,
    progress_to_next,
)

# ==========================================================
# --- Пользователь, роли, профиль ---
# ==========================================================

class Roles(models.TextChoices):
    USER = "user", "Пользователь"
    MODERATOR = "moderator", "Модератор"
    ADMIN = "admin", "Администратор"


class User(AbstractUser):
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Roles.choices, default=Roles.USER)
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    xp = models.PositiveBigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ====== Level System ======
    @property
    def level(self) -> int:
        return level_for_xp(int(self.xp))

    @property
    def max_level(self) -> int:
        return MAX_LEVEL

    @property
    def next_level_xp(self) -> int:
        lvl = self.level
        if lvl >= MAX_LEVEL:
            return total_xp_for_level(MAX_LEVEL)
        return total_xp_for_level(lvl + 1)

    @property
    def need_for_next(self) -> int:
        lvl = self.level
        if lvl >= MAX_LEVEL:
            return 0
        base = total_xp_for_level(lvl)
        need = xp_for_level(lvl + 1)
        done = max(0, int(self.xp) - base)
        return max(0, need - done)

    @property
    def progress(self) -> float:
        return progress_to_next(int(self.xp))

    def add_xp(self, amount: int) -> None:
        if amount <= 0:
            return
        self.xp = min(self.xp + amount, total_xp_for_level(MAX_LEVEL))
        self.save(update_fields=["xp", "updated_at"])

    def __str__(self):
        return self.display_name or self.user.username


# ==========================================================
# --- Список аниме пользователя ---
# ==========================================================

class AnimeStatus(models.TextChoices):
    WILL_WATCH = "will_watch", "Буду смотреть"
    WATCHING = "watching", "Смотрю"
    COMPLETED = "completed", "Просмотрел"
    PLANNED = "planned", "Запланировано"
    ON_HOLD = "on_hold", "Отложено"
    REWATCHING = "rewatching", "Пересматриваю"
    DROPPED = "dropped", "Брошено"


class UserAnimeList(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="anime_list")
    material = models.ForeignKey("kodik.Material", on_delete=models.CASCADE, related_name="user_entries")
    status = models.CharField(max_length=20, choices=AnimeStatus.choices, default=AnimeStatus.PLANNED)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "material")
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["material"]),
        ]

    def __str__(self):
        title = getattr(self.material, "title", "") or getattr(self.material, "slug", "")
        return f"{self.user.username} — {title} [{self.get_status_display()}]"


# ==========================================================
# --- Аватары ---
# ==========================================================

def avatar_upload_to(instance, filename):
    now = timezone.now()
    return f"avatars/{instance.user_id}/{now.year}/{now.month:02d}/{filename}"


class AvatarMedia(models.Model):
    """История загруженных пользователем аватаров (только статичные картинки)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="avatar_media")
    file = models.ImageField(
        upload_to=avatar_upload_to,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    is_animated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "created_at"])]

    def clean(self):
        try:
            img = Image.open(self.file)
            animated = getattr(img, "is_animated", False)
            if not animated and hasattr(img, "n_frames"):
                animated = img.n_frames > 1
            if animated:
                self.is_animated = True
                raise ValidationError("Анимированные аватары загружать нельзя. Используйте покупные.")
        except Exception:
            pass

    @property
    def url(self):
        return self.file.url


# ==========================================================
# --- EmailVerification / OneTimeCode ---
# ==========================================================

class EmailVerification(models.Model):
    """Код подтверждения почты (регистрация / смена email)"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_verifications")
    code = models.CharField(max_length=6, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"])]

    @staticmethod
    def _gen_code() -> str:
        return get_random_string(6, "0123456789")

    @classmethod
    def create_for_user(cls, user, ttl_minutes: int = 15, max_attempts: int = 5):
        for _ in range(max_attempts):
            code = cls._gen_code()
            try:
                with transaction.atomic():
                    return cls.objects.create(
                        user=user,
                        code=code,
                        expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
                    )
            except IntegrityError:
                continue
        raise RuntimeError("Не удалось сгенерировать уникальный код подтверждения")

    def is_valid(self) -> bool:
        return (not self.is_used) and timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.user.username} — {self.code}"


class OneTimeCode(models.Model):
    """Коды одноразовых действий (смена почты, удаление аккаунта и т.п.)"""
    ACTION_CHANGE_EMAIL = "change_email"
    ACTION_DELETE_ACCOUNT = "delete_account"
    ACTIONS = [
        (ACTION_CHANGE_EMAIL, "Смена почты"),
        (ACTION_DELETE_ACCOUNT, "Удаление аккаунта"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="one_time_codes")
    action = models.CharField(max_length=64, choices=ACTIONS, db_index=True)
    value = models.CharField(max_length=255, help_text="Целевое значение (новая почта или текущая почта)")
    code = models.CharField(max_length=10, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ("user", "action", "code")
        indexes = [models.Index(fields=["user", "action", "created_at"])]
        verbose_name = "Одноразовый код"
        verbose_name_plural = "Одноразовые коды"

    def __str__(self):
        return f"{self.action} for {self.user_id}: {self.code}"

    def is_valid(self, ttl_minutes: int = 10) -> bool:
        return timezone.now() - self.created_at < timedelta(minutes=ttl_minutes)
