from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password

from .models import User, Profile, UserAnimeList, AvatarMedia
from kodik.models import Material
from customitem.models import AppliedCustomization, Item


# ===== Пользователи / Профили =====

class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "is_active", "date_joined")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("username", "email", "password", "role")
        extra_kwargs = {"role": {"required": False}}

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        pwd = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(pwd)
        user.save()
        return user


class AvatarMediaSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = AvatarMedia
        fields = ("id","url","created_at")

    def get_url(self, obj):
        req = self.context.get("request")
        return req.build_absolute_uri(obj.file.url) if req else obj.file.url


# ===== Профиль (публично) =====

class ProfilePublicSerializer(serializers.ModelSerializer):
    user = UserPublicSerializer(read_only=True)

    # ссылки на текущие применённые медиа
    avatar_url = serializers.SerializerMethodField()
    header_url = serializers.SerializerMethodField()
    frame_url  = serializers.SerializerMethodField()

    # прогресс
    xp = serializers.IntegerField(read_only=True)
    level = serializers.IntegerField(read_only=True)
    max_level = serializers.IntegerField(read_only=True)
    next_level_total_xp = serializers.IntegerField(read_only=True, source="next_level_xp")
    need_for_next = serializers.IntegerField(read_only=True)
    progress = serializers.FloatField(read_only=True)

    # id надетых предметов
    frame_item_id  = serializers.SerializerMethodField()
    header_item_id = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = (
            "user", "display_name", "bio",
            "avatar_url", "header_url", "frame_url",
            "xp", "level", "max_level",
            "next_level_total_xp", "need_for_next", "progress",
            "frame_item_id", "header_item_id",
        )

    def _abs(self, req, f):
        return req.build_absolute_uri(f.url) if req else f.url

    def get_avatar_url(self, obj: Profile):
        req = self.context.get("request")
        applied = getattr(obj.user, "applied_custom", None)
        if applied and applied.avatar_item:
            item: Item = applied.avatar_item
            if getattr(item, "file_url", None):
                return item.file_url
            if getattr(item, "file", None):
                return self._abs(req, item.file)
        if obj.avatar and hasattr(obj.avatar, "url"):
            return self._abs(req, obj.avatar)
        return None

    def get_header_url(self, obj: Profile):
        req = self.context.get("request")
        applied = getattr(obj.user, "applied_custom", None)
        if not applied or not getattr(applied, "header_item", None):
            return None
        item: Item = applied.header_item
        if getattr(item, "file_url", None):
            return item.file_url
        if getattr(item, "file", None):
            return self._abs(req, item.file)
        return None

    def get_frame_url(self, obj: Profile):
        req = self.context.get("request")
        applied = getattr(obj.user, "applied_custom", None)
        if not applied or not getattr(applied, "frame_item", None):
            return None
        item: Item = applied.frame_item
        if getattr(item, "file_url", None):
            return item.file_url
        if getattr(item, "file", None):
            return self._abs(req, item.file)
        return None

    def get_frame_item_id(self, obj):
        applied = getattr(obj.user, "applied_custom", None)
        return applied.frame_item_id if applied else None

    def get_header_item_id(self, obj):
        applied = getattr(obj.user, "applied_custom", None)
        return applied.header_item_id if applied else None


# ===== Прогресс =====

class MyProgressSerializer(serializers.ModelSerializer):
    xp = serializers.IntegerField(read_only=True)
    level = serializers.IntegerField(read_only=True)
    max_level = serializers.IntegerField(read_only=True)
    next_level_total_xp = serializers.IntegerField(read_only=True, source="next_level_xp")
    need_for_next = serializers.IntegerField(read_only=True)
    progress = serializers.FloatField(read_only=True)

    class Meta:
        model = Profile
        fields = ("xp", "level", "max_level", "next_level_total_xp", "need_for_next", "progress")


# ===== Аниме-списки =====

class MaterialMiniSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="kodik_id", read_only=True)

    class Meta:
        model = Material
        fields = ("id", "kodik_id", "slug", "title", "poster_url", "updated_at")


class UserAnimeListSerializer(serializers.ModelSerializer):
    material = MaterialMiniSerializer(read_only=True)
    material_slug = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Material.objects.all(),
        write_only=True,
        required=True,
        source="material",
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = UserAnimeList
        fields = (
            "id",
            "material",
            "material_slug",
            "status",
            "status_display",
            "created_at",
            "updated_at",
        )

class AvatarCompactSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    avatar_path = serializers.CharField(allow_null=True)
    frame_path = serializers.CharField(allow_null=True)
    avatar_ver = serializers.CharField(allow_null=True)

    @staticmethod
    def build_from(profile: Profile, applied: AppliedCustomization | None):
        """
        Возвращаем относительные пути (например, /media/...) и версию,
        чтобы фронт добавлял ?v=... для пробития кэша.
        """
        user = profile.user
        # 1) аватар
        avatar_path = None
        if applied and getattr(applied, "avatar_item", None):
            item = applied.avatar_item
            if getattr(item, "file_url", None):
                avatar_path = item.file_url  # может быть абсолютный — фронт нормализует
            elif getattr(item, "file", None) and getattr(item.file, "url", None):
                avatar_path = item.file.url
        elif profile.avatar and getattr(profile.avatar, "url", None):
            avatar_path = profile.avatar.url

        # 2) рамка
        frame_path = None
        if applied and getattr(applied, "frame_item", None):
            item = applied.frame_item
            if getattr(item, "file_url", None):
                frame_path = item.file_url
            elif getattr(item, "file", None) and getattr(item.file, "url", None):
                frame_path = item.file.url

        # 3) версия (максимум из обновлений профиля/апплаев)
        ver_sources = [profile.updated_at]
        if applied and getattr(applied, "updated_at", None):
            ver_sources.append(applied.updated_at)
        avatar_ver = str(max(dt for dt in ver_sources if dt).timestamp()) if ver_sources else None

        return {
            "id": user.id,
            "username": user.username,
            "avatar_path": avatar_path,
            "frame_path": frame_path,
            "avatar_ver": avatar_ver,
        }
