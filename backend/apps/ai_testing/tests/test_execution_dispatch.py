"""Tests for the unified AI execution dispatch (thread / django-q) and stop/reconcile semantics."""

import os
from datetime import timedelta
from types import SimpleNamespace
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai_testing.execution import dispatch
from apps.ai_testing.models import AICase, AIExecutionRecord, AiProject


class ExecutionDispatchTests(TestCase):
    def _record(self, **overrides):
        fields = {'case_name': 'Dispatch Case', 'status': 'running', 'execution_mode': 'planner_v2', 'logs': ''}
        fields.update(overrides)
        return AIExecutionRecord.objects.create(**fields)

    def test_backend_defaults_to_thread_and_ignores_unknown_values(self):
        with patch.dict(os.environ, {'AI_TESTING_EXECUTION_BACKEND': ''}):
            self.assertEqual(dispatch.execution_backend(), 'thread')
        with patch.dict(os.environ, {'AI_TESTING_EXECUTION_BACKEND': 'django_q'}):
            self.assertEqual(dispatch.execution_backend(), 'django_q')
        with patch.dict(os.environ, {'AI_TESTING_EXECUTION_BACKEND': 'bogus'}):
            self.assertEqual(dispatch.execution_backend(), 'thread')

    def test_django_q_backend_enqueues_with_long_timeout_and_records_task_id(self):
        record = self._record()
        with patch.dict(os.environ, {'AI_TESTING_EXECUTION_BACKEND': 'django_q'}):
            with patch('django_q.tasks.async_task', return_value='q-task-1') as async_task:
                result = dispatch.dispatch_ai_execution(record.id, {'task_description': 'goal'})

        async_task.assert_called_once()
        self.assertEqual(async_task.call_args.args[:2], (dispatch.TASK_PATH, record.id))
        self.assertEqual(async_task.call_args.kwargs['timeout'], dispatch.DEFAULT_TASK_TIMEOUT_SECONDS)
        self.assertEqual(result, {'backend': 'django_q', 'task_id': 'q-task-1'})
        record.refresh_from_db()
        self.assertEqual((record.dispatch_backend, record.dispatch_task_id), ('django_q', 'q-task-1'))

    def test_thread_backend_starts_a_daemon_thread(self):
        record = self._record()
        with patch.dict(os.environ, {'AI_TESTING_EXECUTION_BACKEND': 'thread'}):
            with patch('apps.ai_testing.execution.dispatch.threading.Thread') as thread_cls:
                result = dispatch.dispatch_ai_execution(record.id, {'task_description': 'goal'})

        thread_cls.assert_called_once()
        self.assertTrue(thread_cls.call_args.kwargs['daemon'])
        thread_cls.return_value.start.assert_called_once()
        self.assertEqual(result['backend'], 'thread')
        record.refresh_from_db()
        self.assertEqual(record.dispatch_backend, 'thread')

    def test_execute_ai_record_persists_terminal_status_and_history(self):
        record = self._record()
        history = SimpleNamespace(steps=[], planner_trace={'source': 'stub'}, artifacts=[], cache_stats={'hit': 1})
        with patch('apps.ai_testing.ai_testing.run_full_process_sync', return_value=history) as runner:
            dispatch.execute_ai_record(record.id, {
                'task_description': 'do it', 'execution_mode': 'planner_v2', 'case_mode': 'structured',
                'task_steps': [{'description': 'step'}], 'use_cache': False, 'execution_user_id': 1,
            })

        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs['execution_record_id'], record.id)
        self.assertFalse(runner.call_args.kwargs['use_cache'])
        self.assertFalse(runner.call_args.kwargs['force_replan'])
        record.refresh_from_db()
        self.assertIn(record.status, {'passed', 'failed', 'inconclusive'})
        self.assertIsNotNone(record.end_time)
        self.assertEqual(record.planner_trace, {'source': 'stub'})
        self.assertEqual(record.cache_stats, {'hit': 1})
        self.assertNotIn(record.id, dispatch.STOP_SIGNALS)

    def test_execute_ai_record_preserves_a_stop_issued_from_another_process(self):
        record = self._record()

        def stop_during_run(*args, **kwargs):
            AIExecutionRecord.objects.filter(pk=record.id).update(status='stopped')
            return SimpleNamespace(steps=[], planner_trace={}, artifacts=[], cache_stats={})

        with patch('apps.ai_testing.ai_testing.run_full_process_sync', side_effect=stop_during_run):
            dispatch.execute_ai_record(record.id, {'task_description': 'do it'})

        record.refresh_from_db()
        self.assertEqual(record.status, 'stopped')
        self.assertIn('任务已由用户停止', record.logs)

    def test_execute_ai_record_marks_failure_on_exception(self):
        record = self._record()
        with patch('apps.ai_testing.ai_testing.run_full_process_sync', side_effect=RuntimeError('boom')):
            dispatch.execute_ai_record(record.id, {'task_description': 'do it'})

        record.refresh_from_db()
        self.assertEqual(record.status, 'failed')
        self.assertIn('boom', record.logs)

    def test_environment_bootstrap_failure_is_inconclusive_not_failed(self):
        from apps.ai_testing.runtime.pyui_compat.runner import EnvironmentBootstrapError

        record = self._record()
        with patch('apps.ai_testing.ai_testing.run_full_process_sync', side_effect=EnvironmentBootstrapError('planner_v2 bootstrap could not find login form')):
            dispatch.execute_ai_record(record.id, {'task_description': 'do it'})

        record.refresh_from_db()
        self.assertEqual(record.status, 'inconclusive')
        self.assertIn('被测环境不可用', record.logs)
        self.assertIn('could not find login form', record.logs)

    def test_request_stop_only_affects_running_records(self):
        record = self._record()
        self.assertTrue(dispatch.request_stop(record.id))
        record.refresh_from_db()
        self.assertEqual(record.status, 'stopped')
        self.assertIsNotNone(record.end_time)
        self.assertFalse(dispatch.request_stop(record.id))

    def test_reconcile_marks_only_stale_records_not_owned_by_this_process(self):
        stale = self._record(heartbeat_at=timezone.now() - timedelta(hours=2))
        fresh = self._record(heartbeat_at=timezone.now())
        owned = self._record(heartbeat_at=timezone.now() - timedelta(hours=2))
        dispatch.STOP_SIGNALS[owned.id] = False
        try:
            reconciled = dispatch.reconcile_stale_executions(stale_after_minutes=30)
        finally:
            dispatch.STOP_SIGNALS.pop(owned.id, None)

        self.assertEqual(reconciled, [stale.id])
        stale.refresh_from_db(); fresh.refresh_from_db(); owned.refresh_from_db()
        self.assertEqual(stale.status, 'failed')
        self.assertIn('执行进程已丢失', stale.logs)
        self.assertEqual(fresh.status, 'running')
        self.assertEqual(owned.status, 'running')


