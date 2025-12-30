from django.urls import path

from .views import (
    PromoValidateView,
    PromoRedeemView,
)

urlpatterns = [
    path("promo/validate/", PromoValidateView.as_view(), name="promo-validate"),
    path("promo/redeem/", PromoRedeemView.as_view(), name="promo-redeem"),
]
