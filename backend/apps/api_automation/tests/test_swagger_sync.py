from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import Mock, patch
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.api_automation.models import ApiAutomationEndpoint, ApiAutomationProject
from apps.api_automation.swagger_sync import (
    SwaggerTokenExpiredError,
    _download_swagger,
    _redact_sensitive_markers,
    _synchronize_endpoint_catalog,
)
from apps.api_automation.views import ApiAutomationEndpointViewSet


class SwaggerCatalogSyncTests(TestCase):
    def test_download_swagger_reports_expired_or_invalid_token(self) -> None:
        response = Mock(status_code=401)

        with patch('apps.api_automation.swagger_sync.requests.get', return_value=response):
            with self.assertRaisesRegex(SwaggerTokenExpiredError, '已过期或无效'):
                _download_swagger('https://example.com/swagger.json', 30, 'expired-token')

    def test_redact_sensitive_markers_removes_aws_access_key(self) -> None:
        raw_document = b'{"key":"AKIA1234567890ABCDEF"}'

        redacted_document = _redact_sensitive_markers(raw_document)

        self.assertEqual(redacted_document, b'{"key":"REDACTED_AWS_ACCESS_KEY"}')

    def test_synchronize_endpoint_catalog_upserts_and_removes_stale_endpoints(self) -> None:
        user = get_user_model().objects.create_user(username='swagger-sync-user')
        project = ApiAutomationProject.objects.create(name='Swagger Sync', owner=user)
        ApiAutomationEndpoint.objects.create(project=project, key='obsolete', path='/obsolete')

        result = _synchronize_endpoint_catalog(
            project,
            {
                'paths': {
                    '/devices/{id}': {
                        'get': {'summary': 'Get device', 'tags': ['devices']},
                        'patch': {'deprecated': True},
                    }
                }
            },
        )

        endpoint = ApiAutomationEndpoint.objects.get(project=project, key='devices_id')
        self.assertEqual(result, {'total': 1, 'created': 1, 'updated': 0, 'deleted': 1})
        self.assertEqual(endpoint.path, '/devices/{id}')
        self.assertEqual(endpoint.methods, ['GET', 'PATCH'])
        self.assertEqual(endpoint.tags, ['devices'])
        self.assertTrue(endpoint.deprecated)


class EndpointCategoryPaginationTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username='endpoint-category-user')
        self.project = ApiAutomationProject.objects.create(name='Endpoint Categories', owner=self.user)
        ApiAutomationEndpoint.objects.create(project=self.project, key='frontend_alert', path='/frontend/alert', tags=['frontend/alert'])
        ApiAutomationEndpoint.objects.create(project=self.project, key='frontend_camera', path='/frontend/camera', tags=['frontend/camera'])
        ApiAutomationEndpoint.objects.create(project=self.project, key='device_service', path='/device/service', tags=['DeviceService'])

    def test_list_separates_frontend_and_others_with_pagination(self) -> None:
        factory = APIRequestFactory()
        view = ApiAutomationEndpointViewSet.as_view({'get': 'list'})

        frontend_request = factory.get('/api/api-automation/endpoints/', {'project': self.project.id, 'category': 'frontend', 'page_size': 1})
        force_authenticate(frontend_request, user=self.user)
        frontend_response = view(frontend_request)

        others_request = factory.get('/api/api-automation/endpoints/', {'project': self.project.id, 'category': 'others', 'page_size': 20})
        force_authenticate(others_request, user=self.user)
        others_response = view(others_request)

        self.assertEqual(frontend_response.data['count'], 2)
        self.assertEqual(len(frontend_response.data['results']), 1)
        self.assertEqual(others_response.data['count'], 1)
        self.assertEqual(others_response.data['results'][0]['key'], 'device_service')