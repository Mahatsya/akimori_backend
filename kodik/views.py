# coding: utf-8
from __future__ import annotations

import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.db import models, transaction
from django.db.models import (
    F,
    Value,
    FloatField,
    Prefetch,
    Q,
    Count,
    BooleanField,
    DateField,
    Case,
    When,
    Avg,
    IntegerField,
)
from django.db.models.functions import Coalesce, ExtractYear
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from rest_framework import status, viewsets, mixins, permissions
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from .models import (
    Material,
    MaterialVersion,
    Season,
    Credit,
    Genre,
    AkiUserRating,
    MaterialComment,
    MaterialExtra,
    MaterialCommentLike,
)
from .serializers import (
    MaterialListSerializer,
    MaterialDetailSerializer,
    AkiUserRatingSerializer,
    AkiRatingSummarySerializer,
    MaterialCommentSerializer,
    MaterialCommentCreateSerializer,
)
from .filters import MaterialFilter


# ------------------------- Утилиты -------------------------


def _client_ip_from_request(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "0.0.0.0")


class SortAliasOrderingFilter(OrderingFilter):
    """Поддержка ?sort=... в дополнение к стандартному ?ordering=..."""

    ordering_param = "ordering"

    def get_ordering(self, request, queryset, view):
        # если явно передан ?ordering= - используем стандартный механизм
        if self.ordering_param in request.query_params:
            return super().get_ordering(request, queryset, view)

        sort = request.query_params.get("sort")
        if not sort:
            return self.get_default_ordering(view)

        fields = [f.strip() for f in sort.split(",") if f.strip()]
        return self.remove_invalid_fields(queryset, fields, view, request) or self.get_default_ordering(view)


# ------------------------- Внешний API Kodik -------------------------


