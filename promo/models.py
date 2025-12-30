from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from economy.models import Currency
from economy.services import ensure_user_wallets, deposit
from customitem.models import Item, Inventory, InventorySource


class PromoCode(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)

    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()

    max_total_uses = models.PositiveIntegerField(default=1)
    max_uses_per_user = models.PositiveIntegerField(default=1)

    # считаем ТОЛЬКО APPLIED
    uses_count = models.PositiveIntegerField(default=0)

    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        return super().save(*args, **kwargs)

    def is_in_window(self, now=None) -> bool:
        now = now or timezone.now()
        return self.starts_at <= now <= self.ends_at

    def can_user_redeem(self, user, now=None) -> tuple[bool, str]:
        return self.can_user_redeem_applied(user, now=now)

    def can_user_redeem_applied(self, user, now=None) -> tuple[bool, str]:
        """
        Проверка возможности использовать промокод (учитываем только APPLIED).
        PENDING/EXPIRED/CANCELLED не должны “съедать” лимиты.
        """
        now = now or timezone.now()

        if not self.is_active:
            return False, "promo_inactive"
        if not self.is_in_window(now=now):
            return False, "promo_expired_or_not_started"
        if self.uses_count >= self.max_total_uses:
            return False, "promo_limit_reached"

        already_applied = PromoRedemption.objects.filter(
            user=user, promo=self, status="applied"
        ).count()
        if already_applied >= self.max_uses_per_user:
            return False, "already_redeemed"

        return True, "ok"

    @transaction.atomic
    def redeem(
        self,
        user,
        *,
        context: str = "manual",
        topup_amount_minor: int | None = None,
        ip: str = "",
        ua: str = "",
    ) -> "PromoRedemption":
        """
        MANUAL redeem: применяет сразу (APPLIED) и увеличивает uses_count.
        Для topup используй reserve/confirm flow.
        """
        locked = PromoCode.objects.select_for_update().get(pk=self.pk)

        ok, reason = locked.can_user_redeem_applied(user)
        if not ok:
            raise ValidationError({"code": reason})

        now = timezone.now()

        redemption = PromoRedemption.objects.create(
            promo=locked,
            user=user,
            status="applied",
            context=context,
            topup_amount_minor=topup_amount_minor,
            redeemed_at=now,
            applied_at=now,
            ip=ip,
            user_agent=ua,
        )

        locked.apply_effect(user=user, redemption=redemption, topup_amount_minor=topup_amount_minor)
        PromoCode.objects.filter(pk=locked.pk).update(uses_count=F("uses_count") + 1)
        return redemption

    def apply_effect(self, *, user, redemption: "PromoRedemption", topup_amount_minor: int | None):
        """
        Применение эффекта (выдача):
        - manual: сразу
        - topup: после confirm оплаты
        """

        # 1) бонус на баланс
        if hasattr(self, "balance_bonus"):
            eff: PromoBalanceBonus = self.balance_bonus
            ensure_user_wallets(user)
            wallet = user.wallets.get(currency=eff.currency)

            bonus_minor = eff.calc_bonus_minor(topup_amount_minor=topup_amount_minor)
            if bonus_minor <= 0:
                raise ValidationError({"code": "bonus_is_zero"})

            deposit(
                wallet,
                bonus_minor,
                description=f"Promo {self.code}",
                idempotency_key=f"promo:{redemption.id}",
            )

            redemption.payload = {
                "type": "balance_bonus",
                "currency": eff.currency,
                "amount_minor": bonus_minor,
            }
            redemption.save(update_fields=["payload"])
            return

        # 2) выдача предмета
        if hasattr(self, "item_grant"):
            eff: PromoItemGrant = self.item_grant

            if Inventory.objects.filter(user=user, item=eff.item).exists():
                raise ValidationError({"code": "item_already_owned"})

            Inventory.objects.create(user=user, item=eff.item, source=InventorySource.GIFT)
            redemption.payload = {"type": "item_grant", "item_id": eff.item_id}
            redemption.save(update_fields=["payload"])
            return

        # 3) скидка на пополнение — расчёт до оплаты
        if hasattr(self, "topup_discount"):
            raise ValidationError({"code": "topup_discount_requires_quote"})

        raise ValidationError({"code": "promo_has_no_effect"})


