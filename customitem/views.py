from rest_framework import viewsets, mixins, permissions, decorators, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from .models import Item, Inventory, AppliedCustomization, ItemType
from .serializers import ItemSerializer, InventorySerializer, AppliedCustomizationSerializer


class ItemViewSet(mixins.ListModelMixin,
                  mixins.RetrieveModelMixin,
                  viewsets.GenericViewSet):
    """
    Публичный каталог.
    /api/customitems/?type=theme&active=1&search=...
    """
    serializer_class = ItemSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Item.objects.all()
        t = self.request.query_params.get("type")
        active = self.request.query_params.get("active")
        search = self.request.query_params.get("search")
        if t:
            qs = qs.filter(type=t)
        if active in ("1", "true", "True"):
            qs = qs.filter(is_active=True)
        if search:
            qs = qs.filter(title__icontains=search)
        return qs.order_by("-created_at")


class MyInventoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    /api/customitems/me/inventory/ — мой инвентарь
    """
    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (Inventory.objects
                .filter(user=self.request.user)
                .select_related("item")
                .order_by("-acquired_at"))


class AppliedViewSet(viewsets.ViewSet):
    """
    GET  /api/customitems/me/applied/
    PUT  /api/customitems/me/applied/ { avatar_item, header_item, theme_item }
    """
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request):
        obj, _ = AppliedCustomization.objects.get_or_create(user=request.user)
        data = AppliedCustomizationSerializer(obj).data
        return Response(data)

    def update(self, request):
        obj, _ = AppliedCustomization.objects.get_or_create(user=request.user)
        ser = AppliedCustomizationSerializer(instance=obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()  # clean() в модели проверит владение и типы
        return Response(ser.data)
