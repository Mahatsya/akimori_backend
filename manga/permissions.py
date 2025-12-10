from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Edition, TranslatorMember


class IsTranslatorMemberCanPublish(BasePermission):
    """
    Разрешает создание/загрузку/изменение, если request.user — член команды переводчика
    edition'а и его роль: owner/moderator/publisher.
    """
    def _allowed(self, user, edition: Edition) -> bool:
        if not user or not user.is_authenticated:
            return False
        qs = edition.translator.translatormember_set.filter(user=user, is_active=True)
        if not qs.exists():
            return False
        role = qs.first().role
        return role in {
            TranslatorMember.Role.OWNER,
            TranslatorMember.Role.MODERATOR,
            TranslatorMember.Role.PUBLISHER,
        }

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        # Для create на /chapters/ edition передаётся в теле/квери
        edition_id = request.data.get("edition") or request.query_params.get("edition")
        if not edition_id:
            return True  # проверим объектно
        try:
            edition = Edition.objects.select_related("translator").get(pk=edition_id)
        except Edition.DoesNotExist:
            return False
        return self._allowed(request.user, edition)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        edition = getattr(obj, "edition", None)
        if edition is None and hasattr(obj, "chapter"):
            edition = obj.chapter.edition
        if edition is None:
            return False
        return self._allowed(request.user, edition)
