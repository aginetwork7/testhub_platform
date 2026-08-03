from django.test import SimpleTestCase

from apps.requirement_analysis.models import AIModelService
from apps.ui_automation.views_config import AIIntelligentModeConfigViewSet


class AIModelServiceUrlTests(SimpleTestCase):
    def test_gemini_openai_compatible_url_does_not_append_v1(self) -> None:
        config = type(
            'ConfigStub',
            (),
            {
                'model_type': 'gemini',
                'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
            },
        )()

        url = AIModelService._build_chat_completions_url(config)

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

        url = AIModelService._build_chat_completions_url(config)

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

        url = AIModelService._build_chat_completions_url(config)

        self.assertEqual(url, 'https://api.deepseek.com/v1/chat/completions')

    def test_ai_mode_config_preserves_gemini_openai_compatible_url(self) -> None:
        viewset = AIIntelligentModeConfigViewSet()

        url = viewset._resolve_base_url(
            'gemini',
            'https://generativelanguage.googleapis.com/v1beta/openai/',
        )

        self.assertEqual(url, 'https://generativelanguage.googleapis.com/v1beta/openai')