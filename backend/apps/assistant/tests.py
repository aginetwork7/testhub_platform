from datetime import timedelta
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AgentModelConfig, AgentPromptConfig, AssistantSession
from apps.requirement_analysis.models import AIModelConfig

class AgentModelConfigApiTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(username='agent-config-owner', password='test-password')
		self.client = APIClient()
		self.client.force_authenticate(self.user)

	def test_active_config_is_exclusive_per_role(self):
		payload = {
			'name': 'Chat Model A',
			'role': 'chat',
			'model_type': 'other',
			'api_key': 'test-key',
			'base_url': 'https://chat.example.test',
			'model_name': 'chat-model',
			'is_active': True,
		}
		first = self.client.post('/api/ai-agent/models/', payload, format='json')
		self.assertEqual(first.status_code, 201)

		payload['name'] = 'Chat Model B'
		second = self.client.post('/api/ai-agent/models/', payload, format='json')
		self.assertEqual(second.status_code, 201)
		self.assertEqual(AgentModelConfig.objects.filter(role='chat', is_active=True).count(), 1)

	def test_alpha_model_roles_are_valid_and_independently_active(self):
		payload = {
			'name': 'Alpha Planner',
			'role': 'alpha_planner',
			'model_type': 'other',
			'api_key': 'test-key',
			'base_url': 'https://planner.example.test',
			'model_name': 'planner-model',
			'is_active': True,
		}

		planner = self.client.post('/api/ai-agent/models/', payload, format='json')

		payload.update(name='Alpha Reflection', role='alpha_reflection', model_name='reflection-model')
		reflection = self.client.post('/api/ai-agent/models/', payload, format='json')

		self.assertEqual(planner.status_code, 201)
		self.assertEqual(reflection.status_code, 201)
		self.assertTrue(AgentModelConfig.objects.get(role='alpha_planner').is_active)
		self.assertTrue(AgentModelConfig.objects.get(role='alpha_reflection').is_active)

	def test_legacy_alpha_configs_are_copied_without_collapsing_duplicates(self):
		created_at = timezone.now() - timedelta(days=2)
		updated_at = timezone.now() - timedelta(days=1)
		for name, role in (
			('Legacy Alpha Planner A', 'alpha_planner'),
			('Legacy Alpha Planner B', 'alpha_planner'),
			('Legacy Alpha Reflection', 'alpha_reflection'),
		):
			legacy_config = AIModelConfig.objects.create(
				name=name,
				role=role,
				model_type='other',
				api_key='legacy-key',
				base_url='https://legacy.example.test',
				model_name='legacy-model',
				max_tokens=2048,
				temperature=0.2,
				top_p=0.4,
				is_active=False,
				created_by=self.user,
			)
			AIModelConfig.objects.filter(pk=legacy_config.pk).update(
				created_at=created_at,
				updated_at=updated_at,
			)

		migration_module = import_module('apps.assistant.migrations.0008_add_alpha_agent_model_roles')
		migration_module.migrate_legacy_alpha_configurations(apps, None)

		copied_configs = AgentModelConfig.objects.filter(name__startswith='Legacy Alpha').order_by('name')
		self.assertEqual(copied_configs.count(), 3)
		self.assertEqual(list(copied_configs.values_list('role', flat=True)), ['alpha_planner', 'alpha_planner', 'alpha_reflection'])
		for copied_config in copied_configs:
			self.assertEqual(copied_config.api_key, 'legacy-key')
			self.assertEqual(copied_config.max_tokens, 2048)
			self.assertEqual(copied_config.temperature, 0.2)
			self.assertEqual(copied_config.top_p, 0.4)
			self.assertEqual(copied_config.created_at, created_at)
			self.assertEqual(copied_config.updated_at, updated_at)

	def test_active_prompt_is_exclusive_per_role(self):
		payload = {
			'name': 'Chat Prompt A',
			'role': 'chat',
			'content': 'Answer as a testing assistant.',
			'is_active': True,
		}
		first = self.client.post('/api/ai-agent/prompts/', payload, format='json')
		self.assertEqual(first.status_code, 201)

		payload['name'] = 'Chat Prompt B'
		second = self.client.post('/api/ai-agent/prompts/', payload, format='json')
		self.assertEqual(second.status_code, 201)
		self.assertEqual(AgentPromptConfig.objects.filter(role='chat', is_active=True).count(), 1)

	@patch('apps.assistant.direct_views.requests.post')
	def test_chat_model_streams_openai_compatible_sse(self, request_post):
		AgentModelConfig.objects.create(
			name='Chat Model',
			role='chat',
			model_type='other',
			api_key='test-key',
			base_url='https://chat.example.test',
			model_name='chat-model',
			created_by=self.user,
			is_active=True,
		)
		AgentPromptConfig.objects.create(
			name='Chat Prompt',
			role='chat',
			content='Answer as a testing assistant.',
			created_by=self.user,
			is_active=True,
		)
		session = AssistantSession.objects.create(user=self.user, session_id='chat-session', title='Chat')

		class UpstreamResponse:
			def raise_for_status(self):
				return None

			def iter_lines(self, decode_unicode=True):
				return iter([
					'data: {"choices":[{"delta":{"reasoning_content":"分析"}}]}',
					'data: {"choices":[{"delta":{"content":"你好"}}]}',
					'data: {"usage":{"total_tokens":3}}',
					'data: [DONE]',
				])

			def close(self):
				return None

		request_post.return_value = UpstreamResponse()

		response = self.client.post(
			'/api/assistant/chat/send_message_stream/',
			{'session_id': session.session_id, 'message': '你好', 'thinking_mode': True},
			format='json',
		)
		payload = b''.join(response.streaming_content).decode('utf-8')

		self.assertEqual(response.status_code, 200)
		self.assertIn('"type": "thinking"', payload)
		self.assertIn('"type": "chunk"', payload)
		self.assertIn('"type": "done"', payload)
