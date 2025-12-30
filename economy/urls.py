# economy/urls.py
from django.urls import path, include
from django.conf import settings
from rest_framework.routers import DefaultRouter

from .views import (
    MyWalletViewSet,
    MyTransactionViewSet,
    DemoActionsViewSet,
)

router = DefaultRouter()

# Основные безопасные эндпоинты — всегда доступны
router.register(r"economy/wallets/me", MyWalletViewSet, basename="my-wallets")
router.register(r"economy/transactions/me", MyTransactionViewSet, basename="my-tx")

# DEMO-эндпоинты:
# - в чистом проде НЕ подключаем
# - подключаем только если DEBUG=True или включён специальный флаг
if settings.DEBUG or getattr(settings, "ECONOMY_DEMO_ENABLED", False):
    router.register(r"economy/demo", DemoActionsViewSet, basename="economy-demo")

urlpatterns = [
    path("", include(router.urls)),
]
