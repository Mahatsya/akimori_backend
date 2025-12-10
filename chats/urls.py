# chats/urls.py
from rest_framework.routers import DefaultRouter
from .views import ConversationViewSet

router = DefaultRouter()
router.register(r"chats", ConversationViewSet, basename="chats")
urlpatterns = router.urls
