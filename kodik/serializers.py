# coding: utf-8
from __future__ import annotations

from rest_framework import serializers

from .models import (
    Material,
    MaterialExtra,
    MaterialVersion,
    Season,
    Episode,
    Translation,
    Genre,
    Studio,
    Country,
    LicenseOwner,
    MDLTag,
    Credit,
    Person,
    AkiUserRating,
    MaterialComment,
)

# ==== справочники ====

class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ("id", "code", "name", "slug")


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("id", "name", "slug", "source")


class StudioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Studio
        fields = ("id", "name", "slug")


class LicenseOwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenseOwner
        fields = ("id", "name", "slug")


class MDLTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = MDLTag
        fields = ("id", "name", "slug")


# ==== Translation ====

class TranslationShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Translation
        fields = ("id", "title", "type", "slug")


class TranslationDetailSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)

    class Meta:
        model = Translation
        fields = (
            "id",
            "ext_id",
            "title",
            "type",
            "slug",
            "poster_url",
            "avatar_url",
            "banner_url",
            "description",
            "website_url",
            "aliases",
            "country",
            "founded_year",
        )


# ==== Person ====

class PersonShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ("id", "name", "slug")


class PersonDetailSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)

    class Meta:
        model = Person
        fields = (
            "id",
            "name",
            "slug",
            "avatar_url",
            "photo_url",
            "banner_url",
            "bio",
            "birth_date",
            "death_date",
            "country",
            "imdb_id",
            "shikimori_id",
            "kinopoisk_id",
            "socials",
        )


# ==== Extra ====

class MaterialExtraSerializer(serializers.ModelSerializer):
    aki_rating = serializers.SerializerMethodField()
    aki_votes = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()

    class Meta:
        model = MaterialExtra
        fields = (
            "title",
            "anime_title",
            "title_en",
            "other_titles",
            "other_titles_en",
            "other_titles_jp",
            "anime_license_name",
            "anime_kind",
            "all_status",
            "anime_status",
            "drama_status",
            "tagline",
            "description",
            "anime_description",
            "poster_url",
            "anime_poster_url",
            "drama_poster_url",
            "duration",
            "kinopoisk_rating",
            "kinopoisk_votes",
            "imdb_rating",
            "imdb_votes",
            "shikimori_rating",
            "shikimori_votes",
            "mydramalist_rating",
            "mydramalist_votes",
            "premiere_ru",
            "premiere_world",
            "aired_at",
            "released_at",
            "next_episode_at",
            "rating_mpaa",
            "minimal_age",
            "episodes_total",
            "episodes_aired",
            # агрегаты
            "aki_rating",
            "aki_votes",
            "comments_count",
            "views_count",
        )

    def get_aki_rating(self, obj):
        return float(obj.aki_rating) if getattr(obj, "aki_rating", None) is not None else None

    def get_aki_votes(self, obj):
        v = getattr(obj, "aki_votes", None)
        return int(v) if v is not None else 0

    def get_comments_count(self, obj):
        v = getattr(obj, "comments_count", None)
        return int(v) if v is not None else 0


# ==== AKI РЕЙТИНГИ ====

