# serializers.py
from rest_framework import serializers

from .models import Wallet, Transaction


class WalletSerializer(serializers.ModelSerializer):
    balance_display = serializers.CharField(read_only=True)

    class Meta:
        model = Wallet
        fields = ("id", "currency", "balance", "balance_display", "created_at", "updated_at")
        read_only_fields = ("id", "balance", "balance_display", "created_at", "updated_at")


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            "id",
            "wallet",
            "tx_type",
            "amount",
            "description",
            "related_tx",
            "idempotency_key",
            "created_at",
        )
        read_only_fields = fields  # журнал только для чтения
