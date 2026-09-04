import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from apps.ai_testing.execution.environment_adapters import read_api_resource, request_http
from apps.ai_testing.execution.http_targets import resolve_http_target


class HttpTargetResolverTests(unittest.TestCase):
    def test_resolves_registered_get_target(self) -> None:
        configuration = SimpleNamespace(runtime_settings={
            'ai_testing_http_targets': {
                'health': {'path': '/health', 'methods': ['GET']},
            },
        })

        target = resolve_http_target(configuration, 'health')

        self.assertEqual(target['path'], '/health')
        self.assertEqual(target['methods'], ('GET',))

    def test_rejects_unknown_target(self) -> None:
        configuration = SimpleNamespace(runtime_settings={'ai_testing_http_targets': {}})

        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            resolve_http_target(configuration, 'unknown')

    def test_reads_registered_resource_with_standard_evidence(self) -> None:
        response = Mock(status_code=200, url='https://example.test/health')
        response.json.return_value = {'status': 'ok'}
        session = Mock()
        session.request.return_value = response
        configuration = SimpleNamespace(
            base_url='https://example.test',
            timeout_seconds=10,
            runtime_settings={'ai_testing_http_targets': {'health': {'path': '/health', 'methods': ['GET']}}},
        )

        result = read_api_resource(configuration, 'health', session=session)

        self.assertEqual(result['response'], {'status': 'ok'})
        self.assertEqual([item['type'] for item in result['evidence']], ['network_response', 'api_response'])

    def test_rejects_non_get_request_to_registered_target(self) -> None:
        configuration = SimpleNamespace(
            base_url='https://example.test',
            runtime_settings={'ai_testing_http_targets': {'health': {'path': '/health', 'methods': ['GET']}}},
        )

        with self.assertRaisesRegex(ValueError, 'not allowed'):
            request_http(configuration, 'health', method='POST')