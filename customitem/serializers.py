from rest_framework import serializers
from .models import Item, Inventory, AppliedCustomization


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = (
            "id", "type", "slug", "title", "description",
            "file", "file_url", "preview",
            "is_animated", "mime", "width", "height", "duration_ms",
            "rarity", "attributes",
            "price_aki", "limited_total", "limited_sold",
            "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = ("limited_sold", "created_at", "updated_at")


class InventorySerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = Inventory
        fields = ("id", "item", "source", "note", "acquired_at")


class AppliedCustomizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppliedCustomization
        fields = ("avatar_item", "header_item", "frame_item", "theme_item", "updated_at")
        read_only_fields = ("updated_at",)
