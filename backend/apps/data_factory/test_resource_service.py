from django.test import SimpleTestCase

from apps.data_factory.resource_service import create_resource


class ResourceServiceTests(SimpleTestCase):
    def test_creates_alert_event_resource(self) -> None:
        result = create_resource('alert_event', {'alert_type': 'vehicle'})

        self.assertTrue(result['success'])
        self.assertEqual(result['resource_type'], 'alert_event')
        self.assertTrue(result['resource_id'])

    def test_rejects_unknown_resource_type(self) -> None:
        result = create_resource('unknown', {})

        self.assertFalse(result['success'])
        self.assertIn('Unsupported resource type', result['error'])