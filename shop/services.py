from django.db import transaction as db_tx
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from economy.models import Currency
from economy.services import ensure_user_wallets, withdraw, InsufficientFunds
from customitem.models import Item, Inventory, InventorySource
from .models import Offer, Purchase

User = get_user_model()


class ShopError(Exception):
    pass


@db_tx.atomic
def buy_item_for_user(user: User, item: Item, *, idempotency_key: str | None = None) -> Purchase:
    """
    Покупка предмета за AKI:
      - нельзя купить, если уже в инвентаре;
      - проверка лимитов/актива;
      - списание AKI (withdraw);
      - запись Purchase + добавление в Inventory;
      - инкремент счетчика продаж.
    """
    # Нельзя покупать дубликаты (по умолчанию)
    if Inventory.objects.filter(user=user, item=item).exists():
        raise ShopError("Предмет уже в инвентаре.")

    # Проверка оффера/продажи
    offer = getattr(item, "offer", None)
    price = (offer.current_price if (offer and offer.is_selling_now()) else item.price_aki)
    if price <= 0 or not item.can_sell_now:
        raise ShopError("Товар сейчас не продаётся.")

    # Списание AKI
    rub_wallet, aki_wallet = ensure_user_wallets(user)
    try:
        tx = withdraw(aki_wallet, price, description=f"Покупка предмета {item.slug}", idempotency_key=idempotency_key)
    except InsufficientFunds:
        raise ShopError("Недостаточно AkiCoin.")
    except Exception as e:
        raise ShopError(f"Ошибка списания: {e}")

    # Запись покупки
    purchase = Purchase.objects.create(
        user=user,
        item=item,
        price_aki=price,
        transaction=tx,
    )

    # Добавление в инвентарь
    Inventory.objects.create(
        user=user,
        item=item,
        source=InventorySource.PURCHASE,
    )

    # Лимиты
    if item.limited_total is not None:
        item.limited_sold = (item.limited_sold or 0) + 1
        item.save(update_fields=["limited_sold", "updated_at"])

    return purchase
