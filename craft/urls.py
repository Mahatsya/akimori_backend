from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HeaderMaterialContentViewSet

router = DefaultRouter()
router.register(
    r"craft/header-materials",
    HeaderMaterialContentViewSet,
    basename="craft-header-materials",
)

urlpatterns = [
    path("", include(router.urls)),
]
