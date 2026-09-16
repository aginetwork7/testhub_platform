"""Experience learning loop: pending experiences auto-verify after repeated independent verification."""

from django.test import TestCase

from apps.ai_testing.models import AIExecutionExperience, AiProject
from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatAgent


class ExperienceLearningTests(TestCase):
    def setUp(self):
        self.project = AiProject.objects.create(name='Learning Project')
        self.agent = PyUICompatAgent(case_name='Learning_Case', execution_user_id=1, ai_project_id=self.project.id)
        self.step = {'index': 1, 'description': 'Click the Team option', 'assertions': [{'assert_kind': 'element_state', 'operator': 'exists'}]}
        self.actions = [{'action': 'click', 'selector': '#team'}]

    def _experience(self):
        return AIExecutionExperience.objects.get(project=self.project)

    def test_pending_experience_is_verified_after_repeated_independent_success(self):
        self.agent._upsert_experience(self.step, self.actions, {})
        first = self._experience()
        self.assertEqual((first.status, first.success_count), ('pending', 1))
        self.assertIsNone(self.agent._find_experience_actions(self.step, {}))

        self.agent._upsert_experience(self.step, self.actions, {})
        second = self._experience()
        self.assertEqual((second.status, second.success_count), ('verified', 2))
        self.assertGreaterEqual(second.confidence, 0.8)
        self.assertEqual(second.review_status, 'pending')
        self.assertEqual(self.agent._find_experience_actions(self.step, {}), self.actions)

    def test_changed_actions_restart_the_verification_count(self):
        self.agent._upsert_experience(self.step, self.actions, {})
        self.agent._upsert_experience(self.step, [{'action': 'click', 'selector': '#other'}], {})
        experience = self._experience()
        self.assertEqual((experience.status, experience.success_count), ('pending', 1))
        self.assertEqual(experience.action_sequence, [{'action': 'click', 'selector': '#other'}])

    def test_invalidated_experience_is_revived_as_pending_when_reverified(self):
        self.agent._upsert_experience(self.step, self.actions, {})
        self.agent._upsert_experience(self.step, self.actions, {})
        self.agent._invalidate_experience_sync(self.step, {})
        self.assertEqual(self._experience().status, 'invalid')

        self.agent._upsert_experience(self.step, self.actions, {})
        revived = self._experience()
        self.assertEqual((revived.status, revived.success_count), ('pending', 1))

    def test_confirmed_only_policy_ignores_auto_verified_experience(self):
        from types import SimpleNamespace

        self.agent._upsert_experience(self.step, self.actions, {})
        self.agent._upsert_experience(self.step, self.actions, {})
        self.assertEqual(self._experience().status, 'verified')
        self.assertEqual(self.agent._find_experience_actions(self.step, {}), self.actions)

        self.agent.environment_configuration = SimpleNamespace(runtime_settings={'ai_testing_browser': {'experience_reuse_policy': 'confirmed_only'}})
        self.assertIsNone(self.agent._find_experience_actions(self.step, {}))
        AIExecutionExperience.objects.filter(project=self.project).update(review_status='confirmed')
        self.assertEqual(self.agent._find_experience_actions(self.step, {}), self.actions)
