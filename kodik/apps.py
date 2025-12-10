from django.apps import AppConfig

class KodikConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "kodik"

    def ready(self):
        # важно: импорт для регистрации сигналов
        from . import signals  # noqa
