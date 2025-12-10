from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAuthorOrStaffOrReadOnly(BasePermission):
    """
    Создатель объекта или staff могут менять; остальные — только читать.
    Ожидаем, что у объекта есть .author.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(obj, "author_id", None) == user.id:
            return True
        return bool(user.is_staff)


class IsThreadOpen(BasePermission):
    """
    Разрешает POST комментариев, только если тема не закрыта.
    В view должен лежать thread (или в сериалайзере).
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        thread = getattr(view, "thread", None)
        if thread is None:
            return True  # пускаем, пусть clean() на модели ещё проверит
        return not bool(getattr(thread, "is_locked", False))
