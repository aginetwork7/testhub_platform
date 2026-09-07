from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.models import EnvironmentConfiguration
from apps.core.views import EnvironmentConfigurationViewSet


class EnvironmentConfigurationViewSetTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username='environment-user')
        self.factory = APIRequestFactory()

    def test_authenticated_user_can_create_global_environment(self) -> None:
        request = self.factory.post(
            '/api/core/environment-configurations/',
            {'name': 'Test Environment', 'environment': 'test', 'base_url': 'https://example.test'},
            format='json',
        )
        force_authenticate(request, user=self.user)

        response = EnvironmentConfigurationViewSet.as_view({'post': 'create'})(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(EnvironmentConfiguration.objects.get().created_by, self.user)

    def test_set_default_clears_existing_default(self) -> None:
        first = EnvironmentConfiguration.objects.create(name='First', environment='first', is_default=True)
        second = EnvironmentConfiguration.objects.create(name='Second', environment='second')
        request = self.factory.post(f'/api/core/environment-configurations/{second.id}/set_default/')
        force_authenticate(request, user=self.user)

        response = EnvironmentConfigurationViewSet.as_view({'post': 'set_default'})(request, pk=second.id)

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    @patch('apps.core.views.DeviceCliCapability.execute')
    def test_device_endpoint_uses_core_capability(self, execute_mock) -> None:
        configuration = EnvironmentConfiguration.objects.create(name='Device', environment='device')
        execute_mock.return_value = {'status': 'PASSED'}
        request = self.factory.post(
            f'/api/core/environment-configurations/{configuration.id}/device-cli/',
            {'device_id': 'nvr_1', 'command': 'uptime'},
            format='json',
        )
        force_authenticate(request, user=self.user)

        response = EnvironmentConfigurationViewSet.as_view({'post': 'execute_device_cli'})(request, pk=configuration.id)

        self.assertEqual(response.status_code, 200)
        execute_mock.assert_called_once_with(configuration, device_id='nvr_1', command='uptime', arguments={})