# aki_backend/asgi.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aki_backend.settings")

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

django_asgi_app = get_asgi_application()

import chats.routing  # noqa
from chats.middleware import JWTAuthMiddleware  # noqa

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        AuthMiddlewareStack(
            URLRouter(chats.routing.websocket_urlpatterns)
        )
    ),
})
