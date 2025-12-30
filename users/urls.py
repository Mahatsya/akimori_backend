from django.urls import path, include
from .views_register import RegisterView, VerifyEmailView
from rest_framework.routers import DefaultRouter

from users.views_jwt import ActiveUserTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    MeView, PublicProfileView, PublicUserAnimeListView,
    MyProgressView, AddXPView, MyAnimeListViewSet,
    MyProfileSettingsView, AvatarUploadView, AvatarSelectView,
    UserAvatarView, MeAvatarView,  
)

from .views_account import (
    ChangePasswordView, ChangeEmailRequestView, ChangeEmailConfirmView,
    DeleteAccountRequestView, DeleteAccountConfirmView,
)

router = DefaultRouter()
router.register(r"users/me/anime", MyAnimeListViewSet, basename="my-anime")

urlpatterns = [
    path("", include(router.urls)),

    path("auth/me/", MeView.as_view()),
    path("users/me/progress/", MyProgressView.as_view()),
    path("users/me/add_xp/", AddXPView.as_view()),

    # Настройки профиля + аватары
    path("users/me/profile/settings/", MyProfileSettingsView.as_view()),
    path("users/me/profile/avatar/upload/",  AvatarUploadView.as_view()),
    path("users/me/profile/avatar/select/",  AvatarSelectView.as_view()),
    path("users/me/avatar/", MeAvatarView.as_view()),                    # GET
    path("users/<int:user_id>/avatar/", UserAvatarView.as_view()),       # GET (публично)

    # Публичные
    path("users/<str:username>/profile/", PublicProfileView.as_view(), name="public-profile"),
    path("users/<str:username>/anime/",   PublicUserAnimeListView.as_view(),   name="public-anime"),

    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/verify/", VerifyEmailView.as_view(), name="auth-verify-email"),
    path("auth/jwt/create/", ActiveUserTokenObtainPairView.as_view(), name="jwt-create"),
    path("auth/jwt/refresh/", TokenRefreshView.as_view(), name="jwt-refresh"),


    path("users/me/account/change-password/", ChangePasswordView.as_view()),
    path("users/me/account/change-email/request/", ChangeEmailRequestView.as_view()),
    path("users/me/account/change-email/confirm/", ChangeEmailConfirmView.as_view()),
    path("users/me/account/delete/request/", DeleteAccountRequestView.as_view()),
    path("users/me/account/delete/confirm/", DeleteAccountConfirmView.as_view()),
]
