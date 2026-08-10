from unittest.mock import call, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.ai_testing.alpha.contracts import SkillTier
from apps.ai_testing.alpha.orchestrator import AlphaOrchestrator
from apps.ai_testing.alpha.skills.catalog import build_phase_one_registry
from apps.ai_testing.alpha.skills.registry import SkillDefinition, SkillRegistry
from apps.ai_testing.models import AlphaRun, AiProject


def _run_handler(_: object, __: dict[str, object]) -> dict[str, object]:
    return {'external_reference': 'not-dispatched-in-test'}


class AlphaOrchestratorTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='alpha-owner', password='test-password')
        self.project = AiProject.objects.create(name='Alpha Project', created_by=self.user)
        self.run = AlphaRun.objects.create(
            project=self.project,
            initiated_by=self.user,
            original_request='List my accessible AI projects',
        )

    @patch('apps.ai_testing.alpha.orchestrator._enqueue_dispatch_intents')
    def test_freeze_queues_only_dependency_ready_read_tasks(self, enqueue_dispatch_intents) -> None:
        orchestrator = AlphaOrchestrator(build_phase_one_registry())
        revision = orchestrator.create_draft_revision(
            self.run.id,
            {
                'tasks': [
                    {'key': 'first', 'skill': 'ai_projects.list', 'arguments': {}, 'depends_on': []},
                    {'key': 'second', 'skill': 'ai_projects.list', 'arguments': {}, 'depends_on': ['first']},
                ]
            },
        )

        with self.captureOnCommitCallbacks(execute=True):
            preparation = orchestrator.freeze_and_prepare_execution(self.run.id, revision.id)

        revision.refresh_from_db()
        self.run.refresh_from_db()
        task_statuses = dict(revision.task_nodes.values_list('task_key', 'status'))
        self.assertEqual(revision.status, 'frozen')
        self.assertEqual(self.run.status, 'executing')
        self.assertEqual(task_statuses, {'first': 'dispatched', 'second': 'pending'})
        self.assertEqual(len(preparation.dispatch_intent_ids), 1)
        self.assertEqual(preparation.approval_request_ids, ())
        enqueue_dispatch_intents.assert_called_once_with(list(preparation.dispatch_intent_ids))

    @patch('apps.ai_testing.alpha.orchestrator._enqueue_dispatch_intents')
    def test_risky_skill_requires_exact_approval_before_dispatch(self, enqueue_dispatch_intents) -> None:
        registry = SkillRegistry()
        registry.register(
            SkillDefinition(
                name='runs.start',
                version='1',
                tier=SkillTier.RUN,
                risky=True,
                arguments=(),
                handler=_run_handler,
            )
        )
        orchestrator = AlphaOrchestrator(registry)
        revision = orchestrator.create_draft_revision(
            self.run.id,
            {'tasks': [{'key': 'start-run', 'skill': 'runs.start', 'arguments': {}, 'depends_on': []}]},
        )

        with self.captureOnCommitCallbacks(execute=True):
            preparation = orchestrator.freeze_and_prepare_execution(self.run.id, revision.id)

        self.run.refresh_from_db()
        task = revision.task_nodes.get(task_key='start-run')
        approval = task.approval_requests.get()
        self.assertEqual(self.run.status, 'awaiting_confirmation')
        self.assertEqual(task.status, 'awaiting_confirmation')
        self.assertEqual(preparation.dispatch_intent_ids, ())
        self.assertEqual(preparation.approval_request_ids, (approval.id,))
        self.assertEqual(approval.arguments_hash, task.arguments_hash)
        enqueue_dispatch_intents.assert_called_once_with([])

    @patch('apps.ai_testing.alpha.orchestrator._enqueue_dispatch_intents')
    def test_approved_risky_task_creates_dispatch_intent(self, enqueue_dispatch_intents) -> None:
        registry = SkillRegistry()
        registry.register(
            SkillDefinition(
                name='runs.start',
                version='1',
                tier=SkillTier.RUN,
                risky=True,
                arguments=(),
                handler=_run_handler,
            )
        )
        orchestrator = AlphaOrchestrator(registry)
        revision = orchestrator.create_draft_revision(
            self.run.id,
            {'tasks': [{'key': 'start-run', 'skill': 'runs.start', 'arguments': {}, 'depends_on': []}]},
        )
        with self.captureOnCommitCallbacks(execute=True):
            preparation = orchestrator.freeze_and_prepare_execution(self.run.id, revision.id)

        approval_id = preparation.approval_request_ids[0]
        with self.captureOnCommitCallbacks(execute=True):
            decision = orchestrator.decide_approval(self.run.id, approval_id, self.user, approve=True)

        self.run.refresh_from_db()
        task = revision.task_nodes.get(task_key='start-run')
        approval = task.approval_requests.get(pk=approval_id)
        self.assertEqual(approval.status, 'approved')
        self.assertEqual(approval.decided_by, self.user)
        self.assertEqual(task.status, 'dispatched')
        self.assertEqual(self.run.status, 'executing')
        self.assertEqual(len(decision.dispatch_intent_ids), 1)
        enqueue_dispatch_intents.assert_has_calls([call([]), call(list(decision.dispatch_intent_ids))])

    @patch('apps.ai_testing.alpha.orchestrator._enqueue_dispatch_intents')
    def test_approval_decision_api_approves_matching_risky_action(self, enqueue_dispatch_intents) -> None:
        registry = SkillRegistry()
        registry.register(
            SkillDefinition(
                name='runs.start',
                version='1',
                tier=SkillTier.RUN,
                risky=True,
                arguments=(),
                handler=_run_handler,
            )
        )
        orchestrator = AlphaOrchestrator(registry)
        revision = orchestrator.create_draft_revision(
            self.run.id,
            {'tasks': [{'key': 'start-run', 'skill': 'runs.start', 'arguments': {}, 'depends_on': []}]},
        )
        with self.captureOnCommitCallbacks(execute=True):
            preparation = orchestrator.freeze_and_prepare_execution(self.run.id, revision.id)

        client = APIClient()
        client.force_authenticate(self.user)
        approval_id = preparation.approval_request_ids[0]
        with patch('apps.ai_testing.alpha.views.build_phase_one_registry', return_value=registry):
            with self.captureOnCommitCallbacks(execute=True):
                response = client.post(
                    f'/api/ai-testing/alpha/runs/{self.run.id}/approvals/{approval_id}/decision/',
                    {'approve': True},
                    format='json',
                )

        self.run.refresh_from_db()
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.data['approved'])
        self.assertEqual(self.run.status, 'executing')
        self.assertEqual(revision.task_nodes.get(task_key='start-run').status, 'dispatched')