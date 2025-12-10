from django.contrib import admin
from .models import Wallet, Transaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "currency",
        "balance",
        "balance_display_admin",
        "updated_at",
    )
    list_filter = ("currency",)
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user",)
    list_select_related = ("user",)
    readonly_fields = ("balance", "created_at", "updated_at")

    @admin.display(description="Balance display")
    def balance_display_admin(self, obj: Wallet):
        # Берём значение из @property, но так мы точно контролируем колонку
        return obj.balance_display


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "wallet", "tx_type", "amount", "created_at", "idempotency_key")
    list_filter = ("tx_type", "wallet__currency")
    search_fields = ("wallet__user__username", "idempotency_key")
    raw_id_fields = ("wallet", "related_tx")
    list_select_related = ("wallet", "wallet__user")
