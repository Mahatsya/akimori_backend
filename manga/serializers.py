from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import (
    Manga, Category, Genre,
    TranslatorPublisher, TranslatorMember,
    Edition, Chapter, ChapterPage
)

User = get_user_model()


# ---- Справочники ----
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("slug", "title")


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("slug", "title")


# ---- Пользователи/Команда переводчика ----
class UserLiteSerializer(serializers.ModelSerializer):
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name")

    def get_first_name(self, obj):
        return getattr(obj, "first_name", "") or ""

    def get_last_name(self, obj):
        return getattr(obj, "last_name", "") or ""


class TranslatorMemberSerializer(serializers.ModelSerializer):
    user = UserLiteSerializer()

    class Meta:
        model = TranslatorMember
        fields = ("id", "role", "title", "is_active", "created_at", "updated_at", "user")


# ---- Переводчик/паблишер ----
class TranslatorMiniSerializer(serializers.ModelSerializer):
    """
    Компактная карточка паблишера для списков в манге.
    """
    class Meta:
        model = TranslatorPublisher
        fields = ("id", "slug", "name", "avatar_url", "followers_count", "manga_count")


class TranslatorSerializer(TranslatorMiniSerializer):
    """
    Полная карточка без участников (для Edition).
    """
    class Meta(TranslatorMiniSerializer.Meta):
        fields = TranslatorMiniSerializer.Meta.fields + ("description",)


class TranslatorDetailSerializer(TranslatorSerializer):
    """
    Деталка паблишера с участниками.
    """
    members = serializers.SerializerMethodField()

    class Meta(TranslatorSerializer.Meta):
        fields = TranslatorSerializer.Meta.fields + ("members",)

    def get_members(self, obj):
        qs = obj.translatormember_set.select_related("user").order_by("role", "user_id")
        return TranslatorMemberSerializer(qs, many=True).data


# ---- Манга/Издания/Главы ----
class ChapterPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChapterPage
        fields = ("id", "order", "image", "type", "created_at", "updated_at")


class ChapterSerializer(serializers.ModelSerializer):
    pages = ChapterPageSerializer(many=True, read_only=True)

    class Meta:
        model = Chapter
        fields = (
            "id", "edition", "number", "name", "volume",
            "pages_count", "published_at",
            "uploaded_by", "created_at", "updated_at",
            "pages",
        )
        read_only_fields = ("uploaded_by", "pages_count")

    def create(self, validated_data):
        request = self.context.get("request")
        return Chapter.objects.create(
            **validated_data,
            uploaded_by=(request.user if request and request.user.is_authenticated else None),
        )


class EditionLiteSerializer(serializers.ModelSerializer):
    translator = TranslatorSerializer()
    is_member = serializers.SerializerMethodField()

    class Meta:
        model = Edition
        fields = ("id", "translation_status", "translator", "is_member")

    def get_is_member(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        qs = obj.translator.translatormember_set.select_related("user")
        return qs.filter(user=request.user, is_active=True).exists()


class EditionDetailSerializer(serializers.ModelSerializer):
    translator = TranslatorSerializer()
    chapters = ChapterSerializer(many=True)

    class Meta:
        model = Edition
        fields = ("id", "translation_status", "translator", "chapters")


# ---- Manga (списки/детали) ----
class MangaListSerializer(serializers.ModelSerializer):
    categories  = CategorySerializer(many=True)
    genres      = GenreSerializer(many=True)
    poster_url  = serializers.SerializerMethodField()
    banner_url  = serializers.SerializerMethodField()

    # правильные имена
    translators      = serializers.SerializerMethodField()
    main_translator  = serializers.SerializerMethodField()
    # совместимость (если фронт уже ждёт publishers)
    publishers       = serializers.SerializerMethodField()
    main_publisher   = serializers.SerializerMethodField()

    class Meta:
        model  = Manga
        fields = (
            "id", "slug",
            "title_ru", "title_en", "alt_titles",
            "type", "age_rating", "year",
            "poster_url", "banner_url",
            "work_status",
            "categories", "genres",
            # новые поля:
            "translators", "main_translator",
            # алиасы для совместимости (можно убрать позже)
            "publishers", "main_publisher",
        )

    # helpers
    def _abs(self, url):
        req = self.context.get("request")
        return req.build_absolute_uri(url) if (req and url) else url

    def _unique_translators(self, obj: Manga):
        seen, items = set(), []
        # ожидаем prefetch: editions__translator
        for ed in getattr(obj, "editions", []).all() if hasattr(obj, "editions") else []:
            tr = getattr(ed, "translator", None)
            if tr and tr.id not in seen:
                seen.add(tr.id)
                items.append(tr)
        return items

    # url fields
    def get_poster_url(self, obj):  return self._abs(obj.poster_url)
    def get_banner_url(self, obj):  return self._abs(obj.banner_url)

    # translators
    def get_translators(self, obj):
        trs = self._unique_translators(obj)
        return TranslatorMiniSerializer(trs, many=True, context=self.context).data

    def get_main_translator(self, obj):
        trs = self._unique_translators(obj)
        return TranslatorMiniSerializer(trs[0], context=self.context).data if trs else None

    # compatibility aliases
    def get_publishers(self, obj):        return self.get_translators(obj)
    def get_main_publisher(self, obj):    return self.get_main_translator(obj)


class MangaDetailSerializer(serializers.ModelSerializer):
    categories  = CategorySerializer(many=True)
    genres      = GenreSerializer(many=True)
    editions    = EditionLiteSerializer(many=True)
    poster_url  = serializers.SerializerMethodField()
    banner_url  = serializers.SerializerMethodField()

    translators      = serializers.SerializerMethodField()
    main_translator  = serializers.SerializerMethodField()
    publishers       = serializers.SerializerMethodField()      # alias
    main_publisher   = serializers.SerializerMethodField()      # alias

    class Meta:
        model  = Manga
        fields = (
            "id", "slug",
            "title_ru", "title_en", "alt_titles",
            "type", "age_rating", "year",
            "poster_url", "banner_url",
            "description", "work_status",
            "links",
            "categories", "genres",
            "editions",
            "translators", "main_translator",
            "publishers", "main_publisher",  # совместимость
            "created_at", "updated_at",
        )

    def _abs(self, url):
        req = self.context.get("request")
        return req.build_absolute_uri(url) if (req and url) else url

    def _unique_translators(self, obj: Manga):
        seen, items = set(), []
        for ed in obj.editions.all():
            tr = getattr(ed, "translator", None)
            if tr and tr.id not in seen:
                seen.add(tr.id)
                items.append(tr)
        return items

    def get_poster_url(self, obj):  return self._abs(obj.poster_url)
    def get_banner_url(self, obj):  return self._abs(obj.banner_url)

    def get_translators(self, obj):
        trs = self._unique_translators(obj)
        return TranslatorMiniSerializer(trs, many=True, context=self.context).data

    def get_main_translator(self, obj):
        trs = self._unique_translators(obj)
        return TranslatorMiniSerializer(trs[0], context=self.context).data if trs else None

    # алиасы
    def get_publishers(self, obj):        return self.get_translators(obj)
    def get_main_publisher(self, obj):    return self.get_main_translator(obj)


class MangaDetailWithChaptersSerializer(MangaDetailSerializer):
    editions = EditionDetailSerializer(many=True)


# ---- Спец. сериализаторы для загрузки страниц ----
class ChapterImagesUploadSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.ImageField(allow_empty_file=False),
        allow_empty=False
    )


class ChapterZipUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
