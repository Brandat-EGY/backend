from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView

from .views import RegisterAPIView, LoginAPIView, CSRFTokenAPIView, MeAPIView


urlpatterns = [
    path("token/refresh/",TokenRefreshView.as_view(),name="token_refresh",),
    path("logout/",TokenBlacklistView.as_view(),name="account-logout",),
    path("register/", RegisterAPIView.as_view(), name="account-register",),
    path("login/", LoginAPIView.as_view(), name="account-login",),
    path("csrf/", CSRFTokenAPIView.as_view(), name="csrf-token",),
    path("me/", MeAPIView.as_view(), name="account-me"),
]
