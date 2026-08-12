from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from apps.users.models import Subject, Language, Gender
from apps.authentication.services import TokenService

User = get_user_model()


class UserProfileAPITests(APITestCase):

    def setUp(self):
        self.math_subject = Subject.objects.create(name='Mathematics', code='MATH')
        self.physics_subject = Subject.objects.create(name='Physics', code='PHYS')

        self.user = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            first_name='Ali',
            last_name='Valiyev'
        )
        tokens = TokenService.get_tokens_for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + tokens['access'])

    def test_get_user_profile(self):
        url = reverse('users:user-me')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'user1@example.com')
        self.assertEqual(response.data['first_name'], 'Ali')

    def test_patch_user_profile(self):
        url = reverse('users:user-me')
        data = {
            'first_name': 'Alisher',
            'language': Language.UZ,
            'gender': Gender.MALE,
            'prepared_subjects': [str(self.math_subject.id), str(self.physics_subject.id)]
        }
        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], 'Alisher')
        self.assertEqual(len(response.data['prepared_subjects']), 2)

    def test_get_subjects_list(self):
        self.client.credentials()  # Unauthenticated
        url = reverse('users:subject-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
