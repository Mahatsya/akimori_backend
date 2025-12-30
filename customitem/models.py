from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils import timezone


class ItemType(models.TextChoices):
    AVATAR_ANIM     = "avatar",   "Аватар"
    HEADER_ANIM     = "header",   "Шапка"
    THEME           = "theme",         "Тема профиля/ридера"
    AVATAR_FRAME    = "avatar_frame",  "Рамка для аватара"


class Rarity(models.TextChoices):
    COMMON   = "common",   "Обычный"
    RARE     = "rare",     "Редкий"
    EPIC     = "epic",     "Эпический"
    LEGEND   = "legend",   "Легендарный"


class Item(models.Model):
    """
    Каталожный предмет. Цена в AKI на стороне каталога для простоты MVP.
    Позже можно вынести прайсы в отдельную таблицу/офферы (в shop).
    """
    type = models.CharField(
        "Тип предмета",
        max_length=32,
        choices=ItemType.choices,
        db_index=True,
    )
    slug = models.SlugField(
        "Слаг",
        max_length=160,
        unique=True,
        db_index=True,
        help_text="URL-идентификатор. Генерируется из названия.",
    )
    title = models.CharField("Название", max_length=160)
    description = models.TextField("Описание", blank=True)

    # Медиа: либо file, либо url (MVP — одно из двух)
    file = models.FileField(
        "Файл",
        upload_to="items/files/",
        blank=True, null=True,
        help_text="Загрузите файл предмета (например, .webp/.webm) либо укажите внешний URL ниже.",
    )
    file_url = models.URLField(
        "Внешний URL файла",
        blank=True, null=True,
        help_text="Если файл хранится вне нашего медиа.",
    )
    preview = models.ImageField(
        "Превью (картинка)",
        upload_to="items/previews/",
        blank=True, null=True,
        help_text="Статичное превью для списка/админки.",
    )

    is_animated = models.BooleanField("Анимированный", default=False)
    mime = models.CharField("MIME-тип", max_length=80, blank=True, help_text="Напр.: image/webp, video/webm")
    width = models.PositiveIntegerField("Ширина", blank=True, null=True)
    height = models.PositiveIntegerField("Высота", blank=True, null=True)
    duration_ms = models.PositiveIntegerField("Длительность (мс)", blank=True, null=True)

    rarity = models.CharField("Редкость", max_length=16, choices=Rarity.choices, default=Rarity.COMMON)
    attributes = models.JSONField(
        "Атрибуты",
        default=dict,
        blank=True,
        help_text="Произвольные настройки/цвета/параметры темы (JSON).",
    )

    # Ценообразование (AKI)
    price_aki = models.PositiveIntegerField(
        "Цена (AKI)",
        default=0,
        help_text="Цена в AkiCoin (целые). 0 — нельзя купить (например, трофей).",
    )

    # Лимиты
    limited_total = models.PositiveIntegerField("Лимит выпущенных", blank=True, null=True)
    limited_sold  = models.PositiveIntegerField("Продано", default=0)

    is_active = models.BooleanField("Активен", default=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["type", "is_active"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return f"{self.title} [{self.get_type_display()}]"

    def clean(self):
        if not self.file and not self.file_url:
            raise ValidationError("Нужно указать файл или внешний URL (одно из двух).")
        if self.type == ItemType.HEADER_ANIM and not self.is_animated:
            # шапки по ТЗ всегда анимированные
            self.is_animated = True

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:160]
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def can_sell_now(self) -> bool:
        if not self.is_active:
            return False
        if self.price_aki <= 0:
            return False
        if self.limited_total is not None and self.limited_sold >= self.limited_total:
            return False
        return True


# === добавили: enum для источника в инвентаре ===
class InventorySource(models.TextChoices):
    PURCHASE   = "purchase", "Покупка"
    GIFT       = "gift",     "Подарок/выдача"
    ACHIEVEMNT = "achieve",  "Ачивка"   # сохранено написание для совместимости со старыми миграциями


class Inventory(models.Model):
    """
    Владелец предмета. Один предмет — одна запись.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="inventory",
    )
    item = models.ForeignKey(
        Item,
        verbose_name="Предмет",
        on_delete=models.CASCADE,
        related_name="owners",
    )
    source = models.CharField(
        "Источник",
        max_length=16,
        choices=InventorySource.choices,
        default=InventorySource.PURCHASE,
    )
    note = models.CharField("Заметка", max_length=180, blank=True)
    acquired_at = models.DateTimeField("Получено", default=timezone.now)

    class Meta:
        verbose_name = "Инвентарь (запись)"
        verbose_name_plural = "Инвентарь"
        unique_together = ("user", "item")
        indexes = [
            models.Index(fields=["user", "acquired_at"]),
        ]

    def __str__(self):
        return f"{self.user} владеет {self.item}"


class AppliedCustomization(models.Model):
    """
    Надетые (активные) предметы. Не храним файлы, только ссылки на Item.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="applied_custom",
    )
    avatar_item = models.ForeignKey(
        Item, verbose_name="Аватар",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="applied_as_avatar"
    )
    header_item = models.ForeignKey(
        Item, verbose_name="Шапка",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="applied_as_header"
    )
    theme_item  = models.ForeignKey(
        Item, verbose_name="Тема",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="applied_as_theme"
    )
    frame_item  = models.ForeignKey(
        Item, verbose_name="Рамка аватара",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="applied_as_frame"
    )

    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Активные предметы пользователя"
        verbose_name_plural = "Активные предметы пользователей"

    def __str__(self):
        return f"Надето у {self.user}"

    def _validate_ownership(self, user, item: "Item | None", allowed_types: tuple[str, ...], slot_name: str):
        if item is None:
            return
        if item.type not in allowed_types:
            raise ValidationError(f"Нельзя поставить «{item.get_type_display()}» в слот «{slot_name}».")
        if not Inventory.objects.filter(user=user, item=item).exists():
            raise ValidationError("У пользователя нет такого предмета в инвентаре.")

    def clean(self):
        self._validate_ownership(self.user, self.avatar_item, (ItemType.AVATAR_ANIM,), "avatar")
        self._validate_ownership(self.user, self.header_item, (ItemType.HEADER_ANIM,), "header")
        self._validate_ownership(self.user, self.theme_item,  (ItemType.THEME,), "theme")
        self._validate_ownership(self.user, self.frame_item,  (ItemType.AVATAR_FRAME,), "frame")
