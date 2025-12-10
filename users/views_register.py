from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import EmailVerification

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]  # 👈 вот это обязательно

    def post(self, request):
        username = request.data.get("username")
        email = request.data.get("email")
        password = request.data.get("password")

        if not all([username, email, password]):
            return Response({"error": "Все поля обязательны"}, status=400)

        if User.objects.filter(username=username).exists():
            return Response({"error": "Имя пользователя занято"}, status=400)

        if User.objects.filter(email=email).exists():
            return Response({"error": "Почта уже используется"}, status=400)

        user = User.objects.create_user(username=username, email=email, password=password)
        code_obj = EmailVerification.create_for_user(user)

        # Здесь можешь добавить отправку письма
        print(f"Verification code for {email}: {code_obj.code}")

        return Response({"message": "Код отправлен на почту"}, status=201)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]  # 👈 обязательно

    def post(self, request):
        email = request.data.get("email")
        code = request.data.get("code")

        if not email or not code:
            return Response({"error": "Укажите email и код"}, status=400)

        try:
            user = User.objects.get(email=email)
            record = EmailVerification.objects.filter(user=user, code=code).first()
            if not record or not record.is_valid():
                return Response({"error": "Код недействителен"}, status=400)

            record.is_used = True
            record.save(update_fields=["is_used"])
            user.is_active = True
            user.save(update_fields=["is_active"])
            return Response({"message": "Email подтверждён"}, status=200)

        except User.DoesNotExist:
            return Response({"error": "Пользователь не найден"}, status=404)
