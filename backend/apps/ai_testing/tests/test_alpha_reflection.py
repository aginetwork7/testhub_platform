from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai_testing.alpha.orchestrator import AlphaOrchestrator
from apps.ai_testing.alpha.reflection import AlphaReflectionService, ReflectionVerdict
from apps.ai_testing.alpha.skills.catalog import build_phase_one_registry
from apps.ai_testing.alpha.tasks import process_alpha_reflection
from apps.ai_testing.models import AlphaRound, AlphaRun, AiProject
from apps.assistant.models import AgentModelConfig, AgentPromptConfig


class AlphaReflectionTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='reflection-owner', password='test-password')
        project = AiProject.objects.create(name='Reflection Project', created_by=self.user)
        self.run = AlphaRun.objects.create(
            project=project,
            initiated_by=self.user,
            original_request='List accessible AI projects',
            status='executing',
        )
        orchestrator = AlphaOrchestrator(build_phase_one_registry())
        self.revision = orchestrator.create_draft_revision(
            self.run.id,
            {'tasks': [{'key': 'list-projects', 'skill': 'ai_projects.list', 'arguments': {}, 'depends_on': []}]},
        )
        self.revision.status = 'frozen'
        self.revision.save(update_fields=['status'])
        task = self.revision.task_nodes.get()
        task.status = 'succeeded'
        task.evidence = {'projects': []}
        task.save(update_fields=['status', 'evidence'])
        self.run.active_revision = self.revision
        self.run.status = 'reflecting'
        self.run.save(update_fields=['active_revision', 'status'])
        AgentModelConfig.objects.create(
            name='Alpha Reflection',
            model_type='other',
            role='alpha_reflection',
            base_url='https://reflection.example.test',
            model_name='reflection-test-model',
            created_by=self.user,
            is_active=True,
        )
        AgentPromptConfig.objects.create(
            name='Alpha Agent Prompt',
            role='agent',
            content='Reflect only from supplied evidence.',
            created_by=self.user,
            is_active=True,
        )

    @patch(
        'apps.ai_testing.alpha.reflection.OpenAICompatibleClient.complete',
        new_callable=AsyncMock,
    )
    def test_reflection_uses_dedicated_reflection_model(self, model_call) -> None:
        model_call.return_value = {
            'choices': [{'message': {'content': '{"verdict":"pass","unmet_criteria":[]}'}}]
        }

        verdict = async_to_sync(AlphaReflectionService().reflect_revision)(self.revision.id)

        self.assertEqual(verdict, ReflectionVerdict(verdict='pass', unmet_criteria=()))
        self.assertEqual(model_call.await_args.args[0].role, 'alpha_reflection')
        context = model_call.await_args.kwargs['context']
        self.assertEqual(context.component, 'alpha_agent')
        self.assertEqual(context.operation, 'reflection')
        self.assertEqual(context.execution_id, self.run.id)

    @patch(
        'apps.ai_testing.alpha.tasks.AlphaReflectionService.reflect_revision',
        new_callable=AsyncMock,
    )
    def test_pass_verdict_completes_run_and_persists_round(self, reflect_revision) -> None:
        reflect_revision.return_value = ReflectionVerdict(verdict='pass', unmet_criteria=())

        process_alpha_reflection(self.revision.id)

        self.run.refresh_from_db()
        round_artifact = AlphaRound.objects.get(revision=self.revision)
        self.assertEqual(self.run.status, 'completed')
        self.assertEqual(self.run.final_output, {'verdict': 'pass', 'unmet_criteria': []})
        self.assertEqual(round_artifact.reflection_verdict, {'verdict': 'pass', 'unmet_criteria': []})

    @patch('apps.ai_testing.alpha.tasks.enqueue_alpha_planning', return_value='planner-task-id')
    @patch(
        'apps.ai_testing.alpha.tasks.AlphaReflectionService.reflect_revision',
        new_callable=AsyncMock,
    )
    def test_replan_verdict_queues_successor_planning(self, reflect_revision, enqueue_alpha_planning) -> None:
        reflect_revision.return_value = ReflectionVerdict(
            verdict='replan',
            unmet_criteria=('Project list must include the requested project.',),
        )

        with self.captureOnCommitCallbacks(execute=True):
            process_alpha_reflection(self.revision.id)

        self.run.refresh_from_db()
        round_artifact = AlphaRound.objects.get(revision=self.revision)
        self.assertEqual(self.run.status, 'planning')
        self.assertEqual(
            round_artifact.reflection_verdict['unmet_criteria'],
            ['Project list must include the requested project.'],
        )
        enqueue_alpha_planning.assert_called_once_with(self.run.id)