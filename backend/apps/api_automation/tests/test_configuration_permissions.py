from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.api_automation.models import ApiAutomationProject
from apps.api_automation.views import ApiAutomationConfigurationViewSet


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
        ApiAutomationProject.objects.create(name='Configuration Project', owner=self.user)
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