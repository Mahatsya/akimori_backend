from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, Profile
from customitem.models import Item, Inventory, ItemType

# Укажи реальные слаги созданных предметов шапок (type=HEADER_ANIM, is_active=True)
DEFAULT_HEADER_SLUGS = ("header-default-1", "header-default-2", "header-default-3")

@receiver(post_save, sender=User)
def ensure_profile(sender, instance: User, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
        # Автовыдача дефолтных шапок (если существуют)
        items = list(Item.objects.filter(type=ItemType.HEADER_ANIM, slug__in=DEFAULT_HEADER_SLUGS, is_active=True)[:3])
        for it in items:
            Inventory.objects.get_or_create(user=instance, item=it)
