from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken, TokenError


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True, help_text="Google OAuth2 ID Token from client")


class TelegramGenerateCodeSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField(required=True)
    telegram_first_name = serializers.CharField(required=False, allow_blank=True, default='')
    telegram_username = serializers.CharField(required=False, allow_blank=True, default='')
    telegram_photo_url = serializers.URLField(required=False, allow_blank=True, default='', allow_null=True)


class TelegramBroadcastSerializer(serializers.Serializer):
    text = serializers.CharField(required=True, help_text="Message text or caption for photo")
    photo_url = serializers.CharField(required=False, allow_blank=True, default='', allow_null=True, help_text="Optional photo URL or Telegram file_id to send")
    telegram_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text="Optional list of specific telegram IDs. If empty, sends to all active bot users."
    )


class TelegramVerifyCodeSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField(required=False, allow_null=True)
    code = serializers.CharField(required=True, min_length=6, max_length=6)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)

    def validate(self, attrs):
        self.token = attrs['refresh']
        return attrs

    def save(self, **kwargs):
        try:
            token = RefreshToken(self.token)
            token.blacklist()
        except TokenError:
            raise serializers.ValidationError({"refresh": "Invalid or expired refresh token."})
