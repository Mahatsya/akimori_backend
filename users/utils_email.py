# users/utils_email.py
from django.conf import settings
from django.core.mail import send_mail

class DevEmailFallback(Exception):
    """Разрешает не падать на деве, если SMTP не сконфигурен."""
    pass

def send_code(email: str, subject: str, code: str):
    body = (
        f"Ваш код подтверждения: {code}\n\n"
        f"Если вы не запрашивали это действие — просто проигнорируйте письмо."
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email])
    except Exception as e:
        if settings.DEBUG:
            # на деве можно продолжать тестировать без реальной почты
            raise DevEmailFallback(str(e))
        raise
