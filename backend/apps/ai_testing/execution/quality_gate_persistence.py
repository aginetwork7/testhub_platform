"""Persist quality-gate decisions derived from durable execution evidence."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from apps.ai_testing.execution.quality_gate import QualityGateResult, evaluate_quality_gate
from apps.ai_testing.models import AIExecutionPlanRevision, AIExecutionQualityGateResult


def evaluate_execution_quality_gate(execution_record_id: int) -> QualityGateResult | None:
    """Evaluate and persist the latest plan revision, or return None for legacy runs."""
    with transaction.atomic():
        revision = (
            AIExecutionPlanRevision.objects.select_for_update()
            .filter(execution_record_id=execution_record_id)
            .order_by('-revision_number')
            .first()
        )
        if revision is None:
            return None

        steps = list(revision.steps.prefetch_related('assertion_results').order_by('display_order', 'id'))
        plan_steps = revision.plan.get('steps', []) if isinstance(revision.plan, dict) else []
        verification_by_order = {
            index: (item.get('verification_required', True) is not False)
            for index, item in enumerate(plan_steps, start=1)
            if isinstance(item, dict)
        }
        result = evaluate_quality_gate(
            [
                {
                    'id': step.step_key,
                    'status': 'completed' if (
                        step.status == 'verified'
                        or step.status == 'action_completed' and not verification_by_order.get(step.display_order, True)
                    ) else step.status,
                    'requires_assertion': verification_by_order.get(step.display_order, True),
                }
                for step in steps
            ],
            [
                {
                    'id': assertion_result.id,
                    'step_id': step.step_key,
                    'status': assertion_result.status,
                    'required': bool(assertion_result.assertion.get('required', True)),
                }
                for step in steps
                for assertion_result in step.assertion_results.all()
            ],
        )
        latest_evaluation = revision.quality_gate_results.aggregate(
            last_evaluation=Max('evaluation_number'),
        )['last_evaluation'] or 0
        AIExecutionQualityGateResult.objects.create(
            plan_revision=revision,
            evaluation_number=latest_evaluation + 1,
            status=result.status,
            details={
                'failed_task_ids': list(result.failed_task_ids),
                'incomplete_task_ids': list(result.incomplete_task_ids),
                'failed_assertion_ids': list(result.failed_assertion_ids),
                'inconclusive_assertion_ids': list(result.inconclusive_assertion_ids),
                'missing_assertion_step_ids': list(result.missing_assertion_step_ids),
            },
        )
        revision.execution_record.status = result.status
        revision.execution_record.save(update_fields=['status'])
        return result