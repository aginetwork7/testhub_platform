import unittest
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.ai_testing.execution.assertion_persistence import evaluate_step_assertions
from apps.ai_testing.execution.plan_persistence import persist_bound_step, persist_execution_plan, persist_replanned_step
from apps.ai_testing.execution.quality_gate import evaluate_quality_gate
from apps.ai_testing.execution.quality_gate_persistence import evaluate_execution_quality_gate
from apps.ai_testing.execution.runtime_persistence import persist_step_attempt
from apps.ai_testing.models import AIExecutionRecord
from apps.ai_testing.views import AIExecutionRecordViewSet


class QualityGateTests(unittest.TestCase):
    def test_empty_plan_is_inconclusive(self) -> None:
        result = evaluate_quality_gate([], [])

        self.assertEqual(result.status, 'inconclusive')

    def test_missing_required_assertion_is_inconclusive(self) -> None:
        result = evaluate_quality_gate([
            {'id': 'open-dashboard', 'status': 'completed'},
        ], [])

        self.assertEqual(result.status, 'inconclusive')
        self.assertEqual(result.missing_assertion_step_ids, ('open-dashboard',))

    def test_failed_required_assertion_fails_run(self) -> None:
        result = evaluate_quality_gate(
            [{'id': 'open-dashboard', 'status': 'completed'}],
            [{'id': 'assert-dashboard', 'step_id': 'open-dashboard', 'status': 'failed'}],
        )

        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.failed_assertion_ids, ('assert-dashboard',))

    def test_invalid_evidence_is_inconclusive(self) -> None:
        result = evaluate_quality_gate(
            [{'id': 'open-dashboard', 'status': 'completed'}],
            [{'id': 'assert-dashboard', 'step_id': 'open-dashboard', 'status': 'invalid_evidence'}],
        )

        self.assertEqual(result.status, 'inconclusive')
        self.assertEqual(result.inconclusive_assertion_ids, ('assert-dashboard',))

    def test_verified_required_assertion_allows_pass(self) -> None:
        result = evaluate_quality_gate(
            [{'id': 'open-dashboard', 'status': 'completed'}],
            [{'id': 'assert-dashboard', 'step_id': 'open-dashboard', 'status': 'passed'}],
        )

        self.assertEqual(result.status, 'passed')


