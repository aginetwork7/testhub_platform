from django.test import SimpleTestCase

from apps.ai_testing.ai_agent import BrowserAgent, HermesAgent, PyUICompatAgent, get_agent_class


class AIAgentRoutingTests(SimpleTestCase):
    def test_text_mode_hybrid_steps_use_pyui_compat_agent(self) -> None:
        agent_class = get_agent_class(
            execution_mode='text',
            case_mode='hybrid',
            task_steps=[{'step_mode': 'ai', 'description': '示例步骤'}],
        )

        self.assertIs(agent_class, PyUICompatAgent)

    def test_text_mode_freeform_keeps_browser_agent(self) -> None:
        agent_class = get_agent_class(
            execution_mode='text',
            case_mode='freeform',
            task_steps=[],
        )

        self.assertIs(agent_class, BrowserAgent)

    def test_hermes_mode_keeps_hermes_agent(self) -> None:
        agent_class = get_agent_class(
            execution_mode='hermes',
            case_mode='hybrid',
            task_steps=[{'step_mode': 'ai', 'description': '示例步骤'}],
        )

        self.assertIs(agent_class, HermesAgent)