# coding: utf-8
from __future__ import annotations

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    KodikVideoLinkView,
    MaterialViewSet,
    AkiUserRatingViewSet,
    MaterialCommentViewSet,
)

router = DefaultRouter()

# каталог
router.register(r"kodik/materials", MaterialViewSet, basename="kodik-materials")

# AKI рейтинги
router.register(r"aki/ratings", AkiUserRatingViewSet, basename="aki-ratings")

# комментарии
router.register(r"aki/comments", MaterialCommentViewSet, basename="aki-comments")

urlpatterns = [
    path("kodik/video-link/", KodikVideoLinkView.as_view(), name="kodik-video-link"),
    path("", include(router.urls)),
]
