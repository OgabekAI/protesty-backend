from unittest.mock import patch
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from apps.authentication.models import TelegramLoginCode

User = get_user_model()


class AuthenticationAPITests(APITestCase):

    def test_telegram_generate_code_requires_secret_if_configured(self):
        url = reverse('authentication:telegram-code')
        data = {
            'telegram_id': 123456789,
            'telegram_first_name': 'TestUser',
        }
        # Without secret header when TELEGRAM_BOT_SECRET is set
        bot_secret = getattr(settings, 'TELEGRAM_BOT_SECRET', '')
        if bot_secret:
            response = self.client.post(url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # With secret header
        response = self.client.post(
            url,
            data,
            format='json',
            HTTP_X_TELEGRAM_BOT_SECRET=bot_secret or ''
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('code', response.data)
        self.assertIn('expires_at', response.data)
        self.assertTrue(TelegramLoginCode.objects.filter(telegram_id=123456789).exists())

    def test_telegram_verify_code_creates_user(self):
        # Generate code first
        code_obj = TelegramLoginCode.objects.create(
            telegram_id=987654321,
            telegram_first_name='TelegramUser',
            code='123456'
        )

        url = reverse('authentication:telegram-verify')
        data = {
            'telegram_id': 987654321,
            'code': '123456'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertEqual(response.data['user']['telegram_id'], 987654321)

        code_obj.refresh_from_db()
        self.assertTrue(code_obj.is_used)

    @patch('apps.authentication.services.google_id_token.verify_oauth2_token')
    def test_google_auth_success(self, mock_verify):
        mock_verify.return_value = {
            'sub': 'google_12345',
            'email': 'testuser@example.com',
            'given_name': 'Google',
            'family_name': 'User',
            'picture': 'https://lh3.googleusercontent.com/a/test',
        }

        url = reverse('authentication:google-auth')
        data = {'id_token': 'fake_google_token'}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)
        self.assertEqual(response.data['user']['email'], 'testuser@example.com')
        self.assertEqual(response.data['user']['google_id'], 'google_12345')

    def test_logout(self):
        user = User.objects.create_user(username='testuser', email='test@example.com')
        from apps.authentication.services import TokenService
        tokens = TokenService.get_tokens_for_user(user)

        url = reverse('authentication:logout')
        data = {'refresh': tokens['refresh']}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Successfully logged out.')
