from django.contrib import admin
from .models import Item, Inventory, AppliedCustomization


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    """
    Каталог косметических предметов.
    """
    list_display = (
        "id", "title_ru", "type_ru", "price_aki_ru", "rarity_ru",
        "is_active_ru", "limited_total_ru", "limited_sold_ru", "created_at_ru",
    )
    list_display_links = ("id", "title_ru")
    list_filter = ("type", "rarity", "is_active")
    search_fields = ("title", "slug", "description")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    empty_value_display = "—"

    fieldsets = (
        ("Основное", {
            "fields": ("type", "title", "slug", "description"),
            "description": "Название, тип и краткое описание предмета.",
        }),
        ("Медиа", {
            "fields": ("file", "file_url", "preview", "is_animated", "mime", "width", "height", "duration_ms"),
            "description": "Файл или URL + характеристики медиа.",
        }),
        ("Характеристики", {
            "fields": ("rarity", "attributes"),
            "description": "Редкость и произвольные атрибуты (например, цвета темы).",
        }),
        ("Продажи", {
            "fields": ("price_aki", "limited_total", "limited_sold", "is_active"),
            "description": "Цена в AkiCoin, лимиты продаж и активность товара.",
        }),
        ("Служебное", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    # Русские колонки
    def title_ru(self, obj): return obj.title
    title_ru.short_description = "Название"
    title_ru.admin_order_field = "title"

    def type_ru(self, obj): return obj.get_type_display()
    type_ru.short_description = "Тип"
    type_ru.admin_order_field = "type"

    def price_aki_ru(self, obj): return obj.price_aki
    price_aki_ru.short_description = "Цена (AKI)"
    price_aki_ru.admin_order_field = "price_aki"

    def rarity_ru(self, obj): return obj.get_rarity_display()
    rarity_ru.short_description = "Редкость"
    rarity_ru.admin_order_field = "rarity"

    @admin.display(boolean=True, description="Активен", ordering="is_active")
    def is_active_ru(self, obj): return obj.is_active

    def limited_total_ru(self, obj): return obj.limited_total
    limited_total_ru.short_description = "Лимит (всего)"
    limited_total_ru.admin_order_field = "limited_total"

    def limited_sold_ru(self, obj): return obj.limited_sold
    limited_sold_ru.short_description = "Продано"
    limited_sold_ru.admin_order_field = "limited_sold"

    def created_at_ru(self, obj): return obj.created_at
    created_at_ru.short_description = "Создано"
    created_at_ru.admin_order_field = "created_at"


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    """
    Инвентарь пользователей (кто чем владеет).
    """
    list_display = ("id", "user_ru", "item_ru", "source_ru", "acquired_at_ru")
    list_display_links = ("id", "user_ru", "item_ru")
    list_filter = ("source", "item__type", "item__rarity")
    search_fields = ("user__username", "item__title", "item__slug")
    raw_id_fields = ("user", "item")
    date_hierarchy = "acquired_at"
    ordering = ("-acquired_at",)
    empty_value_display = "—"

    fieldsets = (
        ("Запись инвентаря", {
            "fields": ("user", "item", "source", "note", "acquired_at"),
            "description": "Кому принадлежит предмет, откуда получен и когда.",
        }),
    )

    def user_ru(self, obj): return obj.user
    user_ru.short_description = "Пользователь"
    user_ru.admin_order_field = "user"

    def item_ru(self, obj): return obj.item
    item_ru.short_description = "Предмет"
    item_ru.admin_order_field = "item"

    def source_ru(self, obj): return obj.get_source_display()
    source_ru.short_description = "Источник"
    source_ru.admin_order_field = "source"

    def acquired_at_ru(self, obj): return obj.acquired_at
    acquired_at_ru.short_description = "Получено"
    acquired_at_ru.admin_order_field = "acquired_at"


@admin.register(AppliedCustomization)
class AppliedCustomizationAdmin(admin.ModelAdmin):
    """
    Надетые предметы (активные аватар/шапка/рамка/тема).
    """
    list_display = ("user_ru", "avatar_item_ru", "header_item_ru", "frame_item_ru", "theme_item_ru", "updated_at_ru")
    list_display_links = ("user_ru",)
    raw_id_fields = ("user", "avatar_item", "header_item", "frame_item", "theme_item")
    ordering = ("-updated_at",)
    empty_value_display = "—"

    fieldsets = (
        ("Активные предметы пользователя", {
            "fields": ("user", "avatar_item", "header_item", "frame_item", "theme_item"),
            "description": "Выбранные предметы для аватара, шапки профиля, рамки и темы.",
        }),
        ("Служебное", {
            "fields": ("updated_at",),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("updated_at",)

    def user_ru(self, obj): return obj.user
    user_ru.short_description = "Пользователь"
    user_ru.admin_order_field = "user"

    def avatar_item_ru(self, obj): return obj.avatar_item
    avatar_item_ru.short_description = "Аватар"

    def header_item_ru(self, obj): return obj.header_item
    header_item_ru.short_description = "Шапка"

    def frame_item_ru(self, obj): return obj.frame_item
    frame_item_ru.short_description = "Рамка"

    def theme_item_ru(self, obj): return obj.theme_item
    theme_item_ru.short_description = "Тема"

    def updated_at_ru(self, obj): return obj.updated_at
    updated_at_ru.short_description = "Обновлено"
    updated_at_ru.admin_order_field = "updated_at"

