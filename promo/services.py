from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import PromoCode, PromoRedemption


RESERVE_TTL_MINUTES = 20


@transaction.atomic
def reserve_promo_for_topup(
    *,
    code: str,
    user,
    topup_amount_minor: int,
    payment_id: str,
    topup_id: str = "",
    idempotency_key: str = "",
    ip: str = "",
    ua: str = "",
) -> PromoRedemption:
    """
    Создаём/возвращаем PENDING резерв. uses_count НЕ увеличиваем.
    """
    code = (code or "").strip().upper()
    if not code:
        raise ValidationError({"code": "promo_required"})
    if not payment_id:
        raise ValidationError({"payment_id": "required"})

    now = timezone.now()

    # Идемпотентность: если уже есть по ключу — возвращаем
    if idempotency_key:
        existing = (
            PromoRedemption.objects.select_for_update()
            .filter(idempotency_key=idempotency_key)
            .order_by("-redeemed_at")
            .first()
        )
        if existing:
            return existing

    promo = PromoCode.objects.select_for_update().filter(code=code).first()
    if not promo:
        raise ValidationError({"code": "promo_not_found"})

    ok, reason = promo.can_user_redeem_applied(user, now=now)
    if not ok:
        raise ValidationError({"code": reason})

    # чистим протухшие PENDING
    PromoRedemption.objects.filter(
        promo=promo,
        status=PromoRedemption.Status.PENDING,
        reserved_until__lt=now,
    ).update(status=PromoRedemption.Status.EXPIRED)

    # защита от oversubscribe по total uses:
    # учитываем активные резервы (PENDING), чтобы промо не “разобрали” больше лимита
    active_pending = PromoRedemption.objects.filter(
        promo=promo,
        status=PromoRedemption.Status.PENDING,
        reserved_until__gt=now,
    ).count()
    if promo.uses_count + active_pending >= promo.max_total_uses:
        raise ValidationError({"code": "promo_limit_reached"})

    # если у юзера уже есть активный резерв на это промо — вернём его
    existing_user_pending = (
        PromoRedemption.objects.select_for_update()
        .filter(
            promo=promo,
            user=user,
            status=PromoRedemption.Status.PENDING,
            reserved_until__gt=now,
        )
        .order_by("-redeemed_at")
        .first()
    )
    if existing_user_pending:
        return existing_user_pending

    red = PromoRedemption.objects.create(
        promo=promo,
        user=user,
        status=PromoRedemption.Status.PENDING,
        context="topup",
        topup_amount_minor=topup_amount_minor,
        payment_id=payment_id,
        topup_id=topup_id or "",
        idempotency_key=idempotency_key or "",
        reserved_until=now + timedelta(minutes=RESERVE_TTL_MINUTES),
        ip=ip,
        user_agent=(ua or "")[:255],
    )

    # payload: discount quote / bonus preview / item preview
    if hasattr(promo, "topup_discount"):
        q = promo.topup_discount.quote(topup_amount_minor)
        if not q.get("ok"):
            red.status = PromoRedemption.Status.CANCELLED
            red.payload = {"type": "topup_discount", "quote": q}
            red.save(update_fields=["status", "payload"])
            raise ValidationError({"code": q.get("reason", "topup_discount_invalid")})

        red.payload = {"type": "topup_discount", "quote": q}
        red.save(update_fields=["payload"])

    elif hasattr(promo, "balance_bonus"):
        try:
            bonus_minor = promo.balance_bonus.calc_bonus_minor(topup_amount_minor=topup_amount_minor)
            red.payload = {
                "type": "balance_bonus_pending",
                "currency": promo.balance_bonus.currency,
                "topup_amount_minor": topup_amount_minor,
                "bonus_minor": bonus_minor,
            }
            red.save(update_fields=["payload"])
        except Exception:
            pass

    elif hasattr(promo, "item_grant"):
        red.payload = {"type": "item_grant_pending", "item_id": promo.item_grant.item_id}
        red.save(update_fields=["payload"])

    return red


@transaction.atomic
def apply_promo_after_payment_success(*, payment_id: str) -> PromoRedemption:
    """
    Вызывается ТОЛЬКО при подтверждённой оплате.
    Делает PENDING -> APPLIED, uses_count++, и применяет эффект (бонус/предмет).
    """
    payment_id = (payment_id or "").strip()
    if not payment_id:
        raise ValidationError({"payment_id": "required"})

    now = timezone.now()

    red = (
        PromoRedemption.objects.select_for_update()
        .select_related("promo")
        .filter(payment_id=payment_id)
        .order_by("-redeemed_at")
        .first()
    )
    if not red:
        raise ValidationError({"code": "redemption_not_found"})

    if red.status == PromoRedemption.Status.APPLIED:
        return red  # идемпотентно
    if red.status in (PromoRedemption.Status.CANCELLED, PromoRedemption.Status.EXPIRED):
        raise ValidationError({"code": "redemption_not_active"})

    if red.reserved_until and red.reserved_until < now:
        red.status = PromoRedemption.Status.EXPIRED
        red.save(update_fields=["status"])
        raise ValidationError({"code": "reservation_expired"})

    promo = PromoCode.objects.select_for_update().get(pk=red.promo_id)

    ok, reason = promo.can_user_redeem_applied(red.user, now=now)
    if not ok:
        red.status = PromoRedemption.Status.CANCELLED
        red.save(update_fields=["status"])
        raise ValidationError({"code": reason})

    # выдача только для bonus/item (скидка уже учтена в оплате)
    if hasattr(promo, "balance_bonus") or hasattr(promo, "item_grant"):
        promo.apply_effect(user=red.user, redemption=red, topup_amount_minor=red.topup_amount_minor)

    red.status = PromoRedemption.Status.APPLIED
    red.applied_at = now
    red.save(update_fields=["status", "applied_at", "payload"])

    PromoCode.objects.filter(pk=promo.pk).update(uses_count=F("uses_count") + 1)
    return red


@transaction.atomic
def cancel_promo_reservation(*, payment_id: str) -> PromoRedemption | None:
    """
    Вызывается если платёж отменён/не прошёл.
    """
    payment_id = (payment_id or "").strip()
    if not payment_id:
        return None

    red = (
        PromoRedemption.objects.select_for_update()
        .filter(payment_id=payment_id)
        .order_by("-redeemed_at")
        .first()
    )
    if not red:
        return None

    if red.status == PromoRedemption.Status.APPLIED:
        return red  # уже применено

    red.status = PromoRedemption.Status.CANCELLED
    red.save(update_fields=["status"])
    return red


@transaction.atomic
def manual_redeem_now(*, code: str, user, ip: str = "", ua: str = "") -> PromoRedemption:
    """
    Для ручного промо (не topup): сразу APPLIED + uses_count++ + выдача эффекта.
    """
    code = (code or "").strip().upper()
    promo = PromoCode.objects.select_for_update().filter(code=code).first()
    if not promo:
        raise ValidationError({"code": "promo_not_found"})

    ok, reason = promo.can_user_redeem_applied(user)
    if not ok:
        raise ValidationError({"code": reason})

    now = timezone.now()

    red = PromoRedemption.objects.create(
        promo=promo,
        user=user,
        status=PromoRedemption.Status.APPLIED,
        context="manual",
        redeemed_at=now,
        applied_at=now,
        ip=ip,
        user_agent=(ua or "")[:255],
    )

    promo.apply_effect(user=user, redemption=red, topup_amount_minor=None)
    PromoCode.objects.filter(pk=promo.pk).update(uses_count=F("uses_count") + 1)
    return red
