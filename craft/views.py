from rest_framework import viewsets, permissions
from .models import HeaderMaterialContent
from .serializers import HeaderMaterialContentSerializer


class HeaderMaterialContentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Отдаём список шапок для главной.
    Можно использовать как слайдер / hero-блок.
    """

    queryset = (
        HeaderMaterialContent.objects
        .select_related("material", "material__extra")
        .filter(is_active=True)
        .order_by("position", "-created_at")
    )
    serializer_class = HeaderMaterialContentSerializer
    permission_classes = [permissions.AllowAny]
