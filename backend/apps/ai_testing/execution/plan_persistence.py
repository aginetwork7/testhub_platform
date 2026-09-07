"""Persistence for immutable execution-plan snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from django.db import transaction

from apps.ai_testing.models import (
    AIExecutionAssertionResult,
    AIExecutionEvidenceArtifact,
    AIExecutionPlanRevision,
    AIExecutionRecord,
    AIExecutionStep,
    AIExecutionStepAttempt,
)


def persist_execution_plan(
    execution_record_id: int,
    source_goal: str,
    planned_tasks: Sequence[Mapping[str, Any]],
    reason: str = 'initial',
) -> AIExecutionPlanRevision:
    """Persist a canonical plan once, returning the existing snapshot on retry."""
    normalized_tasks = [_normalize_task(task, index) for index, task in enumerate(planned_tasks, start=1)]
    plan = {'steps': normalized_tasks}
    plan_hash = _hash_plan(plan)

    with transaction.atomic():
        execution_record = AIExecutionRecord.objects.select_for_update().get(pk=execution_record_id)
        existing_revision = AIExecutionPlanRevision.objects.filter(
            execution_record=execution_record,
            plan_hash=plan_hash,
            reason=reason,
        ).first()
        if existing_revision is not None:
            return existing_revision

        latest_revision = execution_record.plan_revisions.order_by('-revision_number').first()
        revision_number = 1 if latest_revision is None else latest_revision.revision_number + 1
        revision = AIExecutionPlanRevision.objects.create(
            execution_record=execution_record,
            revision_number=revision_number,
            source_goal=source_goal,
            plan=plan,
            plan_hash=plan_hash,
            reason=reason,
        )
        AIExecutionStep.objects.bulk_create([
            AIExecutionStep(
                plan_revision=revision,
                step_key=task['step_key'],
                display_order=index,
                intent=task['intent'],
                dependencies=task['dependencies'],
                allowed_capabilities=task['allowed_capabilities'],
                assertions=task['assertions'],
            )
            for index, task in enumerate(normalized_tasks, start=1)
        ])
        return revision


def persist_replanned_step(
    execution_record_id: int,
    step_order: int,
    failed_action: Mapping[str, Any],
    error_message: str,
    replanned_actions: Sequence[Mapping[str, Any]],
) -> AIExecutionPlanRevision:
    """Append a replan revision without changing previous plans or evidence."""
    with transaction.atomic():
        previous_revision = (
            AIExecutionPlanRevision.objects.select_for_update()
            .filter(execution_record_id=execution_record_id)
            .prefetch_related(
                'steps__attempts__evidence_artifacts',
                'steps__assertion_results__evidence_artifacts',
            )
            .order_by('-revision_number')
            .first()
        )
        if previous_revision is None:
            raise ValueError('Execution plan revision does not exist.')

        planned_tasks = _revision_source_tasks(previous_revision, step_order, failed_action, error_message, replanned_actions)
        _validate_step_local_replan(previous_revision, planned_tasks, step_order)
        revision = persist_execution_plan(
            execution_record_id,
            previous_revision.source_goal,
            planned_tasks,
            reason=f'replan_step_{step_order}_from_{previous_revision.revision_number}',
        )
        if revision.id != previous_revision.id:
            _copy_verified_predecessors(previous_revision, revision, step_order)
        return revision


def persist_bound_step(
    execution_record_id: int,
    step_order: int,
    bindings: Sequence[Mapping[str, Any]],
) -> AIExecutionPlanRevision:
    """Append a revision that binds semantic assertions to observed locators."""
    with transaction.atomic():
        previous_revision = AIExecutionPlanRevision.objects.select_for_update().filter(
            execution_record_id=execution_record_id,
        ).prefetch_related('steps__attempts__evidence_artifacts', 'steps__assertion_results__evidence_artifacts').order_by('-revision_number').first()
        if previous_revision is None:
            raise ValueError('Execution plan revision does not exist.')
        tasks = [dict(item.get('source') or item) for item in previous_revision.plan.get('steps', [])]
        target = dict(tasks[step_order - 1])
        assertions = [dict(item) for item in target.get('assertions', [])]
        for binding in bindings:
            assertion = assertions[int(binding['assertion_index']) - 1]
            semantic_intent = _semantic_target_intent(assertion.get('target', {}))
            assertion['target'] = {'locator': binding['locator'], 'intent': semantic_intent}
        target['assertions'] = assertions
        target['assertion_bindings'] = [dict(binding) for binding in bindings]
        tasks[step_order - 1] = target
        revision = persist_execution_plan(
            execution_record_id,
            previous_revision.source_goal,
            tasks,
            reason=f'binding_step_{step_order}_from_{previous_revision.revision_number}',
        )
        if revision.id != previous_revision.id:
            _copy_verified_predecessors(previous_revision, revision, step_order)
        return revision


def _revision_source_tasks(
    revision: AIExecutionPlanRevision,
    step_order: int,
    failed_action: Mapping[str, Any],
    error_message: str,
    replanned_actions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    source_steps = revision.plan.get('steps') if isinstance(revision.plan, Mapping) else None
    if not isinstance(source_steps, list) or not 1 <= step_order <= len(source_steps):
        raise ValueError(f'Execution step {step_order} does not exist.')
    tasks = [dict(item.get('source') or item) for item in source_steps if isinstance(item, Mapping)]
    if len(tasks) != len(source_steps):
        raise ValueError('Execution plan contains an invalid step.')
    target = dict(tasks[step_order - 1])
    target['replan'] = {
        'failed_action': dict(failed_action),
        'error': error_message,
        'actions': [dict(action) for action in replanned_actions],
    }
    tasks[step_order - 1] = target
    return tasks


def _validate_step_local_replan(
    previous_revision: AIExecutionPlanRevision,
    replanned_tasks: Sequence[Mapping[str, Any]],
    step_order: int,
) -> None:
    source_steps = previous_revision.plan.get('steps') if isinstance(previous_revision.plan, Mapping) else None
    if not isinstance(source_steps, list) or len(source_steps) != len(replanned_tasks):
        raise ValueError('Step replan must preserve the global plan shape.')
    for index, (source_step, replanned_task) in enumerate(zip(source_steps, replanned_tasks), start=1):
        if not isinstance(source_step, Mapping):
            raise ValueError('Execution plan contains an invalid step.')
        source_task = dict(source_step.get('source') or source_step)
        if index != step_order and source_task != dict(replanned_task):
            raise ValueError(f'Step replan cannot modify non-target step {index}.')
        expected_step_key = str(source_step.get('step_key') or source_task.get('key') or source_task.get('id') or '')
        replanned_step_key = str(replanned_task.get('key') or replanned_task.get('id') or expected_step_key)
        if replanned_step_key != expected_step_key:
            raise ValueError(f'Step replan cannot change step identity at position {index}.')


def _copy_verified_predecessors(
    previous_revision: AIExecutionPlanRevision,
    revision: AIExecutionPlanRevision,
    step_order: int,
) -> None:
    target_steps = {step.display_order: step for step in revision.steps.all()}
    for previous_step in previous_revision.steps.all():
        has_required_assertion = any(
            not isinstance(assertion, dict) or assertion.get('required', True) is not False
            for assertion in previous_step.assertions
        )
        completed_without_required_assertion = (
            previous_step.status == 'action_completed' and not has_required_assertion
        )
        if previous_step.display_order >= step_order or (
            previous_step.status != 'verified' and not completed_without_required_assertion
        ):
            continue
        target_step = target_steps[previous_step.display_order]
        evidence_by_id: dict[int, AIExecutionEvidenceArtifact] = {}
        for previous_attempt in previous_step.attempts.all():
            target_attempt = AIExecutionStepAttempt.objects.create(
                step=target_step,
                attempt_number=previous_attempt.attempt_number,
                action=previous_attempt.action,
                action_output=previous_attempt.action_output,
                status=previous_attempt.status,
                error_message=previous_attempt.error_message,
                environment_fingerprint=previous_attempt.environment_fingerprint,
                permission_fingerprint=previous_attempt.permission_fingerprint,
                completed_at=previous_attempt.completed_at,
            )
            for previous_artifact in previous_attempt.evidence_artifacts.all():
                evidence_by_id[previous_artifact.id] = AIExecutionEvidenceArtifact.objects.create(
                    attempt=target_attempt,
                    artifact_type=previous_artifact.artifact_type,
                    storage_path=previous_artifact.storage_path,
                    content_hash=previous_artifact.content_hash,
                    metadata={**previous_artifact.metadata, 'inherited_from_artifact_id': previous_artifact.id},
                )
        for previous_assertion in previous_step.assertion_results.all():
            target_assertion = AIExecutionAssertionResult.objects.create(
                step=target_step,
                assertion=previous_assertion.assertion,
                status=previous_assertion.status,
                actual=previous_assertion.actual,
            )
            target_assertion.evidence_artifacts.add(*[
                evidence_by_id[artifact.id]
                for artifact in previous_assertion.evidence_artifacts.all()
                if artifact.id in evidence_by_id
            ])
        target_step.status = previous_step.status
        target_step.save(update_fields=['status', 'updated_at'])


def _normalize_task(task: Mapping[str, Any], index: int) -> dict[str, Any]:
    step_key = str(task.get('key') or task.get('id') or f'step-{index}').strip()
    if not step_key:
        step_key = f'step-{index}'
    return {
        'step_key': step_key,
        'intent': str(task.get('intent') or task.get('description') or '').strip(),
        'dependencies': _list_value(task.get('depends_on')),
        'allowed_capabilities': _list_value(task.get('allowed_capabilities')),
        'verification_required': task.get('verification_required', True) is not False,
        'assertions': _list_value(task.get('assertions')),
        'correlates_resource': str(task.get('correlates_resource') or '').strip(),
        'source': dict(task),
    }


def _list_value(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _semantic_target_intent(target: object) -> object:
    current = target
    while isinstance(current, Mapping) and 'intent' in current:
        current = current['intent']
    if isinstance(current, Mapping) and set(current) == {'locator'}:
        return current['locator']
    return current


def _hash_plan(plan: Mapping[str, Any]) -> str:
    serialized = json.dumps(plan, ensure_ascii=True, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()