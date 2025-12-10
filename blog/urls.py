from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import PostViewSet, CategoryViewSet, TagViewSet

router = SimpleRouter()
router.register(r"posts", PostViewSet, basename="blog-posts")
router.register(r"categories", CategoryViewSet, basename="blog-categories")
router.register(r"tags", TagViewSet, basename="blog-tags")

urlpatterns = [
    path("blog/", include(router.urls)),
]
