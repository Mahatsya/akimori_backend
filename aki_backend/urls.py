from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from django.conf import settings
from django.conf.urls.static import static
from blog.views import tinymce_image_upload


urlpatterns = [
    path("admin/", admin.site.urls),
    path("summernote/", include("django_summernote.urls")),
    path("froala_editor/", include("froala_editor.urls")),

    # JWT
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),

    # App routes
    path("api/", include("blog.urls")),
    path("api/", include("users.urls")),   # users всё в одном месте
    path("api/", include("manga.urls")),
    path("api/", include("economy.urls")),
    path("api/", include("customitem.urls")),
    path("api/", include("forum.urls")),
    path("api/", include("shop.urls")),
    path("api/", include("kodik.urls")),
    path("api/", include("chats.urls")),
    path("api/", include("craft.urls")),
    path("api/", include("promo.urls")),

    path('tinymce/', include('tinymce.urls')),
    path("tinymce/upload/", tinymce_image_upload, name="tinymce_image_upload"),
    
] 
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)