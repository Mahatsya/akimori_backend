from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet, ThreadKindViewSet, TagViewSet,
    ThreadViewSet, ThreadAttachmentViewSet, CommentViewSet,
)
class OptionalSlashRouter(DefaultRouter):
    trailing_slash = '/?'  # <-- ключ

router = OptionalSlashRouter()
router.register(r"categories", CategoryViewSet, basename="forum-category")
router.register(r"kinds", ThreadKindViewSet, basename="forum-kind")
router.register(r"tags", TagViewSet, basename="forum-tag")
router.register(r"threads", ThreadViewSet, basename="forum-thread")
router.register(r"attachments", ThreadAttachmentViewSet, basename="forum-attachment")
router.register(r"comments", CommentViewSet, basename="forum-comment")

urlpatterns = [
    path("forum/", include(router.urls)),
]