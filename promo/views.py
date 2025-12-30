from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PromoCode
from .serializers import (
    PromoCodeInSerializer,
    PromoRedeemInSerializer,
    PromoOutSerializer,
    build_effect_payload,
)


def api_error(code: str, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": code}, status=http_status)


def get_promo_or_404(code: str):
    try:
        return PromoCode.objects.get(code=code)
    except PromoCode.DoesNotExist:
        return None


def promo_to_out(promo: PromoCode) -> dict:
    return {
        "code": promo.code,
        "is_active": promo.is_active,
        "starts_at": promo.starts_at,
        "ends_at": promo.ends_at,
        "max_total_uses": promo.max_total_uses,
        "max_uses_per_user": promo.max_uses_per_user,
        "uses_count": promo.uses_count,
        "effect": build_effect_payload(promo),
    }


class PromoValidateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = PromoCodeInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        code = (s.validated_data["code"] or "").strip().upper()

        promo = get_promo_or_404(code)
        if promo is None:
            return api_error("promo_not_found", status.HTTP_404_NOT_FOUND)

        ok, reason = promo.can_user_redeem_applied(request.user)
        if not ok:
            return api_error(reason)

        data = promo_to_out(promo)
        return Response(PromoOutSerializer(data).data, status=status.HTTP_200_OK)


class PromoRedeemView(APIView):
    """
    Только manual: бонус/предмет выдаётся сразу.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = PromoRedeemInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        code = (s.validated_data["code"] or "").strip().upper()

        promo = get_promo_or_404(code)
        if promo is None:
            return api_error("promo_not_found", status.HTTP_404_NOT_FOUND)

        ip = request.META.get("REMOTE_ADDR", "") or ""
        ua = request.META.get("HTTP_USER_AGENT", "") or ""

        try:
            redemption = promo.redeem(
                request.user,
                context="manual",
                topup_amount_minor=None,
                ip=ip,
                ua=ua,
            )
        except DjangoValidationError as e:
            msg = e.message_dict.get("code")
            if isinstance(msg, list) and msg:
                return api_error(msg[0])
            if isinstance(msg, str):
                return api_error(msg)
            return api_error("invalid_promo")

        return Response(
            {"ok": True, "redeemed_at": redemption.redeemed_at, "payload": redemption.payload},
            status=status.HTTP_201_CREATED,
        )
