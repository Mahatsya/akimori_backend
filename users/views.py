from rest_framework import generics, permissions, decorators, viewsets, status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser

from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db import transaction
from django.core.exceptions import ValidationError

from .serializers import (
    UserPublicSerializer,
    ProfilePublicSerializer,
    MyProgressSerializer,
    UserAnimeListSerializer,
    AvatarMediaSerializer,
    AvatarCompactSerializer,
)
from .models import Profile, UserAnimeList, AnimeStatus, AvatarMedia
from kodik.models import Material
from customitem.models import AppliedCustomization

from django.utils.http import http_date
from hashlib import sha1

UserModel = get_user_model()

# ===== /api/auth/me/ =====
class MeView(generics.RetrieveAPIView):
    serializer_class = UserPublicSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        return self.request.user

# ===== /api/users/<username>/profile/ =====
class PublicProfileView(generics.RetrieveAPIView):
    serializer_class = ProfilePublicSerializer
    permission_classes = [permissions.AllowAny]
    lookup_url_kwarg = "username"

    def get_object(self):
        username = self.kwargs.get(self.lookup_url_kwarg)
        user = get_object_or_404(UserModel, username=username)
        profile, _ = Profile.objects.get_or_create(user=user)
        return profile

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

# ===== /api/users/me/progress/ =====
class MyProgressView(generics.RetrieveAPIView):
    serializer_class = MyProgressSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

# ===== /api/users/me/add_xp/ =====
class AddXPView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        amount = request.data.get("amount")
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return Response({"detail": "amount must be integer"}, status=http_status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({"detail": "amount must be > 0"}, status=http_status.HTTP_400_BAD_REQUEST)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        before = profile.level
        profile.add_xp(amount)
        after = profile.level

        ser = MyProgressSerializer(profile)
        return Response({"added": amount, "leveled_up": after > before, "data": ser.data}, status=http_status.HTTP_200_OK)

# ===== /api/users/me/anime/… =====
class MyAnimeListViewSet(viewsets.ModelViewSet):
    serializer_class = UserAnimeListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = (
            UserAnimeList.objects
            .filter(user=self.request.user)
            .select_related("material")
            .order_by("-updated_at")
        )
        status_param = self.request.query_params.get("status")
        search = self.request.query_params.get("search")
        if status_param:
            qs = qs.filter(status=status_param)
        if search:
            qs = qs.filter(
                Q(material__title__icontains=search) |
                Q(material__slug__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @decorators.action(detail=False, methods=["post"])
    def upsert_by_slug(self, request):
        material_slug = request.data.get("material_slug")
        status_value = request.data.get("status")
        if not material_slug or status_value not in dict(AnimeStatus.choices):
            return Response({"detail": "material_slug и корректный status обязательны"},
                            status=http_status.HTTP_400_BAD_REQUEST)
        try:
            material = Material.objects.get(slug=material_slug)
        except Material.DoesNotExist:
            return Response({"detail": "Материал не найден"}, status=http_status.HTTP_404_NOT_FOUND)

        obj, created = UserAnimeList.objects.get_or_create(
            user=request.user, material=material,
            defaults={"status": status_value},
        )
        if not created and obj.status != status_value:
            obj.status = status_value
            obj.save(update_fields=["status", "updated_at"])

        ser = self.get_serializer(obj)
        return Response(ser.data, status=http_status.HTTP_200_OK)

# ---- Пагинация ----
class PublicListPagination(PageNumberPagination):
    page_query_param = "page"
    page_size_query_param = "page_size"
    page_size = 24
    max_page_size = 60

# ===== /api/users/<username>/anime/ (публично) =====
class PublicUserAnimeListView(generics.ListAPIView):
    serializer_class = UserAnimeListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = PublicListPagination

    STATUS_ALIASES = {
        "watching": AnimeStatus.WATCHING,
        "смотрю": AnimeStatus.WATCHING,
        "planned": AnimeStatus.PLANNED,
        "plan": AnimeStatus.PLANNED,
        "запланировано": AnimeStatus.PLANNED,
        "буду смотреть": AnimeStatus.PLANNED,
        "completed": AnimeStatus.COMPLETED,
        "завершено": AnimeStatus.COMPLETED,
        "on_hold": AnimeStatus.ON_HOLD,
        "hold": AnimeStatus.ON_HOLD,
        "отложено": AnimeStatus.ON_HOLD,
        "dropped": AnimeStatus.DROPPED,
        "drop": AnimeStatus.DROPPED,
        "брошено": AnimeStatus.DROPPED,
    }

    def get_queryset(self):
        username = self.kwargs.get("username")
        user = get_object_or_404(UserModel, username=username)
        qs = (
            UserAnimeList.objects
            .filter(user=user)
            .select_related("material")
            .order_by("-updated_at")
        )
        status_param = self.request.query_params.get("status")
        search = self.request.query_params.get("search")
        if status_param:
            key = str(status_param).strip().lower()
            code = self.STATUS_ALIASES.get(key, key)
            qs = qs.filter(status=code)
        if search:
            qs = qs.filter(
                Q(material__title__icontains=search) |
                Q(material__slug__icontains=search)
            )
        return qs

# ====== НОВОЕ: Настройки профиля, аватары (история/загрузка/выбор) ======

class MyProfileSettingsView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/users/me/profile/settings/   -> профиль + applied + история аватаров
    PATCH /api/users/me/profile/settings/   -> {display_name?, bio?}
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    # GET возвращает расширенную структуру
    def get(self, request, *args, **kwargs):
        profile = self.get_object()
        applied, _ = AppliedCustomization.objects.get_or_create(user=request.user)
        history_qs = AvatarMedia.objects.filter(user=request.user).order_by("-created_at")[:20]
        history = AvatarMediaSerializer(history_qs, many=True, context={"request": request}).data
        return Response({
            "profile": ProfilePublicSerializer(profile, context={"request": request}).data,
            "applied": {
                "avatar_item_id": applied.avatar_item_id,
                "frame_item_id": applied.frame_item_id,
                "header_item_id": applied.header_item_id,
            },
            "avatars": {"history": history},
        })

    # PATCH меняет только display_name/bio (username НЕ трогаем)
    def patch(self, request, *args, **kwargs):
        profile = self.get_object()
        display_name = request.data.get("display_name", None)
        bio = request.data.get("bio", None)

        changed = False
        if isinstance(display_name, str):
            value = display_name.strip()
            if value != profile.display_name:
                profile.display_name = value
                changed = True
        if isinstance(bio, str) and bio != profile.bio:
            profile.bio = bio
            changed = True

        if changed:
            profile.save(update_fields=["display_name", "bio", "updated_at"])

        return Response({"profile": ProfilePublicSerializer(profile, context={"request": request}).data})

class AvatarUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "file is required (jpg/png/webp)"},
                            status=http_status.HTTP_400_BAD_REQUEST)

        media = AvatarMedia(user=request.user, file=file)
        try:
            media.full_clean()
        except ValidationError as e:
            return Response({"detail": e.messages}, status=http_status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"detail": "Upload error"}, status=http_status.HTTP_400_BAD_REQUEST)

        media.save()

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.avatar = media.file
        profile.save(update_fields=["avatar", "updated_at"])

        applied, _ = AppliedCustomization.objects.get_or_create(user=request.user)
        if applied.avatar_item_id:
            applied.avatar_item = None
            applied.save(update_fields=["avatar_item", "updated_at"])

        return Response(
            AvatarMediaSerializer(media, context={"request": request}).data,
            status=http_status.HTTP_201_CREATED
        )


class AvatarSelectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        media_id = request.data.get("media_id")
        media = get_object_or_404(AvatarMedia, id=media_id, user=request.user)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.avatar = media.file
        profile.save(update_fields=["avatar","updated_at"])

        applied, _ = AppliedCustomization.objects.get_or_create(user=request.user)
        if applied.avatar_item_id:
            applied.avatar_item = None
            applied.save(update_fields=["avatar_item","updated_at"])

        prof = ProfilePublicSerializer(profile, context={"request": request}).data
        return Response({"ok": True, "avatar_url": prof["avatar_url"]})


class UserAvatarView(APIView):
    """
    GET /api/users/<int:user_id>/avatar
    Публичный компакт: username, avatar_path, frame_path, avatar_ver
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, user_id: int):
        user = get_object_or_404(UserModel, pk=user_id, is_active=True)
        profile, _ = Profile.objects.get_or_create(user=user)
        applied = AppliedCustomization.objects.filter(user=user).select_related(
            "avatar_item", "frame_item"
        ).first()

        payload = AvatarCompactSerializer.build_from(profile, applied)

        # Лёгкие кэш-заголовки (ETag/Last-Modified)
        ver = payload.get("avatar_ver") or ""
        etag = sha1(f"{user.id}:{ver}".encode("utf-8")).hexdigest()

        resp = Response(payload, status=http_status.HTTP_200_OK)
        resp["Cache-Control"] = "public, max-age=60"          # 1 мин
        resp["ETag"] = etag
        if profile.updated_at:
            resp["Last-Modified"] = http_date(profile.updated_at.timestamp())
        return resp


class MeAvatarView(APIView):
    """
    GET /api/users/me/avatar
    Тот же формат, но для текущего пользователя (нужна авторизация)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        profile, _ = Profile.objects.get_or_create(user=user)
        applied = AppliedCustomization.objects.filter(user=user).select_related(
            "avatar_item", "frame_item"
        ).first()
        payload = AvatarCompactSerializer.build_from(profile, applied)

        ver = payload.get("avatar_ver") or ""
        etag = sha1(f"{user.id}:{ver}".encode("utf-8")).hexdigest()

        resp = Response(payload, status=http_status.HTTP_200_OK)
        resp["Cache-Control"] = "private, max-age=60"
        resp["ETag"] = etag
        if profile.updated_at:
            resp["Last-Modified"] = http_date(profile.updated_at.timestamp())
        return resp