class ResourceEvidenceQualityGateTests(TestCase):
    def test_resource_evidence_assertions_pass_quality_gate(self) -> None:
        cases = (
            ('api_resource', {'resource_type': 'alert_event'}, {'value': 'event-123'}, ['api_response'], {'type': 'api_response', 'resource_id': 'event-123'}),
            ('field_value', {'field': 'resource.state'}, {'value': 'created'}, ['structured_value'], {'type': 'structured_value', 'value': 'created'}),
            ('absence', {'resource': 'temporary-alert'}, {'value': False}, ['absence_check'], {'type': 'absence_check', 'exists': False}),
        )
        for assert_kind, target, expected, evidence_requirements, artifact in cases:
            with self.subTest(assert_kind=assert_kind):
                record = AIExecutionRecord.objects.create(case_name=f'{assert_kind} evidence')
                persist_execution_plan(
                    record.id,
                    'Verify resource evidence',
                    [{
                        'id': 'verify-resource',
                        'description': 'Verify resource evidence',
                        'assertions': [{
                            'action': 'assert',
                            'assert_kind': assert_kind,
                            'target': target,
                            'operator': 'equals',
                            'expected': expected,
                            'evidence_requirements': evidence_requirements,
                        }],
                    }],
                )
                persist_step_attempt(
                    record.id,
                    1,
                    {'action': 'create', 'executor': 'data_factory'},
                    {},
                    'completed',
                    '',
                    'environment',
                    'permission',
                    [artifact],
                )

                self.assertEqual(evaluate_step_assertions(record.id, 1), ['passed'])
                self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'passed')

                audit = AIExecutionRecordViewSet()._execution_audit_summary(record)

                self.assertEqual(audit['plan_revision'], 1)
                self.assertEqual(audit['quality_gate']['status'], 'passed')
                self.assertEqual(audit['steps'][0]['assertions'][0]['status'], 'passed')
                self.assertEqual(audit['steps'][0]['attempts'][0]['evidence'][0]['artifact_type'], artifact['type'])

    def test_replan_creates_immutable_revision_and_keeps_verified_predecessor(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Replanned execution')
        assertion = {
            'action': 'assert',
            'assert_kind': 'text',
            'target': {'page': 'current'},
            'operator': 'contains',
            'expected': {'value': 'Ready'},
            'evidence_requirements': ['dom_snapshot'],
        }
        persist_execution_plan(record.id, 'Verify states', [
            {'id': 'first', 'description': 'Verify first state', 'assertions': [assertion]},
            {'id': 'second', 'description': 'Verify second state', 'assertions': [assertion]},
        ])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [
            {'type': 'dom_snapshot', 'text': 'Ready'},
        ])
        self.assertEqual(evaluate_step_assertions(record.id, 1), ['passed'])

        revision = persist_replanned_step(
            record.id,
            2,
            {'action': 'click'},
            'ValueError: target unavailable',
            [{'action': 'assert', 'assert_kind': 'text'}],
        )

        self.assertEqual(revision.revision_number, 2)
        self.assertEqual(revision.steps.get(display_order=1).status, 'verified')
        self.assertEqual(revision.steps.get(display_order=1).attempts.count(), 1)
        self.assertEqual(revision.plan['steps'][1]['source']['replan']['failed_action'], {'action': 'click'})

        audit = AIExecutionRecordViewSet()._execution_audit_summary(record)

        self.assertEqual([item['revision_number'] for item in audit['revision_history']], [1, 2])
        self.assertEqual(audit['revision_history'][1]['reason'], 'replan_step_2_from_1')

    def test_replan_keeps_completed_predecessor_without_required_assertions(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Action-only predecessor')
        assertion = {
            'action': 'assert', 'assert_kind': 'text', 'target': {'page': 'current'},
            'operator': 'contains', 'expected': {'value': 'Ready'},
            'evidence_requirements': ['dom_snapshot'],
        }
        persist_execution_plan(record.id, 'Complete action then verify', [
            {'id': 'select', 'description': 'Select value', 'verification_required': False, 'assertions': []},
            {'id': 'verify', 'description': 'Verify value', 'assertions': [assertion]},
        ])
        persist_step_attempt(
            record.id, 1, {'action': 'click'}, {}, 'completed', '', 'environment', 'permission',
            [{'type': 'dom_snapshot', 'text': 'Selected'}],
        )

        revision = persist_replanned_step(
            record.id, 2, {'action': 'assert'}, 'Target unavailable', [{'action': 'assert'}],
        )

        predecessor = revision.steps.get(display_order=1)
        self.assertEqual(predecessor.status, 'action_completed')
        self.assertEqual(predecessor.attempts.count(), 1)

    def test_binding_revision_preserves_semantic_target(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Bound assertion')
        assertion = {'action': 'assert', 'assert_kind': 'element_state', 'target': {'locator': 'new alert'}, 'operator': 'exists', 'expected': {'value': True}, 'evidence_requirements': ['element_state']}
        persist_execution_plan(record.id, 'Locate alert', [{'id': 'alert', 'description': 'Locate alert', 'assertions': [assertion]}])

        revision = persist_bound_step(record.id, 1, [{'assertion_index': 1, 'locator': '[data-testid="alert-row"]', 'selection_basis': 'first_visible'}])

        bound = revision.steps.get(display_order=1).assertions[0]
        self.assertEqual(revision.reason, 'binding_step_1_from_1')
        self.assertEqual(bound['target']['locator'], '[data-testid="alert-row"]')
        self.assertEqual(bound['target']['intent'], 'new alert')

        rebound_revision = persist_bound_step(record.id, 1, [{'assertion_index': 1, 'locator': '[data-testid="new-alert-row"]'}])

        rebound = rebound_revision.steps.get(display_order=1).assertions[0]
        self.assertEqual(rebound['target']['locator'], '[data-testid="new-alert-row"]')
        self.assertEqual(rebound['target']['intent'], 'new alert')

    def test_invalid_evidence_hash_is_inconclusive_at_quality_gate(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Invalid evidence')
        assertion = {
            'action': 'assert', 'assert_kind': 'text', 'target': {'page': 'current'},
            'operator': 'contains', 'expected': {'value': 'Ready'},
            'evidence_requirements': ['dom_snapshot'],
        }
        persist_execution_plan(record.id, 'Verify evidence', [{'id': 'verify', 'description': 'Verify evidence', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'dom_snapshot', 'text': 'Ready'}])
        artifact = record.plan_revisions.latest('revision_number').steps.get(display_order=1).attempts.get().evidence_artifacts.get()
        artifact.content_hash = 'invalid'
        artifact.save(update_fields=['content_hash'])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['invalid_evidence'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'inconclusive')

    def test_tampered_evidence_permission_is_invalid(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Tampered permission')
        assertion = {'action': 'assert', 'assert_kind': 'text', 'target': {'page': 'current'}, 'operator': 'contains', 'expected': {'value': 'Ready'}, 'evidence_requirements': ['dom_snapshot']}
        persist_execution_plan(record.id, 'Verify evidence', [{'id': 'verify', 'description': 'Verify evidence', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'dom_snapshot', 'text': 'Ready'}])
        artifact = record.plan_revisions.latest('revision_number').steps.get(display_order=1).attempts.get().evidence_artifacts.get()
        artifact.metadata['permission_fingerprint'] = 'other-permission'
        artifact.save(update_fields=['metadata'])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['invalid_evidence'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'inconclusive')

    def test_tampered_evidence_environment_is_invalid(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Tampered environment')
        assertion = {'action': 'assert', 'assert_kind': 'text', 'target': {'page': 'current'}, 'operator': 'contains', 'expected': {'value': 'Ready'}, 'evidence_requirements': ['dom_snapshot']}
        persist_execution_plan(record.id, 'Verify evidence', [{'id': 'verify', 'description': 'Verify evidence', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'dom_snapshot', 'text': 'Ready'}])
        artifact = record.plan_revisions.latest('revision_number').steps.get(display_order=1).attempts.get().evidence_artifacts.get()
        artifact.metadata['environment_fingerprint'] = 'other-environment'
        artifact.save(update_fields=['metadata'])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['invalid_evidence'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'inconclusive')

    def test_expired_evidence_is_inconclusive(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Expired evidence')
        assertion = {'action': 'assert', 'assert_kind': 'text', 'target': {'page': 'current'}, 'operator': 'contains', 'expected': {'value': 'Ready'}, 'evidence_requirements': ['dom_snapshot'], 'evidence_max_age_ms': 1000}
        persist_execution_plan(record.id, 'Verify evidence', [{'id': 'verify', 'description': 'Verify evidence', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'dom_snapshot', 'text': 'Ready'}])
        artifact = record.plan_revisions.latest('revision_number').steps.get(display_order=1).attempts.get().evidence_artifacts.get()
        artifact.captured_at = timezone.now() - timedelta(seconds=2)
        artifact.save(update_fields=['captured_at'])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['inconclusive'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'inconclusive')

    def test_command_receipt_passes_quality_gate(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Command receipt')
        assertion = {'action': 'assert', 'assert_kind': 'command_result', 'target': {'device': 'test'}, 'operator': 'equals', 'expected': {'value': 0}, 'evidence_requirements': ['command_receipt']}
        persist_execution_plan(record.id, 'Verify command', [{'id': 'command', 'description': 'Verify command', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'device_cli'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'command_receipt', 'exit_code': 0}])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['passed'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'passed')

    def test_nonzero_command_receipt_fails_quality_gate(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Failed command receipt')
        assertion = {'action': 'assert', 'assert_kind': 'command_result', 'target': {'device': 'test'}, 'operator': 'equals', 'expected': {'value': 0}, 'evidence_requirements': ['command_receipt']}
        persist_execution_plan(record.id, 'Verify command', [{'id': 'command', 'description': 'Verify command', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'device_cli'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'command_receipt', 'exit_code': 1}])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['failed'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'failed')

    def test_evidence_cannot_be_reused_by_another_step(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Step isolation')
        assertion = {'action': 'assert', 'assert_kind': 'text', 'target': {'page': 'current'}, 'operator': 'contains', 'expected': {'value': 'Ready'}, 'evidence_requirements': ['dom_snapshot']}
        persist_execution_plan(record.id, 'Verify steps', [{'id': 'first', 'description': 'First', 'assertions': [assertion]}, {'id': 'second', 'description': 'Second', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'dom_snapshot', 'text': 'Ready'}])
        persist_step_attempt(record.id, 2, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['passed'])
        self.assertEqual(evaluate_step_assertions(record.id, 2), ['inconclusive'])

    def test_evidence_cannot_be_reused_by_replanned_step(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Revision isolation')
        assertion = {'action': 'assert', 'assert_kind': 'text', 'target': {'page': 'current'}, 'operator': 'contains', 'expected': {'value': 'Ready'}, 'evidence_requirements': ['dom_snapshot']}
        persist_execution_plan(record.id, 'Verify state', [{'id': 'verify', 'description': 'Verify', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'dom_snapshot', 'text': 'Ready'}])
        persist_replanned_step(record.id, 1, {'action': 'click'}, 'target failed', [{'action': 'assert'}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['inconclusive'])

    def test_visual_change_evidence_passes_quality_gate(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Visual change')
        assertion = {'action': 'assert', 'assert_kind': 'visual_change', 'target': {'page': 'current'}, 'operator': 'equals', 'expected': {'value': True}, 'evidence_requirements': ['visual_frame_before', 'visual_frame_after']}
        persist_execution_plan(record.id, 'Verify change', [{'id': 'change', 'description': 'Verify change', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'visual_frame_before', 'content_hash': 'before'}, {'type': 'visual_frame_after', 'content_hash': 'after'}])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['passed'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'passed')

    def test_network_response_passes_quality_gate(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Network response')
        assertion = {'action': 'assert', 'assert_kind': 'network', 'target': {'request': 'current'}, 'operator': 'equals', 'expected': {'value': 200}, 'evidence_requirements': ['network_response']}
        persist_execution_plan(record.id, 'Verify response', [{'id': 'network', 'description': 'Verify response', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'network_response', 'status': 200}])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['passed'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'passed')

    def test_nonmatching_network_response_fails_quality_gate(self) -> None:
        record = AIExecutionRecord.objects.create(case_name='Failed network response')
        assertion = {'action': 'assert', 'assert_kind': 'network', 'target': {'request': 'current'}, 'operator': 'equals', 'expected': {'value': 200}, 'evidence_requirements': ['network_response']}
        persist_execution_plan(record.id, 'Verify response', [{'id': 'network', 'description': 'Verify response', 'assertions': [assertion]}])
        persist_step_attempt(record.id, 1, {'action': 'assert'}, {}, 'completed', '', 'environment', 'permission', [{'type': 'network_response', 'status': 500}])

        self.assertEqual(evaluate_step_assertions(record.id, 1), ['failed'])
        self.assertEqual(evaluate_execution_quality_gate(record.id).status, 'failed')