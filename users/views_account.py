# users/views_account.py
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.conf import settings
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken


from .models import OneTimeCode  # <-- ВАЖНО: локальный импорт из .models

User = get_user_model()

def send_code_email(email: str, subject: str, code: str):
    body = (
        f"Ваш код подтверждения: {code}\n\n"
        f"Если вы не запрашивали это действие — просто проигнорируйте письмо."
    )
    send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [email])


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")
        user = request.user

        if not old_password or not new_password:
            return Response({"detail": "Укажите old_password и new_password"}, status=status.HTTP_400_BAD_REQUEST)
        if not user.check_password(old_password):
            return Response({"detail": "Неверный старый пароль"}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 8:
            return Response({"detail": "Пароль должен содержать не менее 8 символов"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"ok": True, "detail": "Пароль успешно изменён"}, status=status.HTTP_200_OK)


class ChangeEmailRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        new_email = (request.data.get("new_email") or "").strip().lower()
        user = request.user
        if not new_email:
            return Response({"detail": "Укажите new_email"}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            return Response({"detail": "Эта почта уже используется"}, status=status.HTTP_400_BAD_REQUEST)

        code = get_random_string(6, "0123456789")
        OneTimeCode.objects.create(user=user, action=OneTimeCode.ACTION_CHANGE_EMAIL, value=new_email, code=code)
        send_code_email(new_email, "Подтверждение смены почты", code)
        return Response({"ok": True, "detail": "Код отправлен на новую почту"}, status=status.HTTP_200_OK)


class ChangeEmailConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        new_email = (request.data.get("new_email") or "").strip().lower()
        code = (request.data.get("code") or "").strip()
        user = request.user
        if not new_email or not code:
            return Response({"detail": "new_email и code обязательны"}, status=status.HTTP_400_BAD_REQUEST)

        rec = OneTimeCode.objects.filter(
            user=user, action=OneTimeCode.ACTION_CHANGE_EMAIL, value=new_email, code=code
        ).order_by("-created_at").first()

        if not rec or not rec.is_valid():
            return Response({"detail": "Неверный или истёкший код"}, status=status.HTTP_400_BAD_REQUEST)

        user.email = new_email
        user.save(update_fields=["email"])
        rec.delete()
        return Response({"ok": True, "detail": "Почта изменена"}, status=status.HTTP_200_OK)


class DeleteAccountRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.email:
            return Response({"detail": "У аккаунта не установлена почта"}, status=status.HTTP_400_BAD_REQUEST)
        code = get_random_string(6, "0123456789")
        OneTimeCode.objects.create(user=user, action=OneTimeCode.ACTION_DELETE_ACCOUNT, value=user.email, code=code)
        send_code_email(user.email, "Подтверждение удаления учётной записи", code)
        return Response({"ok": True, "detail": "Код отправлен на вашу почту"}, status=status.HTTP_200_OK)


class DeleteAccountConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        password = (request.data.get("password") or "").strip()
        code = (request.data.get("code") or "").strip()
        user = request.user

        if not password or not code:
            return Response({"detail": "Пароль и код обязательны"}, status=status.HTTP_400_BAD_REQUEST)
        if not user.check_password(password):
            return Response({"detail": "Неверный пароль"}, status=status.HTTP_400_BAD_REQUEST)

        rec = OneTimeCode.objects.filter(
            user=user, action=OneTimeCode.ACTION_DELETE_ACCOUNT, code=code
        ).order_by("-created_at").first()

        if not rec or not rec.is_valid():
            return Response({"detail": "Неверный или истёкший код"}, status=status.HTTP_400_BAD_REQUEST)

        rec.delete()

        # ✅ Анонимизация, а не NULL
        anonymized_email = f"deleted_{user.pk}@deleted.akimori"
        anonymized_username = f"deleted_{user.pk}"

        user.is_active = False
        user.username = anonymized_username
        user.email = anonymized_email
        user.save(update_fields=["is_active", "username", "email"])

        # ✅ Удаляем JWT-токены (logout)
        try:
            token = RefreshToken.for_user(user)
            token.blacklist()  # если включён blacklist в настройках
        except Exception:
            pass  # fallback если blacklist не активирован

        # Можно также удалить сессионный cookie (если у тебя session-based)
        response = Response({"ok": True, "detail": "Аккаунт деактивирован и вы вышли из системы"},
                            status=status.HTTP_200_OK)
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")

        return response