class KodikVideoLinkView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        public = settings.KODIK_PUBLIC_KEY
        private = settings.KODIK_PRIVATE_KEY
        api_url = settings.KODIK_VIDEO_LINKS_URL

        link = request.query_params.get("link", "").strip()
        if not link:
            return Response({"detail": "link required"}, status=status.HTTP_400_BAD_REQUEST)
        if not public or not private or not api_url:
            return Response({"detail": "KODIK keys are not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if "://" not in link:
            link = "https:" + link
        u = urlparse(link)
        if u.hostname not in {"kodik.info", "kodik.cc", "kodik.biz"}:
            return Response({"detail": "unsupported host"}, status=status.HTTP_400_BAD_REQUEST)

        ip = _client_ip_from_request(request)
        hours = max(1, min(10, int(getattr(settings, "KODIK_DEADLINE_HOURS", 6))))
        deadline_dt = datetime.now(timezone.utc) + timedelta(hours=hours)
        deadline = deadline_dt.strftime("%Y%m%d%H")

        msg = f"{link}:{ip}:{deadline}".encode("utf-8")
        digest = hmac.new(private.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        params: Dict[str, Any] = {"link": link, "p": public, "ip": ip, "d": deadline, "s": digest}

        try:
            resp = requests.get(api_url, params=params, timeout=20)
            resp.raise_for_status()
            return Response(resp.json())
        except requests.HTTPError as e:
            body = e.response.text if e.response is not None else ""
            return Response(
                {"detail": f"http_error {getattr(e.response, 'status_code', '?')}", "body": body},
                status=502,
            )
        except Exception as e:
            return Response({"detail": f"request_failed: {e}"}, status=502)


# ------------------------- Пагинация -------------------------


class MaterialPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100


class CommentsPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


# ------------------------- Каталог -------------------------


ALLOWED_ANIME_TYPES = {"anime", "anime-serial"}


def _split_csv(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x and x.strip()]


def restrict_catalog(qs, request=None):
    # TYPE
    if request:
        raw_type = request.query_params.get("type")
        types = {t.lower() for t in _split_csv(raw_type)} if raw_type else set()
        if types:
            qs = qs.filter(type__in=types)
        else:
            qs = qs.filter(type__in=ALLOWED_ANIME_TYPES)
    else:
        qs = qs.filter(type__in=ALLOWED_ANIME_TYPES)

    # COUNTRY
    if request:
        raw_c = request.query_params.get("countries") or request.query_params.get("country")
        if raw_c:
            if raw_c.strip().lower() == "any":
                return qs.distinct()
            codes = {c.upper() for c in _split_csv(raw_c)}
            if codes:
                return qs.filter(production_countries__code__in=codes).distinct()

    return qs.distinct()


@method_decorator(cache_page(60), name="list")
@method_decorator(cache_page(60), name="retrieve")
class MaterialViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/kodik/materials/
    /api/kodik/materials/<slug>/
    /api/kodik/materials/genres/
    /api/kodik/materials/facets/
    """

    permission_classes = [AllowAny]
    serializer_class = MaterialListSerializer
    pagination_class = MaterialPagination
    filterset_class = MaterialFilter
    filter_backends = [DjangoFilterBackend, SortAliasOrderingFilter]

    # тут перечисляем поля, по которым можно сортировать ?ordering=
    ordering_fields = (
        "primary_date",
        "shiki",
        "aki_rating",
        "aki_votes",
        "views_count",
        "next_episode_at",  # alias на extra__next_episode_at
        "aired_at",         # ✨ alias на extra__aired_at
    )
    ordering = ["-primary_date", "-pk"]

    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    lookup_value_regex = r"[-a-z0-9]+"

    def _annotate_common(self, qs):
        primary_date = Coalesce(
            F("extra__aired_at"),
            F("extra__premiere_world"),
            F("extra__released_at"),
            output_field=DateField(),
        )
        primary_source = Case(
            When(extra__aired_at__isnull=False, then=Value("aired_at")),
            When(extra__premiere_world__isnull=False, then=Value("premiere_world")),
            When(extra__released_at__isnull=False, then=Value("released_at")),
            default=Value("none"),
            output_field=models.CharField(),
        )
        has_date = Case(
            When(
                Q(extra__aired_at__isnull=False)
                | Q(extra__premiere_world__isnull=False)
                | Q(extra__released_at__isnull=False),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        )
        return qs.annotate(
            shiki=Coalesce(F("extra__shikimori_rating"), Value(-1.0), output_field=FloatField()),
            primary_date=primary_date,
            primary_source=primary_source,
            has_date=has_date,
            year_effective=ExtractYear(primary_date),
            aki_rating=F("extra__aki_rating"),
            aki_votes=F("extra__aki_votes"),
            views_count=Coalesce(F("extra__views_count"), Value(0), output_field=IntegerField()),
            next_episode_at=F("extra__next_episode_at"),  # чтобы сортировать/фильтровать по next_episode_at
            aired_at=F("extra__aired_at"),                # ✨ чтобы сортировать/фильтровать по aired_at
        )

    def _apply_default_ordering(self, qs):
        # дефолтная сортировка: сначала по дате релиза (nulls_last), потом по id
        return qs.order_by(F("primary_date").desc(nulls_last=True), F("pk").desc(nulls_last=True))

    def get_queryset(self):
        if self.action == "retrieve":
            qs = (
                Material.objects.select_related("extra")
                .prefetch_related(
                    "genres",
                    "studios",
                    "production_countries",
                    "license_owners",
                    "mdl_tags",
                    Prefetch(
                        "credits",
                        queryset=Credit.objects.select_related("person").order_by("role", "order", "id"),
                    ),
                    Prefetch(
                        "versions",
                        queryset=(
                            MaterialVersion.objects.select_related("translation")
                            .only("id", "material_id", "translation_id", "movie_link")
                            .prefetch_related(
                                Prefetch(
                                    "seasons",
                                    queryset=Season.objects.only("id", "version_id", "number", "link").prefetch_related(
                                        "episodes"
                                    ),
                                )
                            )
                        ),
                    ),
                )
            )
            qs = self._annotate_common(qs)
            qs = restrict_catalog(qs, self.request)
            return qs

        # LIST
        qs = (
            Material.objects.select_related("extra")
            .only(
                "kodik_id",
                "slug",
                "type",
                "title",
                "title_orig",
                "poster_url",
                "year",
                "extra__shikimori_rating",
                "extra__aired_at",
                "extra__premiere_world",
                "extra__released_at",
            )
            .prefetch_related("genres", "studios", "production_countries")
        )
        qs = self._annotate_common(qs)
        qs = restrict_catalog(qs, self.request)

        include_nodate = self.request.query_params.get("include_nodate") in ("1", "true", "yes")
        if not include_nodate:
            qs = qs.filter(has_date=True)

        qs = self.filter_queryset(qs)
        qs = self._apply_default_ordering(qs)
        return qs.distinct()

    def get_serializer_class(self):
        return MaterialDetailSerializer if self.action == "retrieve" else MaterialListSerializer

    # -------- жанры/фасеты --------

    @method_decorator(cache_page(300))
    @action(detail=False, methods=["get"], url_path="genres", permission_classes=[AllowAny])
    def genres(self, request):
        qs = Genre.objects.all()
        src = request.query_params.get("source")
        q = request.query_params.get("q")
        if src:
            qs = qs.filter(source__iexact=src)
        if q:
            qs = qs.filter(name__icontains=q)
        data = [{"id": g.id, "slug": g.slug, "name": g.name, "source": g.source} for g in qs.order_by("name")]
        return Response(data)

    @method_decorator(cache_page(300))
    @action(detail=False, methods=["get"], url_path="facets", permission_classes=[AllowAny])
    def facets(self, request):
        base = Material.objects.all()
        base = self._annotate_common(base)
        base = restrict_catalog(base, request)

        include_nodate = request.query_params.get("include_nodate") in ("1", "true", "yes")
        if not include_nodate:
            base = base.filter(has_date=True)

        base = self.filter_queryset(base)

        genres = (
            base.values("genres__id", "genres__slug", "genres__name", "genres__source")
            .annotate(count=Count("pk"))
            .order_by("genres__name")
        )
        countries = (
            base.values("production_countries__code", "production_countries__name")
            .annotate(count=Count("pk"))
            .order_by("production_countries__name")
        )
        studios = (
            base.values("studios__id", "studios__name").annotate(count=Count("pk")).order_by("studios__name")
        )

        return Response(
            {
                "genres": [
                    {
                        "id": g["genres__id"],
                        "slug": g["genres__slug"],
                        "name": g["genres__name"],
                        "source": g["genres__source"],
                        "count": g["count"],
                    }
                    for g in genres
                    if g["genres__id"] is not None
                ],
                "countries": [
                    {
                        "code": c["production_countries__code"],
                        "name": c["production_countries__name"],
                        "count": c["count"],
                    }
                    for c in countries
                    if c["production_countries__code"] is not None
                ],
                "studios": [
                    {"id": s["studios__id"], "name": s["studios__name"], "count": s["count"]}
                    for s in studios
                    if s["studios__id"] is not None
                ],
            }
        )

    # ─────────────────────────────
    # 🔢 инкремент views_count
    # POST /api/kodik/materials/<slug>/view/
    # ─────────────────────────────
    @action(detail=True, methods=["post"], url_path="view")
    def add_view(self, request: Request, slug: str | None = None):
        material: Material = self.get_object()

        extra, _ = MaterialExtra.objects.get_or_create(material=material)
        MaterialExtra.objects.filter(pk=extra.pk).update(views_count=F("views_count") + 1)
        extra.refresh_from_db(fields=["views_count"])

        return Response({"views_count": extra.views_count})


# ────────────────────────────────────────────────────────────────
# 🔐 permissions
# ────────────────────────────────────────────────────────────────


class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        u = request.user
        if not u or not u.is_authenticated:
            return False
        return getattr(obj, "user_id", None) == u.id or u.is_staff


# ────────────────────────────────────────────────────────────────
# ⭐ AKI РЕЙТИНГИ
# ────────────────────────────────────────────────────────────────


class AkiUserRatingViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    POST   /api/aki/ratings/
    GET    /api/aki/ratings/me/?material=<id>
    DELETE /api/aki/ratings/clear/?material=<id>
    GET    /api/aki/ratings/summary/<id>/
    """

    queryset = AkiUserRating.objects.select_related("material", "user").all()
    serializer_class = AkiUserRatingSerializer

    def get_permissions(self):
        if self.action in ("create", "me", "clear"):
            return [IsAuthenticated()]
        return [permissions.IsAuthenticatedOrReadOnly()]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request: Request):
        material_id = request.query_params.get("material")
        if not material_id:
            return Response({"detail": "material is required"}, status=400)
        obj = AkiUserRating.objects.filter(material_id=material_id, user=request.user).first()
        if not obj:
            return Response({"detail": "not rated"}, status=404)
        return Response(AkiUserRatingSerializer(obj).data)

    @action(detail=False, methods=["delete"], url_path="clear")
    def clear(self, request: Request):
        material_id = request.query_params.get("material")
        if not material_id:
            return Response({"detail": "material is required"}, status=400)
        AkiUserRating.objects.filter(material_id=material_id, user=request.user).delete()
        extra, _ = MaterialExtra.objects.get_or_create(material_id=material_id)
        return Response({"avg": extra.aki_rating, "votes": extra.aki_votes or 0})

    @transaction.atomic
    def create(self, request: Request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication credentials were not provided."},
                status=401,
            )

        ser = self.get_serializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)

        obj = ser.save()

        agg = AkiUserRating.objects.filter(material=obj.material).aggregate(
            avg=Avg("score"),
            votes=Count("id"),
        )
        avg = float(agg["avg"]) if agg["avg"] is not None else None
        votes = int(agg["votes"] or 0)

        extra, _ = MaterialExtra.objects.get_or_create(material=obj.material)
        extra.aki_rating = avg
        extra.aki_votes = votes
        extra.save(update_fields=["aki_rating", "aki_votes"])

        data = AkiUserRatingSerializer(obj).data
        data.update({"avg": avg, "votes": votes})
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=["get"], url_path=r"summary/(?P<material_id>[^/]+)")
    def summary(self, request: Request, material_id: str):
        extra, _ = MaterialExtra.objects.get_or_create(material_id=material_id)
        data = {
            "material": material_id,
            "aki_rating": extra.aki_rating,
            "aki_votes": extra.aki_votes or 0,
        }
        return Response(AkiRatingSummarySerializer(data).data)


