# economy/views.py
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.conf import settings

from rest_framework import (
    permissions,
    viewsets,
    mixins,
    decorators,
    status,
    serializers,
)
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Wallet, Transaction, Currency
from .serializers import WalletSerializer, TransactionSerializer
from .services import ensure_user_wallets, deposit, withdraw, transfer, InsufficientFunds


User = get_user_model()


class MyWalletViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/economy/wallets/me/ — список кошельков текущего пользователя (RUB, AKI).
    Безопасный read-only эндпоинт.
    """
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Лениво создаём кошельки только для текущего пользователя.
        ensure_user_wallets(self.request.user)
        return (
            Wallet.objects.filter(user=self.request.user)
            .order_by("currency")
        )


class MyTransactionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/economy/transactions/me/?currency=AKI —
    журнал по всем моим кошелькам или по конкретной валюте.
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        currency = self.request.query_params.get("currency")
        wallets = Wallet.objects.filter(user=self.request.user)
        if currency and currency in Currency.values:
            wallets = wallets.filter(currency=currency)
        return (
            Transaction.objects
            .filter(wallet__in=wallets)
            .select_related("wallet")
            .order_by("-created_at")
        )


# ===== Сериализаторы для входных данных =====


class AmountSerializer(serializers.Serializer):
    # Заодно ограничим максимально допустимую сумму, чтобы не улетать в абсурдные числа
    amount = serializers.IntegerField(min_value=1, max_value=1_000_000_000)


class TransferAKISerializer(serializers.Serializer):
    to_user_id = serializers.IntegerField(min_value=1)
    amount = serializers.IntegerField(min_value=1, max_value=1_000_000_000)


# ===== DEMO-эндпоинты только для разработки / админов =====

class IsDemoEconomyAllowed(permissions.BasePermission):
    """
    Разрешаем доступ к DEMO-действиям только если:
    - DEBUG = True ИЛИ явно включён флаг ECONOMY_DEMO_ENABLED;
    - пользователь — админ (is_staff).
    """

    def has_permission(self, request, view):
        demo_enabled = getattr(settings, "ECONOMY_DEMO_ENABLED", False)
        if not (settings.DEBUG or demo_enabled):
            return False
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(request.user.is_staff)


class DemoActionsViewSet(viewsets.ViewSet):
    """
    DEMO-набор действий для локальной разработки и отладки.

    ⚠ В продакшене либо НЕ подключается вообще (см. urls.py),
      либо доступен только админам.
    """

    permission_classes = [IsDemoEconomyAllowed]

    @decorators.action(detail=False, methods=["post"], url_path="deposit-aki")
    def deposit_aki(self, request):
        """
        DEMO: пополнить AKI на указанную сумму (целые коины).
        body: { "amount": 100 }
        """
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        # Гарантируем наличие кошельков только для текущего пользователя
        ensure_user_wallets(request.user)
        wallet = Wallet.objects.get(user=request.user, currency=Currency.AKI)

        try:
            tx = deposit(wallet, amount, description="Demo deposit AKI")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages if hasattr(e, "messages") else str(e))

        return Response(TransactionSerializer(tx).data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=False, methods=["post"], url_path="deposit-rub")
    def deposit_rub(self, request):
        """
        DEMO: пополнить RUB на указанную сумму в копейках.
        body: { "amount": 19900 }  # 199.00 ₽
        """
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        ensure_user_wallets(request.user)
        wallet = Wallet.objects.get(user=request.user, currency=Currency.RUB)

        try:
            tx = deposit(wallet, amount, description="Demo deposit RUB")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages if hasattr(e, "messages") else str(e))

        return Response(TransactionSerializer(tx).data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=False, methods=["post"], url_path="transfer-aki")
    def transfer_aki(self, request):
        """
        DEMO: перевести AKI другому пользователю.
        body: { "to_user_id": 123, "amount": 50 }
        """
        serializer = TransferAKISerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        to_user_id = serializer.validated_data["to_user_id"]
        amount = serializer.validated_data["amount"]

        if to_user_id == request.user.id:
            raise serializers.ValidationError({"to_user_id": "Нельзя переводить самому себе"})

        to_user = get_object_or_404(User, id=to_user_id)

        ensure_user_wallets(request.user)
        ensure_user_wallets(to_user)

        from_w = Wallet.objects.get(user=request.user, currency=Currency.AKI)
        to_w = Wallet.objects.get(user=to_user, currency=Currency.AKI)

        try:
            res = transfer(from_w, to_w, amount, description="Demo transfer AKI")
        except InsufficientFunds:
            return Response({"detail": "Недостаточно средств"}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages if hasattr(e, "messages") else str(e))

        data = {
            "out": TransactionSerializer(res.out_tx).data,
            "in": TransactionSerializer(res.in_tx).data,
        }
        return Response(data, status=status.HTTP_201_CREATED)
