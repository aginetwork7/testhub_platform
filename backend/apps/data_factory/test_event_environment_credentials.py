from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import EnvironmentConfiguration
from apps.data_factory.tools.business_tools import BusinessTools
from apps.data_factory.views import DataFactoryViewSet


class EventEnvironmentCredentialTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='event-credential-user')
        self.configuration = EnvironmentConfiguration.objects.create(
            name='Event Credential Environment',
            environment='event-credential',
            base_url='https://example.com/api',
            runtime_settings={
                'api': {
                    'edge': {
                        'main_device': {
                            'device_id': 'nvr-test',
                            'cameras': [{'camera_mac': '00:11:22:33:44:55', 'camera_name': 'Test Camera'}],
                        },
                    },
                },
            },
        )

    def test_reports_event_with_selected_environment_key(self) -> None:
        self.configuration.set_event_device_keys(main_device_key='environment-main-key')
        self.configuration.save(update_fields=['event_device_keys_encrypted'])

        with patch.object(
            BusinessTools,
            'report_alert_events',
            return_value={'success': True, 'event_ids': ['event-1']},
        ) as report_alert_events:
            result = DataFactoryViewSet().execute_business_tool(
                'construct_alert_event',
                {'environment_id': self.configuration.id, 'device': 'main', 'camera_index': 0, 'report_event': True},
                self.user,
            )

        self.assertTrue(result['success'])
        self.assertEqual(report_alert_events.call_args.kwargs['device_key'], 'environment-main-key')

    def test_requires_page_configured_device_key_for_real_reporting(self) -> None:
        result = DataFactoryViewSet().execute_business_tool(
            'construct_alert_event',
            {'environment_id': self.configuration.id, 'device': 'main', 'camera_index': 0, 'report_event': True},
            self.user,
        )

        self.assertFalse(result['success'])
        self.assertIn('页面配置设备私钥', result['error'])