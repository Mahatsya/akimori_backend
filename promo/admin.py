# promo/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    PromoCode,
    PromoRedemption,
    PromoTopupDiscount,
    PromoBalanceBonus,
    PromoItemGrant,
)


# ---------- Inlines (эффекты промокода) ----------

class PromoTopupDiscountInline(admin.StackedInline):
    model = PromoTopupDiscount
    extra = 0
    max_num = 1
    can_delete = True
    fieldsets = (
        (None, {
            "fields": (
                "currency",
                ("discount_type", "discount_value"),
                ("min_topup_minor", "max_discount_minor"),
            )
        }),
    )


class PromoBalanceBonusInline(admin.StackedInline):
    model = PromoBalanceBonus
    extra = 0
    max_num = 1
    can_delete = True
    fieldsets = (
        (None, {
            "fields": (
                "currency",
                ("bonus_type", "bonus_value"),
                "min_topup_minor",
            )
        }),
    )


class PromoItemGrantInline(admin.StackedInline):
    model = PromoItemGrant
    extra = 0
    max_num = 1
    can_delete = True
    autocomplete_fields = ("item",)
    fieldsets = ((None, {"fields": ("item",)}),)


# ---------- PromoCode admin ----------

@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "is_active",
        "window_status",
        "starts_at",
        "ends_at",
        "uses_count",
        "max_total_uses",
        "max_uses_per_user",
        "effect_type",
        "created_at",
    )
    list_filter = ("is_active", "starts_at", "ends_at", "created_at")
    search_fields = ("code", "note")
    ordering = ("-created_at",)
    readonly_fields = ("uses_count", "created_at")

    fieldsets = (
        (None, {"fields": ("code", "note", "is_active")}),
        ("Окно действия", {"fields": ("starts_at", "ends_at")}),
        ("Лимиты", {"fields": ("max_total_uses", "max_uses_per_user", "uses_count")}),
        ("Служебное", {"fields": ("created_at",)}),
    )

    inlines = (PromoBalanceBonusInline, PromoItemGrantInline, PromoTopupDiscountInline)

    actions = ("activate", "deactivate", "reset_uses_count")

    def window_status(self, obj: PromoCode):
        now = timezone.now()
        if obj.starts_at and now < obj.starts_at:
            return format_html('<span style="color:#f59e0b;font-weight:600;">Не начался</span>')
        if obj.ends_at and now > obj.ends_at:
            return format_html('<span style="color:#ef4444;font-weight:600;">Истёк</span>')
        return format_html('<span style="color:#22c55e;font-weight:600;">Активен</span>')
    window_status.short_description = "Статус окна"

    def effect_type(self, obj: PromoCode):
        if hasattr(obj, "balance_bonus"):
            eff = obj.balance_bonus
            return f"balance_bonus ({eff.currency})"
        if hasattr(obj, "item_grant"):
            return "item_grant"
        if hasattr(obj, "topup_discount"):
            eff = obj.topup_discount
            return f"topup_discount ({eff.currency})"
        return "none"
    effect_type.short_description = "Эффект"

    @admin.action(description="Активировать выбранные промокоды")
    def activate(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Деактивировать выбранные промокоды")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Сбросить uses_count (опасно)")
    def reset_uses_count(self, request, queryset):
        queryset.update(uses_count=0)


# ---------- PromoRedemption admin ----------

@admin.register(PromoRedemption)
class PromoRedemptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "promo_code",
        "user",
        "status",
        "context",
        "topup_amount_minor",
        "payment_id",
        "idempotency_key",
        "redeemed_at",
        "applied_at",
    )
    list_filter = ("status", "context", "redeemed_at", "applied_at")
    search_fields = (
        "promo__code",
        "user__username",
        "user__email",
        "payment_id",
        "topup_id",
        "idempotency_key",
        "ip",
    )
    ordering = ("-redeemed_at",)
    readonly_fields = (
        "promo",
        "user",
        "status",
        "context",
        "topup_amount_minor",
        "payment_id",
        "topup_id",
        "idempotency_key",
        "reserved_until",
        "redeemed_at",
        "applied_at",
        "ip",
        "user_agent",
        "payload",
    )

    fieldsets = (
        (None, {"fields": ("promo", "user", "status", "context")}),
        ("Связь с оплатой", {"fields": ("payment_id", "topup_id", "topup_amount_minor")}),
        ("Резерв", {"fields": ("idempotency_key", "reserved_until")}),
        ("Даты", {"fields": ("redeemed_at", "applied_at")}),
        ("Клиент", {"fields": ("ip", "user_agent")}),
        ("Payload", {"fields": ("payload",)}),
    )

    def promo_code(self, obj: PromoRedemption):
        return obj.promo.code
    promo_code.short_description = "Промокод"
