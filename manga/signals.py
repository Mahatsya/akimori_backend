from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Edition, ChapterPage, Chapter, TranslatorPublisher


@receiver(post_save, sender=Edition)
@receiver(post_delete, sender=Edition)
def recalc_manga_count(sender, instance: Edition, **kwargs):
    """
    Поддерживаем счётчик manga_count у переводчика.
    Считаем число уникальных манг, где есть издания данного переводчика.
    """
    tr: TranslatorPublisher = instance.translator
    count = tr.editions.values_list("manga_id", flat=True).distinct().count()
    if tr.manga_count != count:
        tr.manga_count = count
        tr.save(update_fields=["manga_count", "updated_at"])


@receiver(post_save, sender=ChapterPage)
@receiver(post_delete, sender=ChapterPage)
def recalc_pages(sender, instance: ChapterPage, **kwargs):
    """
    Обновляем pages_count у главы при изменениях страниц.
    """
    ch: Chapter = instance.chapter
    ch.recalc_pages_count()
