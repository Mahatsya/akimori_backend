# shop/serializers.py
from urllib.parse import urlparse

from rest_framework import serializers

from .models import Offer, Purchase
from customitem.models import Item


class ItemBriefSerializer(serializers.ModelSerializer):
    """
    Мини-карта предмета для витрины (магазина/инвентаря).

    Важно:
    - preview_url: всегда пытаемся отдать рабочий абсолютный URL.
      Приоритет источника:
        1) preview (ImageField)
        2) file (FileField)
        3) file_url (внешняя ссылка)
    """
    preview_url = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = (
            "id",
            "slug",
            "title",
            "type",
            "rarity",
            "is_animated",
            "mime",
            "width",
            "height",
            "duration_ms",
            "price_aki",        # базовая цена из каталога (для справки)
            "limited_total",
            "limited_sold",
            "preview_url",
        )

    def _abs_url(self, url: str | None) -> str | None:
        """Собираем абсолютный URL, если пришёл относительный (напр. /media/...)."""
        if not url:
            return None
        try:
            parsed = urlparse(url)
            # Если уже абсолютный — возвращаем как есть
            if parsed.scheme and parsed.netloc:
                return url
        except Exception:
            pass
        # Иначе — собираем абсолютный через request, если он есть
        req = self.context.get("request")
        return req.build_absolute_uri(url) if req else url

    def get_preview_url(self, obj: Item) -> str | None:
        # 1) Явная превью-картинка
        if obj.preview and hasattr(obj.preview, "url"):
            return self._abs_url(obj.preview.url)
        # 2) Основной файл (если допустимо показывать как превью)
        if obj.file and hasattr(obj.file, "url"):
            return self._abs_url(obj.file.url)
        # 3) Внешняя ссылка
        if obj.file_url:
            return self._abs_url(obj.file_url)
        return None


class OfferSerializer(serializers.ModelSerializer):
    """
    Оффер на витрине + вычисляемые поля:
      - current_price — итоговая цена (override или item.price_aki)
      - selling_now   — доступен ли к покупке прямо сейчас (True/False)
    """
    item = ItemBriefSerializer(read_only=True)
    current_price = serializers.SerializerMethodField()
    selling_now = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = (
            "id",
            "item",
            "is_active",
            "price_override_aki",
            "starts_at",
            "ends_at",
            "updated_at",
            "current_price",
            "selling_now",
        )

    def get_current_price(self, obj: Offer) -> int:
        return obj.current_price

    def get_selling_now(self, obj: Offer) -> bool:
        return obj.is_selling_now()


class PurchaseSerializer(serializers.ModelSerializer):
    """
    Сериализация факта покупки (на случай списков/истории).
    """
    item = ItemBriefSerializer(read_only=True)

    class Meta:
        model = Purchase
        fields = ("id", "user", "item", "price_aki", "status", "created_at")
        read_only_fields = fields
