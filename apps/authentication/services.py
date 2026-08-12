import httpx
from datetime import timedelta
import secrets
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import exceptions
from rest_framework_simplejwt.tokens import RefreshToken
from .models import TelegramLoginCode, TelegramBotUser

User = get_user_model()


class TokenService:
    @staticmethod
    def get_tokens_for_user(user):
        """Generates SimpleJWT access & refresh tokens for a user."""
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class GoogleAuthService:
    @staticmethod
    def verify_and_authenticate(id_token_str, current_user=None):
        """
        Verifies Google ID Token. 
        Creates a new user or links Google account if user already exists or is logged in.
        """
        try:
            client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
            request = google_requests.Request()
            
            # If client_id is set in settings, verify against it; otherwise verify payload
            if client_id:
                id_info = google_id_token.verify_oauth2_token(id_token_str, request, client_id)
            else:
                id_info = google_id_token.verify_oauth2_token(id_token_str, request)

        except Exception as e:
            raise exceptions.AuthenticationFailed(f"Invalid Google ID token: {str(e)}")

        google_id = id_info.get('sub')
        email = id_info.get('email')
        first_name = id_info.get('given_name', '')
        last_name = id_info.get('family_name', '')
        picture = id_info.get('picture', '')

        if not google_id:
            raise exceptions.AuthenticationFailed("Google token missing sub (user ID).")

        # 1. Account linking if currently logged in
        if current_user and current_user.is_authenticated:
            existing_user = User.objects.filter(google_id=google_id).exclude(id=current_user.id).first()
            if existing_user:
                raise exceptions.ValidationError({
                    "detail": "Ushbu Google akkaunt allaqachon boshqa foydalanuvchiga ulangan. Bir vaqtning o'zida ikkita har xil akkauntga ulash mumkin emas."
                })

            current_user.google_id = google_id
            if picture and not current_user.avatar:
                current_user.avatar = picture
            current_user.save()
            return current_user, TokenService.get_tokens_for_user(current_user)

        # 2. Check if user with this google_id already exists
        user = User.objects.filter(google_id=google_id).first()
        if user:
            if picture and not user.avatar:
                user.avatar = picture
                user.save(update_fields=['avatar'])
            return user, TokenService.get_tokens_for_user(user)

        # 3. Check if user with matching email exists (and doesn't already have a different google_id)
        if email:
            user = User.objects.filter(email=email, google_id__isnull=True).first()
            if user:
                user.google_id = google_id
                if picture and not user.avatar:
                    user.avatar = picture
                user.save()
                return user, TokenService.get_tokens_for_user(user)

        # 4. Create new user
        user = User.objects.create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            google_id=google_id,
            avatar=picture or None,
        )

        return user, TokenService.get_tokens_for_user(user)


