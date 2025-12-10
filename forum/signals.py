from __future__ import annotations
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.timezone import now

from .models import Comment, Thread


@receiver(post_save, sender=Comment)
def comment_created_or_updated(sender, instance: Comment, created, **kwargs):
    thread = instance.thread
    # обновим last_activity на каждый новый комментарий
    if created:
        Thread.objects.filter(pk=thread.pk).update(
            comments_count=thread.comments.count(),
            last_activity_at=now()
        )
        # replies_count у родителя
        if instance.parent_id:
            parent = instance.parent
            parent.replies_count = parent.replies.count()
            parent.save(update_fields=["replies_count", "updated_at"])
    else:
        # если менялся parent — можно тоже пересчитать, но это редкость
        pass


@receiver(post_delete, sender=Comment)
def comment_deleted(sender, instance: Comment, **kwargs):
    thread = instance.thread
    Thread.objects.filter(pk=thread.pk).update(
        comments_count=thread.comments.count(),
        last_activity_at=now()
    )
    if instance.parent_id:
        parent = instance.parent
        # parent может уже быть удалён каскадом — проверяем
        if parent and parent.pk:
            parent.replies_count = parent.replies.count()
            parent.save(update_fields=["replies_count", "updated_at"])
