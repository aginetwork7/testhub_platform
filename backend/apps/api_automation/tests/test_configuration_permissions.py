from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from unittest.mock import patch

from apps.api_automation.models import ApiAutomationConfiguration, ApiAutomationProject, ApiAutomationRun
from apps.api_automation.views import ApiAutomationConfigurationViewSet, ApiAutomationRunViewSet


class ApiAutomationConfigurationPermissionTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='configuration-user',
            email='configuration-user@example.com',
        )
        self.admin_user = user_model.objects.create_user(
            username='configuration-admin',
            email='configuration-admin@example.com',
            is_staff=True,
        )
        self.project = ApiAutomationProject.objects.create(name='Configuration Project', owner=self.user)
        self.factory = APIRequestFactory()
        self.view = ApiAutomationConfigurationViewSet.as_view({'get': 'list'})

    def test_configuration_list_requires_administrator(self) -> None:
        request = self.factory.get('/api/api-automation/configurations/')
        force_authenticate(request, user=self.user)

        response = self.view(request)

        self.assertEqual(response.status_code, 403)

    def test_administrator_can_list_all_configurations(self) -> None:
        request = self.factory.get('/api/api-automation/configurations/')
        force_authenticate(request, user=self.admin_user)

        response = self.view(request)

        self.assertEqual(response.status_code, 200)

    def test_administrator_cannot_bind_configuration_to_project(self) -> None:
        view = ApiAutomationConfigurationViewSet.as_view({'post': 'create'})
        request = self.factory.post(
            '/api/api-automation/configurations/',
            {'name': 'Global Configuration', 'environment': 'test', 'project': 1},
            format='json',
        )
        force_authenticate(request, user=self.admin_user)

        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn('project', response.data)

    @patch('apps.api_automation.views.async_task', return_value='task-1')
    def test_project_member_can_start_run_with_global_configuration(self, async_task_mock) -> None:
        configuration = ApiAutomationConfiguration.objects.create(
            name='Global Configuration',
            environment='test',
        )
        view = ApiAutomationRunViewSet.as_view({'post': 'start'})
        request = self.factory.post(
            '/api/api-automation/runs/start/',
            {'project_id': self.project.id, 'configuration_id': configuration.id},
            format='json',
        )
        force_authenticate(request, user=self.user)

        response = view(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['configuration'], configuration.id)
        self.assertTrue(ApiAutomationRun.objects.filter(project=self.project, configuration=configuration).exists())
        async_task_mock.assert_called_once()