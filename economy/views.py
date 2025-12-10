# views.py
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from rest_framework import permissions, viewsets, mixins, decorators, status, serializers
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Wallet, Transaction, Currency
from .serializers import WalletSerializer, TransactionSerializer
from .services import ensure_user_wallets, deposit, withdraw, transfer, InsufficientFunds


User = get_user_model()


class MyWalletViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/economy/wallets/me/ — список кошельков текущего пользователя (RUB, AKI)
    """
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        ensure_user_wallets(self.request.user)  # лениво создаём, если нет
        return Wallet.objects.filter(user=self.request.user).order_by("currency")


class MyTransactionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/economy/transactions/me/?currency=AKI — журнал по всем моим кошелькам или по валюте
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        currency = self.request.query_params.get("currency")
        wallets = Wallet.objects.filter(user=self.request.user)
        if currency and currency in Currency.values:
            wallets = wallets.filter(currency=currency)
        return Transaction.objects.filter(wallet__in=wallets).select_related("wallet")


# ===== DEMO-сериализаторы для входных данных =====

class AmountSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1)


class TransferAKISerializer(serializers.Serializer):
    to_user_id = serializers.IntegerField(min_value=1)
    amount = serializers.IntegerField(min_value=1)


# Примеры простых действий для теста (можно отключить в проде)
class DemoActionsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @decorators.action(detail=False, methods=["post"], url_path="deposit-aki")
    def deposit_aki(self, request):
        """
        DEMO: пополнить AKI на указанную сумму (целые коины).
        body: { "amount": 100 }
        """
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        wallet = Wallet.objects.get(user=request.user, currency=Currency.AKI)
        try:
            tx = deposit(wallet, amount, description="Demo deposit AKI")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message)

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

        wallet = Wallet.objects.get(user=request.user, currency=Currency.RUB)
        try:
            tx = deposit(wallet, amount, description="Demo deposit RUB")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message)

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

        to_user = get_object_or_404(User, id=to_user_id)
        from_w = Wallet.objects.get(user=request.user, currency=Currency.AKI)
        to_w, _ = Wallet.objects.get_or_create(user=to_user, currency=Currency.AKI)

        try:
            res = transfer(from_w, to_w, amount, description="Demo transfer AKI")
        except InsufficientFunds:
            return Response({"detail": "Недостаточно средств"}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message)

        data = {
            "out": TransactionSerializer(res.out_tx).data,
            "in": TransactionSerializer(res.in_tx).data,
        }
        return Response(data, status=status.HTTP_201_CREATED)
