from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.ai_testing.alpha.planning import AlphaPlannerService
from apps.ai_testing.alpha.tasks import enqueue_alpha_planning
from apps.ai_testing.models import AITestPromptConfig, AlphaRun, AiProject
from apps.assistant.models import AgentModelConfig, AgentPromptConfig


class AlphaPlanningTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='planner-owner', password='test-password')
        self.project = AiProject.objects.create(name='Planner Project', created_by=self.user)
        self.run = AlphaRun.objects.create(
            project=self.project,
            initiated_by=self.user,
            original_request='List accessible AI projects',
        )
        AgentModelConfig.objects.create(
            name='Alpha Planner',
            model_type='other',
            role='alpha_planner',
            base_url='https://planner.example.test',
            model_name='planner-test-model',
            created_by=self.user,
            is_active=True,
        )
        AgentPromptConfig.objects.create(
            name='Alpha Agent Prompt',
            role='agent',
            content='Plan only with registered skills.',
            created_by=self.user,
            is_active=True,
        )

    @patch(
        'apps.ai_testing.alpha.planning.OpenAICompatibleClient.complete',
        new_callable=AsyncMock,
    )
    def test_planner_response_creates_validated_draft_revision(self, model_call) -> None:
        model_call.return_value = {
            'choices': [
                {
                    'message': {
                        'content': (
                            '{"tasks":[{"key":"list-projects","skill":"ai_projects.list",'
                            '"arguments":{},"depends_on":[],"parent":null}]}'
                        )
                    }
                }
            ]
        }

        revision_id = async_to_sync(AlphaPlannerService().create_draft_revision)(self.run.id)

        revision = self.run.revisions.get(pk=revision_id)
        self.run.refresh_from_db()
        self.assertEqual(revision.status, 'draft')
        self.assertEqual(revision.task_nodes.get().skill_name, 'ai_projects.list')
        self.assertEqual(self.run.active_revision_id, revision.id)
        self.assertEqual(self.run.round_count, 1)
        model_call.assert_awaited_once()
        self.assertEqual(model_call.await_args.args[0].role, 'alpha_planner')
        context = model_call.await_args.kwargs['context']
        self.assertEqual(context.component, 'alpha_agent')
        self.assertEqual(context.operation, 'planning')
        self.assertEqual(context.execution_id, self.run.id)

    @patch('apps.ai_testing.alpha.views.enqueue_alpha_planning', return_value='django-q-task-id')
    def test_plan_api_queues_planning_and_records_task_id(self, enqueue_alpha_planning) -> None:
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.post(f'/api/ai-testing/alpha/runs/{self.run.id}/plan/', {}, format='json')

        self.run.refresh_from_db()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['task_id'], 'django-q-task-id')
        self.assertEqual(self.run.status, 'planning')
        enqueue_alpha_planning.assert_called_once_with(self.run.id)

    @patch('apps.ai_testing.alpha.tasks.async_task', return_value='django-q-task-id')
    def test_enqueue_planning_persists_django_q_task_id(self, async_task) -> None:
        self.run.status = 'planning'
        self.run.save(update_fields=['status'])

        task_id = enqueue_alpha_planning(self.run.id)

        self.run.refresh_from_db()
        self.assertEqual(task_id, 'django-q-task-id')
        self.assertEqual(self.run.planner_task_id, 'django-q-task-id')
        async_task.assert_called_once_with(
            'apps.ai_testing.alpha.tasks.process_alpha_planning',
            self.run.id,
            timeout=900,
            retry=60,
        )

    def test_terminal_alpha_run_can_be_deleted(self) -> None:
        self.run.status = 'completed'
        self.run.save(update_fields=['status'])
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.delete(f'/api/ai-testing/alpha/runs/{self.run.id}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(AlphaRun.objects.filter(id=self.run.id).exists())

    def test_active_alpha_run_cannot_be_deleted(self) -> None:
        self.run.status = 'executing'
        self.run.save(update_fields=['status'])
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.delete(f'/api/ai-testing/alpha/runs/{self.run.id}/')

        self.assertEqual(response.status_code, 409)
        self.assertTrue(AlphaRun.objects.filter(id=self.run.id).exists())

    def test_planner_vision_default_prompt_is_seeded(self) -> None:
        prompt = AITestPromptConfig.objects.get(prompt_type='planner_vision', is_active=True)

        self.assertIn('single-step observe-reason-act-verify loop', prompt.content)
        self.assertIn('Resolve blocking state first.', prompt.content)
        self.assertIn('Fail closed on ambiguity.', prompt.content)
        self.assertNotIn('camera', prompt.content.lower())
        self.assertNotIn('playback', prompt.content.lower())