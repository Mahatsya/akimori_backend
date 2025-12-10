from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import OfferViewSet, PurchaseView

app_name = "shop"

router = DefaultRouter()
router.register(r"shop/offers", OfferViewSet, basename="shop-offer")

urlpatterns = [
    path("", include(router.urls)),
    path("shop/purchase/", PurchaseView.as_view(), name="purchase"),
]
