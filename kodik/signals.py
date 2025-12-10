# coding: utf-8
from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Avg
from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete

from .models import (
    MaterialExtra, MaterialComment, MaterialCommentLike,
    AkiUserRating
)

# --- Комментарии (total по материалу)
def recompute_comments(material_id: int):
    comments_qs = (MaterialComment.objects
                   .filter(material_id=material_id, is_deleted=False, status="published")
                   .aggregate(cnt=Count("id")))
    MaterialExtra.objects.filter(material_id=material_id).update(
        comments_count=comments_qs["cnt"] or 0
    )

# --- Ответы (replies_count у родителя)
def recompute_replies(parent_id: int):
    replies_qs = (MaterialComment.objects
                  .filter(parent_id=parent_id, is_deleted=False, status="published")
                  .aggregate(cnt=Count("id")))
    MaterialComment.objects.filter(id=parent_id).update(
        replies_count=replies_qs["cnt"] or 0
    )

# --- Лайки (likes_count у комментария)
def recompute_likes(comment_id: int):
    likes_qs = (MaterialCommentLike.objects
                .filter(comment_id=comment_id)
                .aggregate(cnt=Count("id")))
    MaterialComment.objects.filter(id=comment_id).update(
        likes_count=likes_qs["cnt"] or 0
    )

# --- Рейтинг Akimori (в extra)
def recompute_rating(material_id: int):
    agg = (AkiUserRating.objects
           .filter(material_id=material_id)
           .aggregate(avg=Avg("score"), votes=Count("id")))
    MaterialExtra.objects.filter(material_id=material_id).update(
        aki_rating=(agg["avg"] if agg["avg"] is not None else None),
        aki_votes=agg["votes"] or 0
    )

# ---- Хуки

@receiver(post_save, sender=MaterialComment)
def on_comment_save(sender, instance: MaterialComment, created, **kwargs):
    def _do():
        recompute_comments(instance.material_id)
        if instance.parent_id:
            recompute_replies(instance.parent_id)
    transaction.on_commit(_do)

@receiver(post_delete, sender=MaterialComment)
def on_comment_delete(sender, instance: MaterialComment, **kwargs):
    def _do():
        recompute_comments(instance.material_id)
        if instance.parent_id:
            recompute_replies(instance.parent_id)
    transaction.on_commit(_do)

@receiver(post_save, sender=MaterialCommentLike)
def on_like_save(sender, instance: MaterialCommentLike, created, **kwargs):
    if not created:
        return
    def _do():
        recompute_likes(instance.comment_id)
    transaction.on_commit(_do)

@receiver(post_delete, sender=MaterialCommentLike)
def on_like_delete(sender, instance: MaterialCommentLike, **kwargs):
    def _do():
        recompute_likes(instance.comment_id)
    transaction.on_commit(_do)

@receiver(post_save, sender=AkiUserRating)
def on_rating_save(sender, instance: AkiUserRating, created, **kwargs):
    def _do():
        recompute_rating(instance.material_id)
    transaction.on_commit(_do)

@receiver(post_delete, sender=AkiUserRating)
def on_rating_delete(sender, instance: AkiUserRating, **kwargs):
    def _do():
        recompute_rating(instance.material_id)
    transaction.on_commit(_do)