class QualityGatePurityTests(TestCase):
    def test_quality_gate_evaluation_does_not_mutate_record_status(self):
        from apps.ai_testing.execution.plan_persistence import persist_execution_plan
        from apps.ai_testing.execution.quality_gate_persistence import evaluate_execution_quality_gate

        record = AIExecutionRecord.objects.create(case_name='Gate Case', status='running')
        persist_execution_plan(record.id, 'goal', [{'description': 'step one'}])

        result = evaluate_execution_quality_gate(record.id)

        self.assertEqual(result.status, 'inconclusive')
        record.refresh_from_db()
        self.assertEqual(record.status, 'running')


class LaunchAndAcceptanceCommandTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_superuser(username='acceptance-admin', password='x', email='a@example.com')
        self.project = AiProject.objects.create(name='Launch Project')
        self.case = AICase.objects.create(
            project=self.project, name='Launch Case', case_number='TC_900', case_mode='structured',
            task_description='1. open page', task_steps=[{'description': 'open page', 'step_mode': 'ai'}],
        )

    def test_launch_case_execution_builds_ui_equivalent_payload(self):
        with patch('apps.ai_testing.execution.dispatch.dispatch_ai_execution') as dispatch_mock:
            record = dispatch.launch_case_execution(self.case, user=self.user, execution_mode='planner_v2', use_cache=False)

        dispatch_mock.assert_called_once()
        record_id, payload = dispatch_mock.call_args.args
        self.assertEqual(record_id, record.id)
        self.assertEqual(record.ai_case_id, self.case.id)
        self.assertEqual(record.status, 'running')
        self.assertEqual(payload['case_mode'], 'structured')
        self.assertEqual(payload['task_steps'], self.case.task_steps)
        self.assertFalse(payload['use_cache'])
        self.assertFalse(payload['force_replan'])
        self.assertFalse(payload['legacy_plan_ignored'])
        self.assertEqual(payload['ai_case_id'], self.case.id)

    def _fake_launch(self, status):
        def launch(case, *, user, execution_mode, use_cache, environment_configuration, force_replan=False):
            return AIExecutionRecord.objects.create(
                ai_case=case, case_name=case.name, status=status, duration=1.5, execution_mode=execution_mode,
            )
        return launch

    def test_run_ai_acceptance_reruns_a_case_after_an_environment_outage(self):
        statuses = iter([('inconclusive', '执行出错: 被测环境不可用，未执行任何步骤。bootstrap'), ('passed', '')])

        def launch(case, *, user, execution_mode, use_cache, environment_configuration, force_replan=False):
            status, logs = next(statuses)
            return AIExecutionRecord.objects.create(
                ai_case=case, case_name=case.name, status=status, duration=1.0, execution_mode=execution_mode, logs=logs,
            )

        out = StringIO()
        with patch('apps.ai_testing.management.commands.run_ai_acceptance.launch_case_execution', side_effect=launch):
            call_command('run_ai_acceptance', cases=str(self.case.id), rounds=1, poll=0.01, stdout=out)

        self.assertIn('ENV RETRY', out.getvalue())
        self.assertIn('SUMMARY passed=1/1', out.getvalue())

    def test_run_ai_acceptance_does_not_rerun_ordinary_inconclusive_results(self):
        with patch('apps.ai_testing.management.commands.run_ai_acceptance.launch_case_execution', side_effect=self._fake_launch('inconclusive')) as launch:
            with self.assertRaises(CommandError):
                call_command('run_ai_acceptance', cases=str(self.case.id), rounds=1, poll=0.01, stdout=StringIO())
        self.assertEqual(launch.call_count, 1)

    def test_run_ai_acceptance_reports_rounds_and_writes_json(self):
        import tempfile
        from pathlib import Path

        out = StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.json'
            with patch('apps.ai_testing.management.commands.run_ai_acceptance.launch_case_execution', side_effect=self._fake_launch('passed')):
                call_command('run_ai_acceptance', cases=str(self.case.id), rounds=2, json=str(report), poll=0.01, stdout=out)
            import json as _json
            summary = _json.loads(report.read_text(encoding='utf-8'))

        self.assertIn('SUMMARY passed=2/2', out.getvalue())
        self.assertEqual((summary['rounds'], summary['runs'], summary['passed']), (2, 2, 2))
        self.assertEqual(summary['results'][0]['case_number'], 'TC_900')

    def test_run_ai_acceptance_fails_when_a_run_does_not_pass(self):
        with patch('apps.ai_testing.management.commands.run_ai_acceptance.launch_case_execution', side_effect=self._fake_launch('inconclusive')):
            with self.assertRaises(CommandError):
                call_command('run_ai_acceptance', project=self.project.id, case_prefix='TC_', poll=0.01, stdout=StringIO())


class PlanContextFingerprintWiringTests(SimpleTestCase):
    def test_initial_plan_is_tagged_with_the_planning_context(self) -> None:
        import inspect
        from apps.ai_testing.execution.dispatch import execute_ai_record
        from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatAgent

        dispatch_source = inspect.getsource(execute_ai_record)
        self.assertIn("step_info.get('type') == 'plan_context'", dispatch_source)
        self.assertIn("context_fingerprint=plan_context['fingerprint']", dispatch_source)
        runner_source = inspect.getsource(PyUICompatAgent.run_full_process)
        self.assertIn("'type': 'plan_context'", runner_source)
        self.assertIn('last_context_fingerprint', runner_source)


class ForceReplanLaunchTests(SimpleTestCase):
    def test_launch_and_execute_carry_the_force_replan_switch(self) -> None:
        import inspect

        self.assertIn("'force_replan': bool(force_replan)", inspect.getsource(dispatch.launch_case_execution))
        self.assertIn("force_replan=bool(payload.get('force_replan', False))", inspect.getsource(dispatch.execute_ai_record))
