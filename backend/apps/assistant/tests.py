from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AgentModelConfig, AssistantSession

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
		first = self.client.post('/api/assistant/config/agent-models/', payload, format='json')
		self.assertEqual(first.status_code, 201)

		payload['name'] = 'Chat Model B'
		second = self.client.post('/api/assistant/config/agent-models/', payload, format='json')
		self.assertEqual(second.status_code, 201)
		self.assertEqual(AgentModelConfig.objects.filter(role='chat', is_active=True).count(), 1)

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
