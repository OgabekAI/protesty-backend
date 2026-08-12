from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    GoogleAuthView,
    TelegramGenerateCodeView,
    TelegramVerifyCodeView,
    TelegramBroadcastView,
    LogoutView,
)

app_name = 'authentication'

urlpatterns = [
    path('google/', GoogleAuthView.as_view(), name='google-auth'),
    path('telegram/code/', TelegramGenerateCodeView.as_view(), name='telegram-code'),
    path('telegram/verify/', TelegramVerifyCodeView.as_view(), name='telegram-verify'),
    path('telegram/broadcast/', TelegramBroadcastView.as_view(), name='telegram-broadcast'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
