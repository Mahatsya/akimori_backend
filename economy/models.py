# models.py
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q
from django.utils import timezone


class Currency(models.TextChoices):
    RUB = "RUB", "Рубли"
    AKI = "AKI", "AkiCoin"


# масштаб для хранения в минорных единицах (integer)
SCALE: dict[str, int] = {
    Currency.RUB: 100,  # копейки
    Currency.AKI: 1,    # целые коины
}


def normalize_amount(currency: str | Currency, amount: int | str | float | Decimal) -> int:
    """
    Приводим внешнее число к integer в минорных единицах.

    ВАЖНО: сейчас считаем, что приходят уже *минорные* единицы:
      - RUB: копейки (19900 -> 199.00 ₽)
      - AKI: целые коинты

    Если где-нибудь захочешь принимать рубли в формате "199.50" — тогда можно
    доработать тут через Decimal и SCALE[currency].
    """
    if amount is None:
        raise ValidationError("Amount is required")

    try:
        # Не даём использовать NaN/inf и прочий мусор
        if isinstance(amount, Decimal):
            ivalue = int(amount)
        else:
            ivalue = int(str(amount).strip())
    except (ValueError, TypeError, InvalidOperation) as e:
        raise ValidationError(f"Invalid amount: {amount}") from e

    if ivalue <= 0:
        raise ValidationError("Amount must be > 0")

    return ivalue


class Wallet(models.Model):
    """
    Один кошелёк на валюту на пользователя.
    Баланс хранится в минорных единицах (копейки/коины).
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallets",
    )
    currency = models.CharField(max_length=3, choices=Currency.choices)
    balance = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("user", "currency"),)
        indexes = [
            models.Index(fields=["user", "currency"]),
        ]
        constraints = [
            CheckConstraint(check=Q(balance__gte=0), name="wallet_balance_non_negative"),
        ]
        verbose_name = "Кошелёк"
        verbose_name_plural = "Кошельки"

    def __str__(self) -> str:
        return f"{self.user} [{self.currency}] — {self.balance}"

    @property
    def scale(self) -> int:
        return SCALE[self.currency]

    @property
    def balance_display(self) -> str:
        return str(self.balance)

    def can_debit(self, amount: int) -> bool:
        return amount > 0 and self.balance >= amount


class TxType(models.TextChoices):
    DEPOSIT      = "deposit", "Пополнение"
    WITHDRAW     = "withdraw", "Списание"
    TRANSFER_OUT = "transfer_out", "Перевод исходящий"
    TRANSFER_IN  = "transfer_in", "Перевод входящий"
    ADJUST       = "adjust", "Корректировка (админ)"


class Transaction(models.Model):
    """
    Журнал операций по кошельку (одна строка = одно движение по одному кошельку).
    Для перевода между кошельками будет ПАРА строк: OUT + IN, связанные related_tx.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    tx_type = models.CharField(max_length=20, choices=TxType.choices)
    amount = models.BigIntegerField()  # >0 в минорных единицах
    description = models.CharField(max_length=255, blank=True, default="")
    related_tx = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paired",
    )
    idempotency_key = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        help_text="Ключ идемпотентности, чтобы не задвоить операции",
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["idempotency_key"]),
        ]
        ordering = ("-created_at",)
        verbose_name = "Транзакция"
        verbose_name_plural = "Транзакции"

    def __str__(self) -> str:
        sign = "+" if self.tx_type in (TxType.DEPOSIT, TxType.TRANSFER_IN, TxType.ADJUST) else "-"
        return f"{self.wallet} {sign}{self.amount} ({self.tx_type})"


# Служебные исключения для сервиса
class InsufficientFunds(Exception):
    pass


@dataclass(frozen=True)
class TransferResult:
    out_tx: Transaction | None
    in_tx: Transaction | None
    amount: int
