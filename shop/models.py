from django.conf import settings
from django.db import models
from django.utils import timezone
from customitem.models import Item
from economy.models import Transaction  # линк на проводку в экономике


class Offer(models.Model):
    """
    Торговое предложение для предмета (витрина).
    Можно переопределять цену, ограничивать период продаж и включать/выключать оффер.
    """
    item = models.OneToOneField(
        Item,
        verbose_name="Предмет",
        on_delete=models.CASCADE,
        related_name="offer",
    )
    is_active = models.BooleanField("Активен", default=True)
    price_override_aki = models.PositiveIntegerField(
        "Цена (override, AKI)",
        blank=True, null=True,
        help_text="Если задано — заменяет Item.price_aki.",
    )
    starts_at = models.DateTimeField("Начало продаж", blank=True, null=True)
    ends_at = models.DateTimeField("Окончание продаж", blank=True, null=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Оффер"
        verbose_name_plural = "Офферы"
        ordering = ("-created_at",)

    def __str__(self):
        return f"Оффер: {self.item.title}"

    @property
    def current_price(self) -> int:
        return self.price_override_aki if self.price_override_aki is not None else self.item.price_aki

    def is_selling_now(self) -> bool:
        if not self.is_active:
            return False
        if not self.item.can_sell_now:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return self.current_price > 0


class PurchaseStatus(models.TextChoices):
    SUCCESS = "success", "Успешно"
    FAILED  = "failed",  "Ошибка"


class Purchase(models.Model):
    """
    Покупка предмета пользователем.
    Сохраняем цену в AKI и ссылку на транзакцию из экономики.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="purchases",
    )
    item = models.ForeignKey(
        Item,
        verbose_name="Предмет",
        on_delete=models.PROTECT,
        related_name="purchases",
    )
    price_aki = models.PositiveIntegerField("Цена (AKI)")
    transaction = models.ForeignKey(
        Transaction,
        verbose_name="Транзакция",
        on_delete=models.PROTECT,
        related_name="item_purchases",
    )

    status = models.CharField("Статус", max_length=12, choices=PurchaseStatus.choices, default=PurchaseStatus.SUCCESS)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Покупка"
        verbose_name_plural = "Покупки"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user} купил {self.item} за {self.price_aki} AKI"
