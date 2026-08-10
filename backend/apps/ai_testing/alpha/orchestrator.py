"""Durable Alpha revision persistence and outbox preparation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.ai_testing.alpha.contracts import AlphaDomainError, record_completed_planning_cycle
from apps.ai_testing.alpha.planner import PlannedTask, parse_plan_payload
from apps.ai_testing.alpha.skills.registry import SkillRegistry
from apps.ai_testing.models import (
    AlphaApprovalRequest,
    AlphaDispatchIntent,
    AlphaPlanRevision,
    AlphaRun,
    AlphaTaskDependency,
    AlphaTaskNode,
)


APPROVAL_TTL = timedelta(minutes=15)


class AlphaOrchestrationError(ValueError):
    """Raised when a persisted Alpha workflow cannot advance safely."""


@dataclass(frozen=True, slots=True)
class ExecutionPreparation:
    revision_id: int
    dispatch_intent_ids: tuple[int, ...]
    approval_request_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approval_id: int
    dispatch_intent_ids: tuple[int, ...]


class AlphaOrchestrator:
    """Coordinates immutable revision creation and pre-dispatch safety gates."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def create_draft_revision(self, run_id: int, planner_payload: object) -> AlphaPlanRevision:
        """Persist one validated draft revision and make it the run's active revision."""
        planned_tasks = parse_plan_payload(planner_payload, self._registry)
        payload_hash = _hash_json(planner_payload)
        try:
            with transaction.atomic():
                run = AlphaRun.objects.select_for_update().get(pk=run_id)
                if run.status in {'completed', 'failed', 'cancelled'}:
                    raise AlphaOrchestrationError('Terminal Alpha runs cannot receive a new plan revision')

                round_count = record_completed_planning_cycle(run.round_count)
                latest_revision = run.revisions.aggregate(number=Max('revision_number'))['number'] or 0
                revision = AlphaPlanRevision.objects.create(
                    run=run,
                    revision_number=latest_revision + 1,
                    planner_output=planner_payload,
                    content_hash=payload_hash,
                )
                nodes = self._create_nodes(revision, planned_tasks)
                self._create_dependencies(nodes, planned_tasks)
                run.active_revision = revision
                run.status = 'planning'
                run.round_count = round_count
                run.state_version += 1
                run.save(update_fields=['active_revision', 'status', 'round_count', 'state_version', 'updated_at'])
                return revision
        except AlphaDomainError as error:
            raise AlphaOrchestrationError(str(error)) from error

    def freeze_and_prepare_execution(self, run_id: int, revision_id: int) -> ExecutionPreparation:
        """Freeze a revision and persist exact approvals or idempotent outbox intents."""
        with transaction.atomic():
            run = AlphaRun.objects.select_for_update().get(pk=run_id)
            revision = AlphaPlanRevision.objects.select_for_update().get(pk=revision_id, run=run)
            if run.active_revision_id != revision.id:
                raise AlphaOrchestrationError('Only the active Alpha revision can start execution')
            if revision.status != 'draft':
                raise AlphaOrchestrationError('Only a draft Alpha revision can be frozen')

            tasks = list(revision.task_nodes.select_for_update().order_by('display_order', 'id'))
            if not tasks:
                raise AlphaOrchestrationError('Alpha revision has no tasks to execute')

            approval_ids: list[int] = []
            intent_ids: list[int] = []
            expires_at = timezone.now() + APPROVAL_TTL
            for task in tasks:
                definition = self._registry.get(task.skill_name)
                if definition.version != task.skill_version or definition.tier.value != task.tier:
                    raise AlphaOrchestrationError(f'Skill contract changed for task: {task.task_key}')
                if definition.requires_confirmation:
                    approval = AlphaApprovalRequest.objects.create(
                        run=run,
                        revision=revision,
                        task=task,
                        arguments_hash=task.arguments_hash,
                        risk_metadata=task.risk_metadata,
                        expires_at=expires_at,
                    )
                    task.status = 'awaiting_confirmation'
                    task.save(update_fields=['status', 'updated_at'])
                    approval_ids.append(approval.id)
                    continue

                if not task.dependencies.exists():
                    intent = AlphaDispatchIntent.objects.create(
                        task=task,
                        idempotency_key=_intent_key(revision.id, task.id, task.arguments_hash),
                    )
                    task.status = 'dispatched'
                    task.save(update_fields=['status', 'updated_at'])
                    intent_ids.append(intent.id)

            revision.status = 'frozen'
            revision.frozen_at = timezone.now()
            revision.save(update_fields=['status', 'frozen_at'])
            run.status = 'awaiting_confirmation' if approval_ids else 'executing'
            run.state_version += 1
            run.save(update_fields=['status', 'state_version', 'updated_at'])
            transaction.on_commit(lambda: _enqueue_dispatch_intents(intent_ids))
            return ExecutionPreparation(
                revision_id=revision.id,
                dispatch_intent_ids=tuple(intent_ids),
                approval_request_ids=tuple(approval_ids),
            )

    def decide_approval(
        self,
        run_id: int,
        approval_id: int,
        approver: object,
        approve: bool,
    ) -> ApprovalDecision:
        """Approve or reject one exact risky action and queue it only when dependency-ready."""
        intent_ids: list[int] = []
        with transaction.atomic():
            approval = (
                AlphaApprovalRequest.objects.select_for_update()
                .select_related('run', 'revision', 'task')
                .get(pk=approval_id, run_id=run_id)
            )
            run = approval.run
            task = approval.task
            if approval.status != 'pending':
                raise AlphaOrchestrationError('Alpha approval is no longer pending')
            if approval.expires_at <= timezone.now():
                approval.status = 'expired'
                approval.save(update_fields=['status'])
                raise AlphaOrchestrationError('Alpha approval has expired')
            if run.active_revision_id != approval.revision_id or approval.revision.status != 'frozen':
                approval.status = 'invalidated'
                approval.save(update_fields=['status'])
                raise AlphaOrchestrationError('Alpha approval does not match the active frozen revision')
            if approval.arguments_hash != task.arguments_hash:
                approval.status = 'invalidated'
                approval.save(update_fields=['status'])
                raise AlphaOrchestrationError('Alpha approval arguments no longer match the task')

            approval.decided_by = approver
            approval.decided_at = timezone.now()
            if not approve:
                approval.status = 'rejected'
                task.status = 'cancelled'
                task.save(update_fields=['status', 'updated_at'])
                approval.save(update_fields=['status', 'decided_by', 'decided_at'])
                run.status = 'failed'
                run.error_message = f'Risky task rejected: {task.task_key}'
                run.state_version += 1
                run.save(update_fields=['status', 'error_message', 'state_version', 'updated_at'])
                return ApprovalDecision(approval_id=approval.id, dispatch_intent_ids=())

            definition = self._registry.get(task.skill_name)
            if not definition.requires_confirmation or definition.version != task.skill_version:
                raise AlphaOrchestrationError('Alpha approval no longer matches the registered Skill contract')
            approval.status = 'approved'
            approval.save(update_fields=['status', 'decided_by', 'decided_at'])
            if all(dependency.depends_on.status == 'succeeded' for dependency in task.dependencies.select_related('depends_on')):
                intent = AlphaDispatchIntent.objects.create(
                    task=task,
                    idempotency_key=_intent_key(approval.revision_id, task.id, task.arguments_hash),
                )
                task.status = 'dispatched'
                task.save(update_fields=['status', 'updated_at'])
                intent_ids.append(intent.id)
            else:
                task.status = 'pending'
                task.save(update_fields=['status', 'updated_at'])

            if not AlphaApprovalRequest.objects.filter(revision=approval.revision, status='pending').exists():
                run.status = 'executing'
                run.state_version += 1
                run.save(update_fields=['status', 'state_version', 'updated_at'])
            transaction.on_commit(lambda: _enqueue_dispatch_intents(intent_ids))
            return ApprovalDecision(approval_id=approval.id, dispatch_intent_ids=tuple(intent_ids))

    def _create_nodes(
        self,
        revision: AlphaPlanRevision,
        planned_tasks: tuple[PlannedTask, ...],
    ) -> dict[str, AlphaTaskNode]:
        nodes: dict[str, AlphaTaskNode] = {}
        for order, planned_task in enumerate(planned_tasks):
            definition = self._registry.get(planned_task.skill_name)
            task = AlphaTaskNode.objects.create(
                revision=revision,
                task_key=planned_task.task_key,
                display_order=order,
                skill_name=planned_task.skill_name,
                skill_version=planned_task.skill_version,
                tier=planned_task.tier.value,
                risk_metadata={
                    'tier': definition.tier.value,
                    'risky': definition.risky,
                    'requires_confirmation': definition.requires_confirmation,
                },
                normalized_arguments=planned_task.normalized_arguments,
                arguments_hash=_hash_json(planned_task.normalized_arguments),
            )
            nodes[planned_task.task_key] = task
        for planned_task in planned_tasks:
            if planned_task.parent_key is None:
                continue
            task = nodes[planned_task.task_key]
            task.parent = nodes[planned_task.parent_key]
            task.save(update_fields=['parent', 'updated_at'])
        return nodes

    @staticmethod
    def _create_dependencies(
        nodes: dict[str, AlphaTaskNode],
        planned_tasks: tuple[PlannedTask, ...],
    ) -> None:
        dependencies = [
            AlphaTaskDependency(task=nodes[task.task_key], depends_on=nodes[dependency_key])
            for task in planned_tasks
            for dependency_key in task.dependency_keys
        ]
        AlphaTaskDependency.objects.bulk_create(dependencies)


def _hash_json(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=True, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _intent_key(revision_id: int, task_id: int, arguments_hash: str) -> str:
    source = f'alpha:{revision_id}:{task_id}:{arguments_hash}'
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def _enqueue_dispatch_intents(intent_ids: list[int]) -> None:
    from apps.ai_testing.alpha.tasks import enqueue_dispatch_intent

    for intent_id in intent_ids:
        enqueue_dispatch_intent(intent_id)