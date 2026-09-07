from django.test import SimpleTestCase

from apps.ai_testing.views import resolve_execution_status


class ExecutionStatusTests(SimpleTestCase):
    def test_empty_plan_is_inconclusive(self) -> None:
        status, summary = resolve_execution_status([])

        self.assertEqual(status, 'inconclusive')
        self.assertEqual(summary['total'], 0)

    def test_pending_plan_is_inconclusive(self) -> None:
        status, summary = resolve_execution_status([
            {'id': 1, 'description': 'Open the dashboard', 'status': 'pending'},
        ])

        self.assertEqual(status, 'inconclusive')
        self.assertEqual(summary['pending'], 1)

    def test_failed_plan_is_failed(self) -> None:
        status, summary = resolve_execution_status([
            {'id': 1, 'description': 'Open the dashboard', 'status': 'failed'},
        ])

        self.assertEqual(status, 'failed')
        self.assertEqual(summary['failed'], 1)

    def test_completed_plan_is_passed(self) -> None:
        status, summary = resolve_execution_status([
            {'id': 1, 'description': 'Open the dashboard', 'status': 'completed'},
        ])

        self.assertEqual(status, 'passed')
        self.assertEqual(summary['completed'], 1)