import asyncio

from django.test import TransactionTestCase

from apps.ai_testing.models import AIExecutionExperience, AiProject
from apps.ai_testing.runtime.pyui_compat import PyUICompatAgent


class ExperienceRevalidationTests(TransactionTestCase):
    def test_successful_revalidation_persists_current_audit(self) -> None:
        project = AiProject.objects.create(name='Experience Project')
        agent = PyUICompatAgent(ai_project_id=project.id, execution_user_id=1)
        step = {'index': 1, 'description': 'Verify state', 'assertions': []}
        agent._cache_context_by_step[agent._step_context_key(step)] = {'fingerprint': 'page'}
        experience = AIExecutionExperience.objects.create(
            project=project, step_description='Verify state', intent_hash=agent._intent_hash(step),
            page_fingerprint='page', permission_fingerprint=agent._permission_fingerprint(),
            assertion_contract_hash=agent._assertion_contract_hash(step), status='verified',
        )

        asyncio.run(agent._record_successful_revalidation(step, {'plan_revision': 2, 'attempt_number': 3, 'evidence_hashes': ['a' * 64]}))
        experience.refresh_from_db()

        self.assertEqual(experience.last_verified_plan_revision, 2)
        self.assertEqual(experience.last_verified_attempt, 3)
        self.assertEqual(experience.last_verified_evidence_hashes, ['a' * 64])

    def test_failed_revalidation_does_not_replace_existing_audit(self) -> None:
        project = AiProject.objects.create(name='Preserved Experience Project')
        experience = AIExecutionExperience.objects.create(
            project=project, step_description='Verify state', intent_hash='intent', page_fingerprint='page',
            permission_fingerprint='permission', assertion_contract_hash='contract', status='verified',
            last_verified_plan_revision=1, last_verified_attempt=1, last_verified_evidence_hashes=['old-hash'],
        )

        self.assertFalse(PyUICompatAgent._assertions_are_verified(['failed']))
        experience.refresh_from_db()

        self.assertEqual(experience.last_verified_plan_revision, 1)
        self.assertEqual(experience.last_verified_attempt, 1)
        self.assertEqual(experience.last_verified_evidence_hashes, ['old-hash'])