# shop/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Offer, Purchase, PurchaseStatus


# ===== Вспомогательный фильтр: продаётся ли сейчас =====
class SellingNowFilter(admin.SimpleListFilter):
    title = _("Продаётся сейчас")
    parameter_name = "selling_now"

    def lookups(self, request, model_admin):
        return (
            ("yes", _("Да")),
            ("no",  _("Нет")),
        )

    def queryset(self, request, queryset: QuerySet[Offer]):
        val = self.value()
        if val not in {"yes", "no"}:
            return queryset
        now = timezone.now()
        # Логика идентична Offer.is_selling_now(), но на уровне ORM
        cond = (
            queryset.filter(is_active=True)
            .filter(item__isnull=False, item__is_active=True)  # если у Item есть флаг активности
            .filter(item__price_aki__gt=0)
        )
        # starts_at / ends_at с учётом null
        cond = cond.filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
        cond = cond.filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
        return cond if val == "yes" else queryset.exclude(pk__in=cond.values("pk"))


# ===== Админка Offer =====
@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "item_link",
        "price_column",
        "is_active",
        "selling_now_badge",
        "starts_at",
        "ends_at",
        "created_at",
    )
    list_filter = (
        "is_active",
        SellingNowFilter,
        ("starts_at", admin.DateFieldListFilter),
        ("ends_at", admin.DateFieldListFilter),
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "item__title",
        "item__slug",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "current_price_readonly", "selling_now_readonly")
    list_select_related = ("item",)

    fieldsets = (
        (_("Предмет и состояние"), {
            "fields": ("item", "is_active", "selling_now_readonly"),
        }),
        (_("Цена"), {
            "fields": ("price_override_aki", "current_price_readonly"),
            "description": _("Если указана override-цена — она перекрывает Item.price_aki."),
        }),
        (_("Ограничение по времени"), {
            "fields": ("starts_at", "ends_at"),
        }),
        (_("Служебное"), {
            "fields": ("created_at", "updated_at"),
        }),
    )

    # ——— Колонки ———
    def item_link(self, obj: Offer):
        url = reverse("admin:customitem_item_change", args=[obj.item_id])
        return format_html('<a href="{}">{}</a>', url, obj.item.title)
    item_link.short_description = _("Предмет")

    def price_column(self, obj: Offer):
        if obj.price_override_aki is not None:
            return format_html(
                '<span title="override">{} <span style="color:#64748b;">(ovr)</span></span>',
                obj.price_override_aki,
            )
        return obj.item.price_aki
    price_column.short_description = _("Цена (AKI)")

    def selling_now_badge(self, obj: Offer):
        ok = obj.is_selling_now()
        color = "#065f46" if ok else "#991b1b"
        bg = "rgba(16,185,129,.12)" if ok else "rgba(239,68,68,.12)"
        text = "ДА" if ok else "НЕТ"
        return format_html(
            '<span style="padding:2px 8px;border-radius:999px;color:{};background:{};font-weight:600;font-size:12px;">{}</span>',
            color, bg, text,
        )
    selling_now_badge.short_description = _("Продаётся")

    # ——— ReadOnly поля ———
    def current_price_readonly(self, obj: Offer):
        if not obj.pk:
            return "-"
        return obj.current_price
    current_price_readonly.short_description = _("Текущая цена (AKI)")

    def selling_now_readonly(self, obj: Offer):
        if not obj.pk:
            return "-"
        return "Да" if obj.is_selling_now() else "Нет"
    selling_now_readonly.short_description = _("Продаётся сейчас")

    # ——— Actions ———
    actions = ("make_active", "make_inactive")

    @admin.action(description=_("Сделать активными"))
    def make_active(self, request, queryset: QuerySet[Offer]):
        updated = queryset.update(is_active=True)
        self.message_user(request, _(f"Обновлено офферов: {updated}"), messages.SUCCESS)

    @admin.action(description=_("Сделать неактивными"))
    def make_inactive(self, request, queryset: QuerySet[Offer]):
        updated = queryset.update(is_active=False)
        self.message_user(request, _(f"Обновлено офферов: {updated}"), messages.SUCCESS)


# ===== Админка Purchase =====
@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_link",
        "item_link",
        "price_aki",
        "status_badge",
        "transaction_link",
        "created_at",
    )
    list_filter = (
        "status",
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "user__username",
        "user__email",
        "item__title",
        "item__slug",
        "transaction__idempotency_key",
        "transaction__external_id",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = (
        "user", "item", "price_aki", "transaction", "status", "created_at",
        "user_link_readonly", "item_link_readonly", "transaction_link_readonly",
    )
    list_select_related = ("user", "item", "transaction")

    fieldsets = (
        (_("Общее"), {"fields": ("user_link_readonly", "item_link_readonly", "price_aki", "status")}),
        (_("Транзакция"), {"fields": ("transaction_link_readonly",)}),
        (_("Служебное"), {"fields": ("created_at",)}),
    )

    # ——— Колонки ———
    def user_link(self, obj: Purchase):
        url = reverse("admin:users_user_change", args=[obj.user_id])
        return format_html('<a href="{}">@{}</a>', url, obj.user.username)
    user_link.short_description = _("Пользователь")

    def item_link(self, obj: Purchase):
        url = reverse("admin:customitem_item_change", args=[obj.item_id])
        return format_html('<a href="{}">{}</a>', url, obj.item.title)
    item_link.short_description = _("Предмет")

    def transaction_link(self, obj: Purchase):
        url = reverse("admin:economy_transaction_change", args=[obj.transaction_id])
        # можно добавить короткое описание транзакции
        return format_html('<a href="{}">#{}</a>', url, obj.transaction_id)
    transaction_link.short_description = _("Транзакция")

    def status_badge(self, obj: Purchase):
        ok = obj.status == PurchaseStatus.SUCCESS
        color = "#065f46" if ok else "#991b1b"
        bg = "rgba(16,185,129,.12)" if ok else "rgba(239,68,68,.12)"
        text = "УСПЕШНО" if ok else "ОШИБКА"
        return format_html(
            '<span style="padding:2px 8px;border-radius:999px;color:{};background:{};font-weight:600;font-size:12px;">{}</span>',
            color, bg, text,
        )
    status_badge.short_description = _("Статус")

    # ——— ReadOnly поля (для fieldsets) ———
    def user_link_readonly(self, obj: Purchase):
        return self.user_link(obj)
    user_link_readonly.short_description = _("Пользователь")

    def item_link_readonly(self, obj: Purchase):
        return self.item_link(obj)
    item_link_readonly.short_description = _("Предмет")

    def transaction_link_readonly(self, obj: Purchase):
        return self.transaction_link(obj)
    transaction_link_readonly.short_description = _("Транзакция")


# ===== Дополнительно (опционально) =====
# Если хочешь видеть покупки прямо внутри карточки Item — можно сделать Inline в админке Item.
# Пример (в приложении customitem/admin.py):
#
# from django.contrib import admin
# from shop.models import Purchase
#
# class PurchaseInline(admin.TabularInline):
#     model = Purchase
#     fields = ("user", "price_aki", "status", "transaction", "created_at")
#     readonly_fields = fields
#     extra = 0
#     can_delete = False
#
# @admin.register(Item)
# class ItemAdmin(admin.ModelAdmin):
#     inlines = [PurchaseInline]
#     # ... остальной конфиг
