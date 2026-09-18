"""Proven execution plans, stored per case rather than per execution record.

``AIExecutionPlanRevision`` hangs off an execution record, so clearing the report tables also clears every
plan a passing run had proven. This module keeps the same plans in a table that report truncation does not
touch, and is the first place :meth:`GlobalTestPlanner.create_plan` looks.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.ai_testing.models import AIVerifiedPlan

# How many distinct proven plans to keep for one goal in one environment under one planning context. Plans
# accumulate evidence rather than overwrite one another, so a plan that passed twenty times is not displaced
# by one that passed once; the cap stops that from growing without bound.
MAX_PLANS_PER_CONTEXT = 5


def goal_hash(source_goal: str) -> str:
    """Indexable key for a goal; ``source_goal`` itself is TEXT and cannot carry a unique constraint."""
    return hashlib.sha256(str(source_goal or '').encode('utf-8')).hexdigest()


def plan_hash(plan: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(plan or {}, ensure_ascii=True, sort_keys=True).encode('utf-8')
    ).hexdigest()


def load_verified_plan_steps(
    source_goal: str,
    environment_configuration_id: int | None,
    context_fingerprint: str = '',
    allow_legacy: bool = True,
) -> list[dict[str, Any]]:
    """Steps of the best proven plan for this goal, or an empty list when none is proven.

    A plan recorded before fingerprints existed, or under an older planning context, is still proven for an
    ordinary goal; a goal naming the target device must re-plan so the plan reflects the current devices.
    That is the same rule the execution-record plan cache applies.
    """
    rows = list(
        AIVerifiedPlan.objects.filter(
            goal_hash=goal_hash(source_goal),
            environment_configuration_id=environment_configuration_id,
        ).order_by('-verified_count', '-last_verified_at', '-id')[:MAX_PLANS_PER_CONTEXT * 2]
    )

    def acceptable(row: AIVerifiedPlan) -> bool:
        if not isinstance(row.plan, dict):
            return False
        stored = str(row.context_fingerprint or '')
        if not context_fingerprint or stored == context_fingerprint:
            return True
        return allow_legacy

    chosen = next((row for row in rows if acceptable(row)), None)
    if chosen is None:
        return []
    steps = chosen.plan.get('steps')
    if not isinstance(steps, list):
        return []
    return [dict(step.get('source') or step) for step in steps if isinstance(step, dict)]


def record_verified_plan(
    source_goal: str,
    plan: dict[str, Any],
    environment_configuration_id: int | None,
    execution_record_id: int | None = None,
    ai_case_id: int | None = None,
    case_name: str = '',
) -> AIVerifiedPlan | None:
    """Remember that this plan passed. Returns the stored row, or None when there is nothing to store."""
    steps = (plan or {}).get('steps')
    if not isinstance(steps, list) or not steps:
        return None
    digest = plan_hash(plan)
    key = goal_hash(source_goal)
    fingerprint = str((plan or {}).get('context_fingerprint') or '')
    now = timezone.now()

    with transaction.atomic():
        updated = AIVerifiedPlan.objects.filter(
            goal_hash=key,
            environment_configuration_id=environment_configuration_id,
            context_fingerprint=fingerprint,
            plan_hash=digest,
        ).update(
            verified_count=F('verified_count') + 1,
            last_passed_record_id=execution_record_id,
            last_verified_at=now,
            case_name=case_name or F('case_name'),
            ai_case_id=ai_case_id if ai_case_id is not None else F('ai_case_id'),
        )
        if not updated:
            try:
                AIVerifiedPlan.objects.create(
                    goal_hash=key,
                    source_goal=source_goal,
                    ai_case_id=ai_case_id,
                    case_name=case_name or '',
                    environment_configuration_id=environment_configuration_id,
                    context_fingerprint=fingerprint,
                    plan=plan,
                    plan_hash=digest,
                    verified_count=1,
                    last_passed_record_id=execution_record_id,
                    last_verified_at=now,
                )
            except IntegrityError:
                # Two runs of the same case finished together; the other one created the row.
                AIVerifiedPlan.objects.filter(
                    goal_hash=key,
                    environment_configuration_id=environment_configuration_id,
                    context_fingerprint=fingerprint,
                    plan_hash=digest,
                ).update(verified_count=F('verified_count') + 1, last_verified_at=now)
        _prune(key, environment_configuration_id, fingerprint)

    return AIVerifiedPlan.objects.filter(
        goal_hash=key,
        environment_configuration_id=environment_configuration_id,
        context_fingerprint=fingerprint,
        plan_hash=digest,
    ).first()


def _prune(key: str, environment_configuration_id: int | None, fingerprint: str) -> int:
    """Keep only the best-proven plans for one context; returns how many were dropped."""
    surviving = list(
        AIVerifiedPlan.objects.filter(
            goal_hash=key,
            environment_configuration_id=environment_configuration_id,
            context_fingerprint=fingerprint,
        )
        .order_by('-verified_count', '-last_verified_at', '-id')
        .values_list('id', flat=True)[:MAX_PLANS_PER_CONTEXT]
    )
    return AIVerifiedPlan.objects.filter(
        goal_hash=key,
        environment_configuration_id=environment_configuration_id,
        context_fingerprint=fingerprint,
    ).exclude(id__in=surviving).delete()[0]


def backfill_from_execution_records(environment_configuration_id: int | None = None) -> int:
    """Seed the table from execution records that already passed. Returns how many plans were recorded.

    Without this, deploying the table to an environment that has been running for a while throws away every
    plan those runs proved: the table starts empty, and the first report truncation leaves nothing behind.
    Re-running it is harmless, it just accumulates more evidence on the same rows.
    """
    from apps.ai_testing.models import AIExecutionPlanRevision

    revisions = AIExecutionPlanRevision.objects.filter(
        reason='initial',
        execution_record__status='passed',
    ).select_related('execution_record').order_by('execution_record_id', 'revision_number')
    if environment_configuration_id is not None:
        revisions = revisions.filter(execution_record__environment_configuration_id=environment_configuration_id)

    recorded = 0
    for revision in revisions:
        record = revision.execution_record
        stored = record_verified_plan(
            revision.source_goal or record.task_description or '',
            revision.plan if isinstance(revision.plan, dict) else {},
            record.environment_configuration_id,
            execution_record_id=record.id,
            ai_case_id=record.ai_case_id,
            case_name=record.case_name or '',
        )
        if stored is not None:
            recorded += 1
    return recorded


def export_verified_plans(ai_case_id: int | None = None, environment_configuration_id: int | None = None) -> list[dict[str, Any]]:
    """Proven plans as plain dicts, so an environment that has warmed up can seed one that has not."""
    queryset = AIVerifiedPlan.objects.all()
    if ai_case_id is not None:
        queryset = queryset.filter(ai_case_id=ai_case_id)
    if environment_configuration_id is not None:
        queryset = queryset.filter(environment_configuration_id=environment_configuration_id)
    return [
        {
            'source_goal': row.source_goal,
            'ai_case_id': row.ai_case_id,
            'case_name': row.case_name,
            'environment_configuration_id': row.environment_configuration_id,
            'context_fingerprint': row.context_fingerprint,
            'plan': row.plan,
            'verified_count': row.verified_count,
        }
        for row in queryset.order_by('-verified_count', '-id')
    ]


def import_verified_plans(payload: list[dict[str, Any]], environment_configuration_id: int | None = None) -> int:
    """Load exported plans, optionally retargeting them at another environment. Returns rows written."""
    written = 0
    for item in payload or []:
        if not isinstance(item, dict) or not isinstance(item.get('plan'), dict):
            continue
        target_environment = (
            environment_configuration_id
            if environment_configuration_id is not None
            else item.get('environment_configuration_id')
        )
        stored = record_verified_plan(
            str(item.get('source_goal') or ''),
            item['plan'],
            target_environment,
            ai_case_id=item.get('ai_case_id'),
            case_name=str(item.get('case_name') or ''),
        )
        if stored is not None:
            written += 1
    return written
