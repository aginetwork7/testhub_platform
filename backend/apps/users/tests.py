from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class UserAccessTests(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username='regular-user',
            email='regular@example.com',
            password='password123',
        )
        self.admin_user = User.objects.create_user(
            username='admin-user',
            email='admin@example.com',
            password='password123',
            is_staff=True,
        )

    def test_registration_requires_email(self) -> None:
        response = self.client.post(
            reverse('register'),
            {
                'username': 'missing-email',
                'password': 'password123',
                'password_confirm': 'password123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_registration_does_not_accept_personal_profile_fields(self) -> None:
        response = self.client.post(
            reverse('register'),
            {
                'username': 'registration-user',
                'email': 'registration@example.com',
                'password': 'password123',
                'password_confirm': 'password123',
                'first_name': 'Ignored',
                'last_name': 'Ignored',
                'department': 'Ignored',
                'position': 'Ignored',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='registration-user')
        self.assertEqual(user.first_name, '')
        self.assertEqual(user.last_name, '')
        self.assertIsNone(user.department)
        self.assertIsNone(user.position)

    def test_test_registration_endpoint_is_not_exposed(self) -> None:
        response = self.client.post('/api/auth/test-register/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_list_is_restricted_to_administrators(self) -> None:
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse('user-list'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_can_read_assignable_user_directory(self) -> None:
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse('assignable-user-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('phone', response.data[0])
        self.assertIn('email', response.data[0])

    def test_administrator_can_list_users_without_phone_numbers(self) -> None:
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse('user-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('phone', response.data['results'][0])