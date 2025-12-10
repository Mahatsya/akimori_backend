from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ItemViewSet, MyInventoryViewSet, AppliedViewSet

router = DefaultRouter()
router.register(r"customitems", ItemViewSet, basename="custom-items")
router.register(r"customitems/me/inventory", MyInventoryViewSet, basename="my-inventory")

urlpatterns = [
    path("", include(router.urls)),
    path("customitems/me/applied/", AppliedViewSet.as_view({"get": "retrieve", "put": "update"})),
]