class TelegramAuthService:
    @staticmethod
    def generate_login_code(telegram_id, telegram_first_name='', telegram_photo_url='', telegram_username=''):
        """
        Generates a 6-digit Telegram login code.
        Includes a 30-second cooldown to prevent spamming.
        Also upserts TelegramBotUser model.
        """
        # Save or update TelegramBotUser
        TelegramBotUser.objects.update_or_create(
            telegram_id=telegram_id,
            defaults={
                'first_name': telegram_first_name or '',
                'username': telegram_username or '',
                'photo_url': telegram_photo_url or None,
                'is_active': True
            }
        )

        now = timezone.now()
        # Cooldown check: if code created in last 30 seconds, return existing valid code
        recent_code = TelegramLoginCode.objects.filter(
            telegram_id=telegram_id,
            is_used=False,
            created_at__gte=now - timedelta(seconds=30)
        ).first()

        if recent_code and recent_code.is_valid:
            return recent_code

        # Create new login code (automatically invalidates previous codes in save method)
        code_obj = TelegramLoginCode.objects.create(
            telegram_id=telegram_id,
            telegram_first_name=telegram_first_name,
            telegram_photo_url=telegram_photo_url or None,
        )
        return code_obj

    @staticmethod
    def broadcast_message(text, photo_url='', telegram_ids=None):
        """
        Sends broadcast message (with optional photo) to active Telegram bot users.
        """
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not bot_token:
            raise exceptions.ValidationError({"detail": "TELEGRAM_BOT_TOKEN is not configured on backend."})

        if telegram_ids and len(telegram_ids) > 0:
            target_ids = set(telegram_ids)
        else:
            bot_users = set(TelegramBotUser.objects.filter(is_active=True).values_list('telegram_id', flat=True))
            user_table_ids = set(User.objects.filter(telegram_id__isnull=False).values_list('telegram_id', flat=True))
            target_ids = bot_users.union(user_table_ids)

        if not target_ids:
            return {"total": 0, "sent": 0, "failed": 0, "detail": "No active Telegram users found."}

        sent_count = 0
        failed_count = 0

        with httpx.Client(timeout=10.0) as client:
            for tid in target_ids:
                try:
                    if photo_url:
                        url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                        payload = {
                            "chat_id": tid,
                            "photo": photo_url,
                        }
                        if text:
                            payload["caption"] = text
                            payload["parse_mode"] = "HTML"

                        res = client.post(url, json=payload)
                        # Fallback if HTML entities parse error occurs
                        if res.status_code != 200 and "can't parse entities" in res.text:
                            payload.pop("parse_mode", None)
                            res = client.post(url, json=payload)
                    else:
                        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                        payload = {
                            "chat_id": tid,
                            "text": text,
                            "parse_mode": "HTML"
                        }
                        res = client.post(url, json=payload)
                        # Fallback if HTML entities parse error occurs
                        if res.status_code != 200 and "can't parse entities" in res.text:
                            payload.pop("parse_mode", None)
                            res = client.post(url, json=payload)

                    if res.status_code == 200 and res.json().get('ok'):
                        sent_count += 1
                    else:
                        failed_count += 1
                        error_desc = res.json().get('description', '')
                        print(f"Broadcast failed for {tid}: {res.status_code} - {error_desc}")
                        if 'blocked' in error_desc.lower() or 'user is deactivated' in error_desc.lower():
                            TelegramBotUser.objects.filter(telegram_id=tid).update(is_active=False)
                except Exception as e:
                    print(f"Exception broadcasting to {tid}: {e}")
                    failed_count += 1

        return {
            "total": len(target_ids),
            "sent": sent_count,
            "failed": failed_count
        }

    @staticmethod
    def verify_login_code(telegram_id, code_str, current_user=None):
        """
        Verifies 6-digit code for a telegram_id.
        Immediately invalidates code on success.
        Increments attempts count (max 5) on failure.
        """
        if telegram_id:
            code_obj = TelegramLoginCode.objects.filter(
                telegram_id=telegram_id,
                is_used=False
            ).first()
        else:
            code_obj = TelegramLoginCode.objects.filter(
                code=str(code_str).strip(),
                is_used=False
            ).first()

        if not code_obj or not code_obj.is_valid:
            raise exceptions.ValidationError({
                "code": "Invalid or expired login code. Please request a new code via Telegram."
            })

        telegram_id = code_obj.telegram_id


        # Secure constant-time code comparison
        if not secrets.compare_digest(str(code_obj.code), str(code_str).strip()):
            code_obj.increment_attempts()
            remaining = max(0, 5 - code_obj.attempts)
            if remaining == 0:
                raise exceptions.ValidationError({
                    "code": "Maximum 5 incorrect attempts reached. Code is now invalid."
                })
            raise exceptions.ValidationError({
                "code": f"Incorrect login code. You have {remaining} attempt(s) remaining."
            })

        # Code matched successfully! IMMEDIATELY mark used so it can NEVER be reused.
        code_obj.is_used = True
        code_obj.save(update_fields=['is_used'])

        # 1. Account linking if currently logged in
        if current_user and current_user.is_authenticated:
            existing_user = User.objects.filter(telegram_id=telegram_id).exclude(id=current_user.id).first()
            if existing_user:
                raise exceptions.ValidationError({
                    "detail": "Ushbu Telegram akkaunt allaqachon boshqa foydalanuvchiga ulangan. Bir vaqtning o'zida ikkita har xil akkauntga ulash mumkin emas."
                })

            current_user.telegram_id = telegram_id
            if code_obj.telegram_first_name and not current_user.telegram_first_name:
                current_user.telegram_first_name = code_obj.telegram_first_name
            if code_obj.telegram_photo_url and not current_user.avatar:
                current_user.avatar = code_obj.telegram_photo_url
            current_user.save()
            return current_user, TokenService.get_tokens_for_user(current_user)

        # 2. Find existing user by telegram_id
        user = User.objects.filter(telegram_id=telegram_id).first()
        if user:
            if code_obj.telegram_photo_url and not user.avatar:
                user.avatar = code_obj.telegram_photo_url
                user.save(update_fields=['avatar'])
            return user, TokenService.get_tokens_for_user(user)

        # 3. Create new user
        user = User.objects.create_user(
            telegram_id=telegram_id,
            telegram_first_name=code_obj.telegram_first_name,
            avatar=code_obj.telegram_photo_url or None,
        )

        return user, TokenService.get_tokens_for_user(user)
