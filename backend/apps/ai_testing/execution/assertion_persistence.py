"""Persist deterministic assertion evaluations for one execution step."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai_testing.execution.assertion_evaluator import evaluate_assertion
from apps.ai_testing.execution.assertion_registry import AssertionContractError, parse_assertion
from apps.ai_testing.models import AIExecutionAssertionResult, AIExecutionPlanRevision


def evaluate_step_assertions(execution_record_id: int, step_order: int) -> list[str]:
    """Evaluate the current step's planned assertions against its latest evidence."""
    with transaction.atomic():
        revision = (
            AIExecutionPlanRevision.objects.select_for_update()
            .filter(execution_record_id=execution_record_id)
            .order_by('-revision_number')
            .first()
        )
        if revision is None:
            raise ValueError('Execution plan revision does not exist.')
        step = revision.steps.select_for_update().filter(display_order=step_order).first()
        if step is None:
            raise ValueError(f'Execution step {step_order} does not exist.')
        if not isinstance(step.assertions, list) or not step.assertions:
            return []

        attempt = step.attempts.order_by('-attempt_number').first()
        if attempt is None:
            raise ValueError(f'Execution step {step_order} has no action attempt.')
        evidence = list(attempt.evidence_artifacts.all())
        statuses: list[str] = []
        for raw_assertion in step.assertions:
            invalid_evidence = [artifact for artifact in evidence if not _is_valid_evidence_artifact(artifact, attempt)]
            if invalid_evidence:
                status, actual, evidence_ids = 'invalid_evidence', {
                    'reason': 'Evidence artifact has an invalid content hash.',
                }, set()
            else:
                status, actual, evidence_ids = _evaluate_assertion(raw_assertion, evidence)
            result = AIExecutionAssertionResult.objects.create(
                step=step,
                assertion=dict(raw_assertion) if isinstance(raw_assertion, Mapping) else {'raw': str(raw_assertion)},
                status=status,
                actual=actual,
            )
            result.evidence_artifacts.add(*[artifact for artifact in evidence if artifact.id in evidence_ids])
            statuses.append(status)

        required_statuses = [
            status
            for raw_assertion, status in zip(step.assertions, statuses)
            if not isinstance(raw_assertion, Mapping) or raw_assertion.get('required', True) is not False
        ]
        if 'failed' in required_statuses:
            step.status = 'failed'
        elif any(status in {'inconclusive', 'invalid_evidence'} for status in required_statuses):
            step.status = 'inconclusive'
        elif required_statuses:
            step.status = 'verified'
        step.save(update_fields=['status', 'updated_at'])
        return statuses


def _evaluate_assertion(
    raw_assertion: object,
    evidence: list[Any],
) -> tuple[str, dict[str, Any], set[int]]:
    if not isinstance(raw_assertion, Mapping):
        return 'invalid_evidence', {'reason': 'Assertion must be an object.'}, set()
    try:
        assertion = parse_assertion(raw_assertion)
    except AssertionContractError as error:
        return 'invalid_evidence', {'reason': str(error)}, set()

    evidence_types = set(assertion.evidence_requirements)
    if assertion.assert_kind == 'stream_state':
        evidence_types.update({'canvas_frame_before', 'canvas_frame_after'})
    if assertion.assert_kind == 'playback':
        evidence_types.add('playback_visual_progress')
    matching_evidence = [
        artifact
        for artifact in evidence
        if artifact.artifact_type in evidence_types
    ]
    if assertion.evidence_max_age_ms is not None:
        now = timezone.now()
        stale_evidence = [
            artifact for artifact in matching_evidence
            if (now - artifact.captured_at).total_seconds() * 1000 > assertion.evidence_max_age_ms
        ]
        if stale_evidence:
            return 'inconclusive', {
                'reason': 'Required evidence exceeded evidence_max_age_ms.',
            }, {artifact.id for artifact in matching_evidence}
    evaluation = evaluate_assertion(
        assertion,
        [
            {'artifact_type': artifact.artifact_type, 'metadata': artifact.metadata}
            for artifact in matching_evidence
        ],
    )
    return evaluation.status, {**evaluation.actual, 'reason': evaluation.reason}, {
        artifact.id for artifact in matching_evidence
    }


def _has_valid_content_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _is_valid_evidence_artifact(artifact: Any, attempt: Any) -> bool:
    metadata = artifact.metadata if isinstance(artifact.metadata, Mapping) else {}
    return (
        _has_valid_content_hash(artifact.content_hash)
        and metadata.get('environment_fingerprint') == attempt.environment_fingerprint
        and metadata.get('permission_fingerprint') == attempt.permission_fingerprint
    )