# ────────────────────────────────────────────────────────────────
# 💬 КОММЕНТАРИИ
# ────────────────────────────────────────────────────────────────


class MaterialCommentViewSet(viewsets.ModelViewSet):
    """
    GET    /api/aki/comments/?material=<id>&parent=<id?>
    POST   /api/aki/comments/
    PATCH  /api/aki/comments/{id}/
    DELETE /api/aki/comments/{id}/

    POST /api/aki/comments/{id}/like/
    POST /api/aki/comments/{id}/unlike/
    POST /api/aki/comments/{id}/pin/
    POST /api/aki/comments/{id}/unpin/
    """

    queryset = MaterialComment.objects.select_related("user").all()
    permission_classes = [IsAuthorOrReadOnly]
    pagination_class = CommentsPagination

    def get_permissions(self):
        if self.action in ("create", "like", "unlike"):
            return [IsAuthenticated()]
        if self.action in ("pin", "unpin"):
            return [IsAdminUser()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "create":
            return MaterialCommentCreateSerializer
        return MaterialCommentSerializer

    def list(self, request: Request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            ser = self.get_serializer(page, many=True)
            return self.get_paginated_response(ser.data)
        ser = self.get_serializer(queryset, many=True)
        return Response({"results": ser.data, "count": queryset.count()})

    def get_queryset(self):
        qs = super().get_queryset()
        material_id = self.request.query_params.get("material")
        parent = self.request.query_params.get("parent")

        qs = qs.filter(is_deleted=False, status="published")

        if material_id:
            qs = qs.filter(material_id=material_id)

        if parent:
            qs = qs.filter(parent_id=parent)
        else:
            qs = qs.filter(parent__isnull=True)

        return qs.order_by("-is_pinned", "-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance: MaterialComment):
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted", "updated_at"])

    @action(detail=True, methods=["post"])
    def like(self, request: Request, pk: str | None = None):
        obj = self.get_object()
        _, created = MaterialCommentLike.objects.get_or_create(comment=obj, user=request.user)
        return Response({"ok": True, "created": created})

    @action(detail=True, methods=["post"])
    def unlike(self, request: Request, pk: str | None = None):
        obj = self.get_object()
        MaterialCommentLike.objects.filter(comment=obj, user=request.user).delete()
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def pin(self, request: Request, pk: str | None = None):
        obj = self.get_object()
        obj.is_pinned = True
        obj.save(update_fields=["is_pinned"])
        return Response({"pinned": True})

    @action(detail=True, methods=["post"])
    def unpin(self, request: Request, pk: str | None = None):
        obj = self.get_object()
        obj.is_pinned = False
        obj.save(update_fields=["is_pinned"])
        return Response({"pinned": False})
