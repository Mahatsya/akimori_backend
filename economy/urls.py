from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MyWalletViewSet, MyTransactionViewSet, DemoActionsViewSet

router = DefaultRouter()
router.register(r"economy/wallets/me", MyWalletViewSet, basename="my-wallets")
router.register(r"economy/transactions/me", MyTransactionViewSet, basename="my-tx")
router.register(r"economy/demo", DemoActionsViewSet, basename="economy-demo")

urlpatterns = [
    path("", include(router.urls)),
]
