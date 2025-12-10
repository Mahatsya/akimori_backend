from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from rest_framework_simplejwt.authentication import JWTAuthentication

class JWTAuthMiddleware:
    """
    Достаёт JWT из query (?token=...) и аутентифицирует scope['user'].
    Оставляем совместимость с cookie-сессией, если токена нет.
    """
    def __init__(self, inner):
        self.inner = inner
        self.jwt_auth = JWTAuthentication()

    async def __call__(self, scope, receive, send):
        user = scope.get("user", AnonymousUser())
        try:
            raw_qs = scope.get("query_string", b"").decode()
            query = parse_qs(raw_qs)
            token = None
            # пробуем несколько ключей
            for k in ("token", "access", "Authorization", "authorization"):
                if k in query and len(query[k]):
                    token = query[k][0]
                    break
            if token and token.startswith("Bearer "):
                token = token.split(" ", 1)[1]

            if token:
                validated = self.jwt_auth.get_validated_token(token)
                user = await self._get_user(validated)
        except Exception:
            # любая ошибка — остаёмся анонимом
            user = user or AnonymousUser()

        scope["user"] = user
        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def _get_user(self, validated_token):
        return self.jwt_auth.get_user(validated_token)
