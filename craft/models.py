from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


def header_poster_upload_to(instance, filename: str) -> str:
    """
    Путь для файла шапки.
    Храним по material_id, чтобы было удобно находить.
    """
    now = timezone.now()
    return f"headers/{instance.material_id}/{now.year}/{now.month:02d}/{filename}"


class HeaderMaterialContent(models.Model):
    """
    Шапка для материала.
    Храним только:
      - ссылку на сам материал Kodik.Material
      - свой кастомный постер для шапки (крупный фон).
    Всё остальное (название, описание, рейтинг и т.п.) берём
    из kodik.Material / kodik.MaterialExtra.
    """

    material = models.OneToOneField(
        "kodik.Material",
        on_delete=models.CASCADE,
        related_name="header_content",
        verbose_name="Материал Kodik",
    )

    poster = models.ImageField(
        upload_to=header_poster_upload_to,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
        verbose_name="Постер для шапки",
        help_text="Крупное изображение для фоновой шапки.",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Показывать",
        help_text="Если выключено — не участвует в выборке для главной.",
    )

    position = models.PositiveIntegerField(
        default=0,
        verbose_name="Позиция",
        help_text="Для сортировки нескольких шапок.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Шапка материала"
        verbose_name_plural = "Шапки материалов"
        ordering = ("position", "-created_at")
        indexes = [
            models.Index(fields=["is_active", "position"]),
        ]

    def __str__(self) -> str:  # type: ignore[override]
        return f"Шапка: {self.material.title if self.material_id else '—'}"

    @property
    def poster_url(self) -> str:
        """
        Удобное свойство: абсолютный URL до файла шапки (MEDIA_URL обернёшь в serializer-е),
        а если файл по каким-то причинам пустой — можно fallback сделать.
        """
        if self.poster:
            return self.poster.url
        # запасной вариант: взять постер из extra, если нужно
        extra = getattr(self.material, "extra", None)
        if extra and extra.poster_url:
            return extra.poster_url
        return ""
