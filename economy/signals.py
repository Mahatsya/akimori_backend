from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .services import ensure_user_wallets

User = get_user_model()


@receiver(post_save, sender=User)
def create_wallets_on_user_create(sender, instance: User, created, **kwargs):
    if created:
        ensure_user_wallets(instance)
