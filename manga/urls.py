from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import MangaViewSet, TranslatorViewSet, ChapterViewSet

router = DefaultRouter()
router.register(r"manga", MangaViewSet, basename="manga")
router.register(r"translators", TranslatorViewSet, basename="translator")
router.register(r"chapters", ChapterViewSet, basename="chapter")

urlpatterns = [
    path("", include(router.urls)),
]
