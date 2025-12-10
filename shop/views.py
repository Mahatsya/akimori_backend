# shop/views.py
from django.db import transaction, models
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Offer, Purchase, PurchaseStatus
from customitem.models import Item, Inventory, InventorySource
from .serializers import OfferSerializer

# Экономика: используем готовые сервисы и типы
from economy.services import (
    ensure_user_wallets,
    withdraw,
    InsufficientFunds,
)
from economy.models import Currency  # для выбора кошелька (AKI)


class OfferViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/shop/offers/           — список
    GET /api/shop/offers/<id|slug>/ — детально (slug = item.slug)
    """
    queryset = Offer.objects.select_related("item")
    serializer_class = OfferSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "pk"  # get_object ниже умеет и id, и slug

    def get_object(self):
        lookup = self.kwargs.get(self.lookup_field)
        qs = self.get_queryset()
        # как id
        try:
            return qs.get(pk=int(lookup))
        except (TypeError, ValueError):
            pass
        # как slug предмета
        return qs.get(item__slug=lookup)


class PurchaseView(APIView):
    """
    POST /api/shop/purchase/
    Body: { item_slug?: string, offer_id?: number }

    Логика:
      - ищем оффер (по offer_id или по item_slug)
      - проверяем окно продаж/лимиты/дубликаты владения
      - списываем AKI с кошелька пользователя через economy.services.withdraw(...)
      - создаём Purchase и выдаём предмет в инвентарь
    Ответ 200: { ok, purchase_id, inventory_id, new_balance }
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        item_slug = request.data.get("item_slug")
        offer_id = request.data.get("offer_id")

        if not item_slug and not offer_id:
            return Response(
                {"detail": "Укажите item_slug или offer_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1) Находим оффер и предмет под блокировкой
        if offer_id:
            try:
                offer = (
                    Offer.objects.select_for_update()
                    .select_related("item")
                    .get(pk=offer_id)
                )
            except Offer.DoesNotExist:
                return Response(
                    {"detail": "Оффер не найден."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            try:
                offer = (
                    Offer.objects.select_for_update()
                    .select_related("item")
                    .get(item__slug=item_slug)
                )
            except Offer.DoesNotExist:
                return Response(
                    {"detail": "Оффер по этому слагу не найден."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        item: Item = Item.objects.select_for_update().get(pk=offer.item_id)

        # 2) Проверки доступности
        if not offer.is_selling_now():
            return Response(
                {"detail": "Продажи недоступны для этого предмета."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Inventory.objects.filter(user=request.user, item=item).exists():
            return Response(
                {"detail": "Вы уже владеете этим предметом."},
                status=status.HTTP_409_CONFLICT,
            )

        if item.limited_total is not None and item.limited_sold >= item.limited_total:
            return Response(
                {"detail": "Лимит продаж исчерпан."},
                status=status.HTTP_409_CONFLICT,
            )

        price = offer.current_price
        if price <= 0:
            return Response(
                {"detail": "Предмет недоступен для покупки."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3) Кошельки пользователя — гарантируем наличие и берём AKI
        _, aki_wallet = ensure_user_wallets(request.user)
        if aki_wallet.currency != Currency.AKI:
            return Response(
                {"detail": "Неверная конфигурация кошелька AKI."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 4) Списание через сервис экономики (создаётся проводка Transaction)
        # idempotency_key защитит от двойного клика
        idem_key = f"shop:buy:{request.user.id}:{offer.id}:{item.id}:{price}"
        try:
            tx = withdraw(
                aki_wallet,
                price,
                description=f"Покупка в магазине: {item.slug}",
                idempotency_key=idem_key,
            )
        except InsufficientFunds:
            return Response(
                {"detail": "Недостаточно AkiCoin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5) Фиксируем покупку
        purchase = Purchase.objects.create(
            user=request.user,
            item=item,
            price_aki=price,
            transaction=tx,
            status=PurchaseStatus.SUCCESS,
        )

        # 6) Выдаём предмет и увеличиваем счётчик продаж
        inv, _ = Inventory.objects.get_or_create(
            user=request.user,
            item=item,
            defaults={"source": InventorySource.PURCHASE},
        )
        if item.limited_total is not None:
            # безопасно инкрементим счётчик
            type(item).objects.filter(pk=item.pk).update(
                limited_sold=models.F("limited_sold") + 1
            )

        # 7) Готово
        return Response(
            {
                "ok": True,
                "purchase_id": purchase.id,
                "inventory_id": inv.id,
                "new_balance": aki_wallet.balance,  # минорные единицы (целые AKI)
            }
        )
