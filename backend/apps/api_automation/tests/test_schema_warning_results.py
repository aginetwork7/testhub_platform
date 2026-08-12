from django.test import SimpleTestCase

from apps.api_automation.executor import _result_test_counts


class SchemaWarningResultCountTests(SimpleTestCase):
    def test_schema_warning_is_counted_as_pass_and_warning(self) -> None:
        result = {'status': 'SCHEMA_WARNING', 'details': {}}

        counts = _result_test_counts(result)

        self.assertEqual(
            counts,
            {'total': 1, 'passed': 1, 'failed': 0, 'skipped': 0, 'schema_warnings': 1},
        )

    def test_schema_warning_preserves_runner_test_counts(self) -> None:
        result = {
            'status': 'SCHEMA_WARNING',
            'details': {
                'test_counts': {'total': 2, 'passed': 2, 'failed': 0, 'skipped': 0},
            },
        }

        counts = _result_test_counts(result)

        self.assertEqual(
            counts,
            {'total': 2, 'passed': 2, 'failed': 0, 'skipped': 0, 'schema_warnings': 1},
        )