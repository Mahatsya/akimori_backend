from django.apps import AppConfig

class EconomyConfig(AppConfig):
    name = "economy"
    verbose_name = "Economy"

    def ready(self):
        from . import signals  # noqa: F401
