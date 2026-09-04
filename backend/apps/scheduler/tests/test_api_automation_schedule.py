from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.scheduler.task_executor import execute_api_automation_suite


class ApiAutomationScheduleTests(SimpleTestCase):
    def test_scheduled_run_uses_global_configuration(self) -> None:
        configuration = SimpleNamespace(id=31)
        project = SimpleNamespace(id=7)
        run = MagicMock(
            id=17,
            project=project,
            status='COMPLETED',
            total_cases=1,
            passed_cases=1,
            schema_warning_cases=0,
            failed_cases=0,
            skipped_cases=0,
        )
        schedule_config = SimpleNamespace(
            project_id=project.id,
            task_config={'configuration_id': configuration.id},
            created_by=SimpleNamespace(id=3),
            notify_on_success=False,
            notify_on_failure=False,
        )

        with (
            patch('apps.scheduler.models.ScheduleConfig.objects.get', return_value=schedule_config),
            patch('apps.api_automation.executor.execute_run'),
            patch('apps.api_automation.models.ApiAutomationProject.objects.get', return_value=project),
            patch(
                'apps.core.models.EnvironmentConfiguration.objects.get',
                return_value=configuration,
            ) as configuration_get,
            patch('apps.api_automation.models.ApiAutomationRun.objects.create', return_value=run),
            patch('apps.scheduler.task_executor._update_task_stats'),
            patch('apps.scheduler.task_executor._record_api_automation_notification'),
        ):
            result = execute_api_automation_suite(schedule_id=42, is_manual_execution=True)

        configuration_get.assert_called_once_with(id=configuration.id)
        self.assertTrue(result['success'])
        self.assertEqual(result['run_id'], run.id)