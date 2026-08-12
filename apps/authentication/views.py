from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings

from apps.users.serializers import UserSerializer
from .serializers import (
    GoogleAuthSerializer,
    TelegramGenerateCodeSerializer,
    TelegramVerifyCodeSerializer,
    TelegramBroadcastSerializer,
    LogoutSerializer,
)
from .services import GoogleAuthService, TelegramAuthService


class GoogleAuthView(APIView):
    """
    POST /api/v1/auth/google/
    Authenticates or registers a user via Google OAuth2 ID Token.
    Supports optional account linking if user is already authenticated.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        id_token = serializer.validated_data['id_token']
        current_user = request.user if request.user.is_authenticated else None

        user, tokens = GoogleAuthService.verify_and_authenticate(id_token, current_user=current_user)

        return Response({
            'user': UserSerializer(user).data,
            'tokens': tokens,
        }, status=status.HTTP_200_OK)


def verify_bot_secret(request) -> bool:
    bot_secret = getattr(settings, 'TELEGRAM_BOT_SECRET', '')
    if not bot_secret:
        return True
    incoming_secret = (
        request.headers.get('X-Telegram-Bot-Secret', '') or
        request.headers.get('x-telegram-bot-secret', '') or
        request.META.get('HTTP_X_TELEGRAM_BOT_SECRET', '') or
        (isinstance(request.data, dict) and request.data.get('bot_secret', ''))
    )
    return incoming_secret == bot_secret


class TelegramGenerateCodeView(APIView):
    """
    POST /api/v1/auth/telegram/code/
    Generates a 6-digit Telegram login code for the specified telegram_id.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        if not verify_bot_secret(request):
            return Response(
                {"detail": "Unauthorized: Invalid bot secret key."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = TelegramGenerateCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        telegram_id = serializer.validated_data['telegram_id']
        telegram_first_name = serializer.validated_data.get('telegram_first_name', '')
        telegram_username = serializer.validated_data.get('telegram_username', '')
        telegram_photo_url = serializer.validated_data.get('telegram_photo_url', '')

        code_obj = TelegramAuthService.generate_login_code(
            telegram_id=telegram_id,
            telegram_first_name=telegram_first_name,
            telegram_photo_url=telegram_photo_url,
            telegram_username=telegram_username,
        )

        return Response({
            'message': 'Login code generated successfully.',
            'code': code_obj.code,
            'expires_at': code_obj.expires_at.isoformat(),
        }, status=status.HTTP_201_CREATED)


class TelegramBroadcastView(APIView):
    """
    POST /api/v1/auth/telegram/broadcast/
    Broadcasts announcement / ad (text or photo + text) to Telegram bot users.
    Requires bot secret key or admin user credentials.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        is_admin = request.user and request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'role', '') in ('ADMIN', 'SUPER_ADMIN'))
        if not verify_bot_secret(request) and not is_admin:
            return Response(
                {"detail": "Unauthorized: Admin privileges or valid bot secret required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = TelegramBroadcastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        text = serializer.validated_data['text']
        photo_url = serializer.validated_data.get('photo_url', '')
        telegram_ids = serializer.validated_data.get('telegram_ids', [])

        result = TelegramAuthService.broadcast_message(
            text=text,
            photo_url=photo_url,
            telegram_ids=telegram_ids
        )

        return Response(result, status=status.HTTP_200_OK)


class TelegramVerifyCodeView(APIView):
    """
    POST /api/v1/auth/telegram/verify/
    Verifies 6-digit login code and returns SimpleJWT tokens.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = TelegramVerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        telegram_id = serializer.validated_data.get('telegram_id')
        code = serializer.validated_data['code']
        current_user = request.user if request.user.is_authenticated else None

        user, tokens = TelegramAuthService.verify_login_code(
            telegram_id=telegram_id,
            code_str=code,
            current_user=current_user
        )

        return Response({
            'user': UserSerializer(user).data,
            'tokens': tokens,
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Blacklists the provided refresh token.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': 'Successfully logged out.'
        }, status=status.HTTP_200_OK)