class PromoRedemption(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPLIED = "applied", "Applied"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    promo = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="promo_redemptions",
    )

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    context = models.CharField(max_length=16, default="manual")
    topup_amount_minor = models.BigIntegerField(null=True, blank=True)

    payment_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    topup_id = models.CharField(max_length=64, blank=True, default="", db_index=True)

    idempotency_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    reserved_until = models.DateTimeField(null=True, blank=True)

    redeemed_at = models.DateTimeField(default=timezone.now)
    applied_at = models.DateTimeField(null=True, blank=True)

    ip = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.CharField(max_length=255, blank=True, default="")

    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["promo", "user", "status", "redeemed_at"]),
            models.Index(fields=["payment_id"]),
            models.Index(fields=["topup_id"]),
            models.Index(fields=["idempotency_key"]),
        ]
        constraints = [
            # ✅ Уникальность promo+user только для APPLIED
            models.UniqueConstraint(
                fields=["promo", "user"],
                condition=Q(status="applied"),
                name="uniq_promo_user_applied",
            ),
            # ✅ Идемпотентность по ключу (если ключ не пуст)
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_promo_idempotency_key",
            ),
        ]

    def is_reservation_valid(self) -> bool:
        if self.status != self.Status.PENDING:
            return False
        if not self.reserved_until:
            return True
        return timezone.now() < self.reserved_until


class PromoTopupDiscount(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percent"
        FIXED = "fixed", "Fixed"

    promo = models.OneToOneField(PromoCode, on_delete=models.CASCADE, related_name="topup_discount")
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.RUB)

    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)

    min_topup_minor = models.BigIntegerField(default=0)
    max_discount_minor = models.BigIntegerField(null=True, blank=True)

    def quote(self, topup_amount_minor: int) -> dict:
        if topup_amount_minor < self.min_topup_minor:
            return {"ok": False, "reason": "topup_too_small"}

        if self.discount_type == self.DiscountType.PERCENT:
            disc = int(Decimal(topup_amount_minor) * (self.discount_value / Decimal("100")))
        else:
            disc = int(self.discount_value)

        if self.max_discount_minor is not None:
            disc = min(disc, int(self.max_discount_minor))

        disc = max(0, min(disc, topup_amount_minor))
        payable = topup_amount_minor - disc

        return {"ok": True, "discount_minor": disc, "payable_minor": payable}


class PromoBalanceBonus(models.Model):
    class BonusType(models.TextChoices):
        FIXED = "fixed", "Fixed"
        PERCENT = "percent", "Percent of topup"

    promo = models.OneToOneField(PromoCode, on_delete=models.CASCADE, related_name="balance_bonus")
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.AKI)
    bonus_type = models.CharField(max_length=10, choices=BonusType.choices, default=BonusType.FIXED)

    bonus_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_topup_minor = models.BigIntegerField(null=True, blank=True)

    def calc_bonus_minor(self, *, topup_amount_minor: int | None) -> int:
        if self.bonus_type == self.BonusType.FIXED:
            return int(self.bonus_value)

        if topup_amount_minor is None:
            raise ValidationError({"code": "topup_amount_required"})
        if self.min_topup_minor is not None and topup_amount_minor < self.min_topup_minor:
            raise ValidationError({"code": "topup_too_small"})

        return int(Decimal(topup_amount_minor) * (self.bonus_value / Decimal("100")))


class PromoItemGrant(models.Model):
    promo = models.OneToOneField(PromoCode, on_delete=models.CASCADE, related_name="item_grant")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
