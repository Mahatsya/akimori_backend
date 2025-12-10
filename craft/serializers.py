from rest_framework import serializers
from .models import HeaderMaterialContent


class HeaderMaterialContentSerializer(serializers.ModelSerializer):
    # поля из Kodik.Material / MaterialExtra
    slug = serializers.CharField(source="material.slug", read_only=True)
    year = serializers.IntegerField(source="material.year", read_only=True)
    type = serializers.CharField(source="material.type", read_only=True)

    shikimori_rating = serializers.FloatField(
        source="material.extra.shikimori_rating",
        read_only=True,
        allow_null=True,
    )
    aired_at = serializers.DateField(
        source="material.extra.aired_at", read_only=True, allow_null=True
    )
    next_episode_at = serializers.DateTimeField(
        source="material.extra.next_episode_at", read_only=True, allow_null=True
    )
    description = serializers.CharField(
        source="material.extra.description", read_only=True, allow_blank=True
    )

    # 🔥 заменяем title на get_title()
    title = serializers.SerializerMethodField()

    # наш постер
    poster_url = serializers.SerializerMethodField()

    class Meta:
        model = HeaderMaterialContent
        fields = [
            "id",
            "poster_url",
            "slug",
            "title",
            "year",
            "type",
            "shikimori_rating",
            "aired_at",
            "next_episode_at",
            "description",
        ]

    # ==== TITLE PRIORITY: anime_title > extra.title > material.title ====
    def get_title(self, obj):
        material = obj.material
        extra = getattr(material, "extra", None)

        if extra:
            if extra.anime_title:
                return extra.anime_title
            if extra.title:
                return extra.title

        return material.title

    # ==== POSTER ====
    def get_poster_url(self, obj: HeaderMaterialContent) -> str:
        request = self.context.get("request")

        # приоритет: наш постер из Craft
        if obj.poster:
            url = obj.poster.url
            return request.build_absolute_uri(url) if request else url

        # fallback — постер из Kodik.extra
        extra = getattr(obj.material, "extra", None)
        fallback = getattr(extra, "poster_url", "") if extra else ""
        return fallback or ""
