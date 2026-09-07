from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from apps.core.llm import LLMCallContext, OpenAICompatibleClient
from apps.ui_automation.views_config import AIIntelligentModeConfigViewSet


class OpenAICompatibleClientTests(SimpleTestCase):
    def test_call_context_exposes_business_origin(self) -> None:
        context = LLMCallContext(
            component='alpha_agent',
            operation='planning',
            execution_id=42,
        )

        self.assertEqual(
            context.log_prefix(),
            '[component=alpha_agent operation=planning execution_id=42]',
        )

    def test_gemini_openai_compatible_url_does_not_append_v1(self) -> None:
        config = type(
            'ConfigStub',
            (),
            {
                'model_type': 'gemini',
                'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
            },
        )()

        url = OpenAICompatibleClient.build_chat_completions_url(config)

        self.assertEqual(
            url,
            'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
        )

    def test_existing_google_gemini_config_uses_gemini_endpoint(self) -> None:
        config = type(
            'ConfigStub',
            (),
            {
                'model_type': 'google_gemini',
                'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
            },
        )()

        url = OpenAICompatibleClient.build_chat_completions_url(config)

        self.assertEqual(
            url,
            'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
        )

    def test_standard_openai_compatible_url_keeps_v1_behavior(self) -> None:
        config = type(
            'ConfigStub',
            (),
            {
                'model_type': 'deepseek',
                'base_url': 'https://api.deepseek.com',
            },
        )()

        url = OpenAICompatibleClient.build_chat_completions_url(config)

        self.assertEqual(url, 'https://api.deepseek.com/v1/chat/completions')

    def test_standard_model_uses_configured_generation_parameters(self) -> None:
        config = type(
            'ConfigStub',
            (),
            {
                'model_type': 'deepseek',
                'model_name': 'deepseek-chat',
                'temperature': 0.3,
                'top_p': 0.8,
            },
        )()

        payload = OpenAICompatibleClient.build_request_payload(config, [], 1234, False)

        self.assertEqual(payload['max_tokens'], 1234)
        self.assertEqual(payload['temperature'], 0.3)
        self.assertEqual(payload['top_p'], 0.8)
        self.assertNotIn('max_completion_tokens', payload)

    def test_reasoning_model_uses_supported_generation_parameters(self) -> None:
        config = type(
            'ConfigStub',
            (),
            {
                'model_type': 'openai',
                'model_name': 'o3-mini',
                'temperature': 0.3,
                'top_p': 0.8,
            },
        )()

        payload = OpenAICompatibleClient.build_request_payload(config, [], 2345, False)

        self.assertEqual(payload['max_completion_tokens'], 2345)
        self.assertNotIn('max_tokens', payload)
        self.assertNotIn('temperature', payload)
        self.assertNotIn('top_p', payload)

    def test_kimi_model_uses_required_temperature(self) -> None:
        config = type(
            'ConfigStub',
            (),
            {
                'model_type': 'other',
                'model_name': 'kimi-k2.5',
                'temperature': 0.3,
                'top_p': 0.8,
            },
        )()

        payload = OpenAICompatibleClient.build_request_payload(config, [], 3456, False)

        self.assertEqual(payload['temperature'], 1.0)

    def test_ai_mode_config_preserves_gemini_openai_compatible_url(self) -> None:
        viewset = AIIntelligentModeConfigViewSet()

        url = viewset._resolve_base_url(
            'gemini',
            'https://generativelanguage.googleapis.com/v1beta/openai/',
        )

        self.assertEqual(url, 'https://generativelanguage.googleapis.com/v1beta/openai')

    def test_ai_mode_config_validates_generation_parameters(self) -> None:
        parameters = AIIntelligentModeConfigViewSet._validated_model_parameters({
            'max_tokens': 8192,
            'temperature': 1.2,
            'top_p': 0.95,
        })

        self.assertEqual(parameters, {
            'max_tokens': 8192,
            'temperature': 1.2,
            'top_p': 0.95,
        })

        with self.assertRaises(ValidationError):
            AIIntelligentModeConfigViewSet._validated_model_parameters({'top_p': 1.1})

    def test_ai_mode_connection_payload_adapts_reasoning_model_parameters(self) -> None:
        payload = AIIntelligentModeConfigViewSet()._build_test_payload(
            'executor_text',
            'gpt-5-mini',
            max_tokens=8192,
            temperature=0.4,
            top_p=0.8,
        )

        self.assertEqual(payload['max_completion_tokens'], 8192)
        self.assertNotIn('max_tokens', payload)
        self.assertNotIn('temperature', payload)
        self.assertNotIn('top_p', payload)