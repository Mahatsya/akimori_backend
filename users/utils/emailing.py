# users/utils/emailing.py
from django.core.mail import send_mail
from django.conf import settings

def send_verification_email(user, code):
    subject = "Подтверждение регистрации на Akimori"
    message = f"Привет, {user.username}!\n\nВаш код подтверждения: {code}\nОн действителен 15 минут."
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