class AkiUserRatingSerializer(serializers.ModelSerializer):
    material = serializers.SlugRelatedField(
        slug_field="kodik_id",
        queryset=Material.objects.all(),
    )
    score = serializers.IntegerField(min_value=1, max_value=10)

    class Meta:
        model = AkiUserRating
        fields = ("id", "material", "score", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError({"detail": "auth required"})

        material = validated_data["material"]
        score = validated_data["score"]

        obj, _ = AkiUserRating.objects.update_or_create(
            material=material,
            user=user,
            defaults={"score": score},
        )
        return obj


class AkiRatingSummarySerializer(serializers.Serializer):
    material = serializers.CharField()
    aki_rating = serializers.FloatField(allow_null=True)
    aki_votes = serializers.IntegerField()


# ==== КОММЕНТАРИИ ====

class MaterialCommentSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField(read_only=True)
    body = serializers.CharField(source="content", read_only=True)

    class Meta:
        model = MaterialComment
        fields = (
            "id",
            "material",
            "user",
            "parent",
            "body",
            "status",
            "is_deleted",
            "is_pinned",
            "likes_count",
            "replies_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id", "user", "status", "is_deleted",
            "likes_count", "replies_count", "created_at", "updated_at",
        )

    def get_user(self, obj):
        u = obj.user
        display = getattr(u, "first_name", "") or getattr(u, "username", "") or f"id:{u.id}"
        return {"id": u.id, "username": getattr(u, "username", ""), "display_name": display}


class MaterialCommentCreateSerializer(serializers.ModelSerializer):
    body = serializers.CharField(write_only=True)
    parent = serializers.PrimaryKeyRelatedField(
        queryset=MaterialComment.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = MaterialComment
        fields = ("material", "parent", "body")

    def validate_body(self, v: str):
        v = (v or "").strip()
        if not v:
            raise serializers.ValidationError("Empty comment")
        return v

    def validate(self, attrs):
        parent = attrs.get("parent")
        material = attrs.get("material")
        if parent and parent.material_id != material.kodik_id:
            raise serializers.ValidationError("Parent belongs to another material.")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("Auth required")

        content = validated_data.pop("body").strip()
        validated_data["content"] = content
        validated_data["user"] = request.user
        return super().create(validated_data)


# ==== сезоны/эпизоды ====

class EpisodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Episode
        fields = ("id", "number", "title", "link", "screenshots")


class SeasonSerializer(serializers.ModelSerializer):
    episodes = EpisodeSerializer(many=True, read_only=True)

    class Meta:
        model = Season
        fields = ("id", "number", "link", "episodes")


class MaterialVersionSerializer(serializers.ModelSerializer):
    translation = TranslationShortSerializer(read_only=True)
    seasons = SeasonSerializer(many=True, read_only=True)

    class Meta:
        model = MaterialVersion
        fields = ("id", "translation", "movie_link", "seasons")


# ==== кредиты ====

class CreditSerializer(serializers.ModelSerializer):
    person = PersonShortSerializer(read_only=True)

    class Meta:
        model = Credit
        fields = (
            "id",
            "role",
            "person",
            "character_name",
            "order",
            "note",
        )


# ==== списочный материал ====

class MaterialListSerializer(serializers.ModelSerializer):
    genres = GenreSerializer(many=True, read_only=True)
    studios = StudioSerializer(many=True, read_only=True)
    production_countries = CountrySerializer(many=True, read_only=True)

    # 👇 вместо прямого поля модели
    title = serializers.SerializerMethodField()

    primary_date = serializers.DateField(read_only=True)
    year_effective = serializers.IntegerField(read_only=True)
    primary_source = serializers.CharField(read_only=True)

    shikimori_rating = serializers.FloatField(
        source="extra.shikimori_rating", read_only=True, allow_null=True
    )
    views_count = serializers.IntegerField(
        source="extra.views_count", read_only=True
    )
    next_episode_at = serializers.DateTimeField(
        source="extra.next_episode_at",
        read_only=True,
        allow_null=True,
    )
    aired_at = serializers.DateField(
        source="extra.aired_at", read_only=True, allow_null=True
    )

    class Meta:
        model = Material
        fields = (
            "kodik_id",
            "slug",
            "type",
            "title",
            "title_orig",
            "year",
            "poster_url",
            "updated_at",
            "genres",
            "studios",
            "production_countries",
            "shikimori_rating",
            "views_count",
            "primary_date",
            "year_effective",
            "primary_source",
            "next_episode_at",
            "aired_at",
        )

    def get_title(self, obj: Material) -> str:
        extra = getattr(obj, "extra", None)
        if extra:
            # сначала anime_title, потом обычный title из extra
            if extra.anime_title:
                return extra.anime_title
            if extra.title:
                return extra.title
        return obj.title




# ==== детальный материал ====

class MaterialDetailSerializer(serializers.ModelSerializer):
    genres = GenreSerializer(many=True, read_only=True)
    studios = StudioSerializer(many=True, read_only=True)
    production_countries = CountrySerializer(many=True, read_only=True)
    license_owners = LicenseOwnerSerializer(many=True, read_only=True)
    mdl_tags = MDLTagSerializer(many=True, read_only=True)

    credits = CreditSerializer(many=True, read_only=True)
    extra = MaterialExtraSerializer(read_only=True)

    versions = MaterialVersionSerializer(many=True, read_only=True)
    translation = TranslationShortSerializer(read_only=True)

    primary_date = serializers.DateField(read_only=True)
    year_effective = serializers.IntegerField(read_only=True)
    primary_source = serializers.CharField(read_only=True)

    episodes_total = serializers.IntegerField(
        source="extra.episodes_total", read_only=True
    )
    episodes_aired = serializers.IntegerField(
        source="extra.episodes_aired", read_only=True
    )
    next_episode_at = serializers.DateTimeField(
        source="extra.next_episode_at",
        read_only=True,
        allow_null=True,
    )
    aired_at = serializers.DateField(
        source="extra.aired_at", read_only=True, allow_null=True
    )

    # 👇 переопределяем title
    title = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = (
            "kodik_id",
            "slug",
            "type",
            "link",
            "title",
            "title_orig",
            "other_title",
            "year",
            "poster_url",
            "kinopoisk_id",
            "imdb_id",
            "mdl_id",
            "shikimori_id",
            "worldart_link",
            "updated_at",
            "genres",
            "studios",
            "production_countries",
            "license_owners",
            "mdl_tags",
            "credits",
            "versions",
            "extra",
            "translation",
            "primary_date",
            "year_effective",
            "primary_source",
            "episodes_total",
            "episodes_aired",
            "next_episode_at",
            "aired_at",
        )

    def get_title(self, obj: Material) -> str:
        extra = getattr(obj, "extra", None)
        if extra:
            if extra.anime_title:
                return extra.anime_title
            if extra.title:
                return extra.title
        return obj.title
