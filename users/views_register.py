from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings

from .models import EmailVerification

User = get_user_model()


class RegisterView(APIView):
    permission_classes = []  # публично

    @transaction.atomic
    def post(self, request):
        username = (request.data.get("username") or "").strip()
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""

        if not username or not email or not password:
            return Response({"detail": "username, email, password required"}, status=http_status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"detail": "Username already taken"}, status=http_status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=email).exists():
            return Response({"detail": "Email already used"}, status=http_status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(username=username, email=email, password=password)
        # ВАЖНО: до подтверждения почты пользователь не активен
        user.is_active = False
        user.save(update_fields=["is_active"])

        ver = EmailVerification.create_for_user(user=user, ttl_minutes=15)

        # Отправка письма (минимальная)
        subject = "Подтверждение почты"
        message = f"Ваш код подтверждения: {ver.code}\nСрок действия: 15 минут."
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)

        # Если почта не настроена — хотя бы не ломаем регистрацию
        try:
            send_mail(subject, message, from_email, [email], fail_silently=True)
        except Exception:
            pass

        return Response(
            {"ok": True, "detail": "Verification code sent", "email": email},
            status=http_status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    permission_classes = []  # публично

    @transaction.atomic
    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        code = (request.data.get("code") or "").strip()

        if not email or not code:
            return Response({"detail": "email and code required"}, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "Invalid email or code"}, status=http_status.HTTP_400_BAD_REQUEST)

        # Ищем код именно для этого пользователя
        ver = (
            EmailVerification.objects
            .select_for_update()
            .filter(user=user, code=code, is_used=False)
            .order_by("-created_at")
            .first()
        )

        if not ver or not ver.is_valid():
            return Response({"detail": "Invalid or expired code"}, status=http_status.HTTP_400_BAD_REQUEST)

        ver.is_used = True
        ver.save(update_fields=["is_used"])

        user.is_active = True
        user.save(update_fields=["is_active"])

        return Response({"ok": True}, status=http_status.HTTP_200_OK)
