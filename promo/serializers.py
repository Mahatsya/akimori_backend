from __future__ import annotations

from rest_framework import serializers

from .models import PromoCode


class PromoCodeInSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)


class PromoRedeemInSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    topup_amount_minor = serializers.IntegerField(required=False, allow_null=True)


class PromoTopupQuoteInSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    amount_minor = serializers.IntegerField(min_value=1)


class PromoTopupApplyInSerializer(serializers.Serializer):
    """
    APPLY = RESERVE. Требует payment_id.
    """
    code = serializers.CharField(max_length=32)
    amount_minor = serializers.IntegerField(min_value=1)
    payment_id = serializers.CharField(max_length=128)
    topup_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class PromoPaymentInSerializer(serializers.Serializer):
    payment_id = serializers.CharField(max_length=128)


class PromoOutSerializer(serializers.Serializer):
    code = serializers.CharField()
    is_active = serializers.BooleanField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    max_total_uses = serializers.IntegerField()
    max_uses_per_user = serializers.IntegerField()
    uses_count = serializers.IntegerField()
    effect = serializers.DictField()


def build_effect_payload(promo: PromoCode, *, topup_amount_minor: int | None = None) -> dict:
    # Скидка
    if hasattr(promo, "topup_discount"):
        eff = promo.topup_discount
        out = {
            "type": "topup_discount",
            "currency": eff.currency,
            "discount_type": eff.discount_type,
            "discount_value": str(eff.discount_value),
            "min_topup_minor": eff.min_topup_minor,
            "max_discount_minor": eff.max_discount_minor,
        }
        if topup_amount_minor is not None:
            out["quote"] = eff.quote(topup_amount_minor)
        return out

    # Бонус
    if hasattr(promo, "balance_bonus"):
        eff = promo.balance_bonus
        out = {
            "type": "balance_bonus",
            "currency": eff.currency,
            "bonus_type": eff.bonus_type,
            "bonus_value": str(eff.bonus_value),
            "min_topup_minor": eff.min_topup_minor,
        }
        if topup_amount_minor is not None:
            try:
                out["preview_bonus_minor"] = eff.calc_bonus_minor(topup_amount_minor=topup_amount_minor)
            except Exception:
                pass
        return out

    # Предмет
    if hasattr(promo, "item_grant"):
        eff = promo.item_grant
        return {"type": "item_grant", "item_id": eff.item_id}

    return {"type": "none"}
