"""Django-Q workers for idempotent Alpha read-Skill dispatch intents."""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from django.db import transaction
from django.utils import timezone
from django_q.tasks import async_task

from apps.ai_testing.alpha.orchestrator import _intent_key
from apps.ai_testing.alpha.planning import AlphaPlanningError, AlphaPlannerService
from apps.ai_testing.alpha.reflection import AlphaReflectionError, AlphaReflectionService
from apps.ai_testing.alpha.skills.catalog import build_phase_one_registry
from apps.ai_testing.alpha.skills.registry import SkillRegistryError
from apps.ai_testing.models import AlphaDispatchIntent, AlphaPlanRevision, AlphaRound, AlphaRun, AlphaTaskNode


logger = logging.getLogger(__name__)
ALPHA_PLANNING_TIMEOUT_SECONDS = 900
ALPHA_REFLECTION_TIMEOUT_SECONDS = 300
ALPHA_TASK_RETRY_SECONDS = 60


def enqueue_dispatch_intent(intent_id: int) -> str:
    """Queue an outbox intent only after its transaction has committed."""
    return str(async_task('apps.ai_testing.alpha.tasks.process_dispatch_intent', intent_id))


def enqueue_alpha_planning(run_id: int) -> str:
    """Queue Alpha planning and persist the durable Django-Q task identifier."""
    task_id = str(async_task(
        'apps.ai_testing.alpha.tasks.process_alpha_planning',
        run_id,
        timeout=ALPHA_PLANNING_TIMEOUT_SECONDS,
        retry=ALPHA_TASK_RETRY_SECONDS,
    ))
    AlphaRun.objects.filter(pk=run_id, status='planning').update(planner_task_id=task_id)
    return task_id


def process_alpha_planning(run_id: int) -> None:
    """Generate one validated draft revision or record a deterministic planning failure."""
    try:
        async_to_sync(AlphaPlannerService().create_draft_revision)(run_id)
    except AlphaPlanningError as error:
        AlphaRun.objects.filter(pk=run_id, status='planning').update(
            status='failed',
            error_message=str(error),
            planner_task_id='',
        )
        logger.warning('Alpha planning failed: run_id=%s reason=%s', run_id, error)
        return
    AlphaRun.objects.filter(pk=run_id).update(planner_task_id='')


def enqueue_alpha_reflection(revision_id: int) -> str:
    """Queue Alpha reflection and persist the durable Django-Q task identifier."""
    task_id = str(async_task(
        'apps.ai_testing.alpha.tasks.process_alpha_reflection',
        revision_id,
        timeout=ALPHA_REFLECTION_TIMEOUT_SECONDS,
        retry=ALPHA_TASK_RETRY_SECONDS,
    ))
    AlphaRun.objects.filter(active_revision_id=revision_id, status='reflecting').update(reflection_task_id=task_id)
    return task_id


def process_alpha_reflection(revision_id: int) -> None:
    """Persist a reflection verdict and either complete the run or request replanning."""
    try:
        verdict = async_to_sync(AlphaReflectionService().reflect_revision)(revision_id)
    except AlphaReflectionError as error:
        AlphaRun.objects.filter(active_revision_id=revision_id, status='reflecting').update(
            status='failed',
            error_message=str(error),
            reflection_task_id='',
        )
        logger.warning('Alpha reflection failed: revision_id=%s reason=%s', revision_id, error)
        return

    with transaction.atomic():
        revision = AlphaPlanRevision.objects.select_for_update().select_related('run').get(pk=revision_id)
        run = AlphaRun.objects.select_for_update().get(pk=revision.run_id)
        AlphaRound.objects.update_or_create(
            revision=revision,
            defaults={
                'run': run,
                'sequence': revision.revision_number,
                'planner_input': revision.planner_input,
                'planner_output': revision.planner_output,
                'reflection_input': {'task_evidence': [task.evidence for task in revision.task_nodes.all()]},
                'reflection_verdict': verdict.as_dict(),
            },
        )
        run.reflection_task_id = ''
        if verdict.verdict == 'pass':
            run.status = 'completed'
            run.final_output = verdict.as_dict()
        else:
            run.status = 'planning'
            run.error_message = ''
        run.state_version += 1
        run.save(
            update_fields=['status', 'final_output', 'error_message', 'reflection_task_id', 'state_version', 'updated_at']
        )
        if verdict.verdict == 'replan':
            transaction.on_commit(lambda: enqueue_alpha_planning(run.id))


def process_dispatch_intent(intent_id: int) -> None:
    """Claim and execute one low-risk read intent exactly once from Alpha's perspective."""
    with transaction.atomic():
        intent = (
            AlphaDispatchIntent.objects.select_for_update()
            .select_related('task__revision__run__initiated_by')
            .filter(pk=intent_id)
            .first()
        )
        if intent is None or intent.status != 'pending':
            return
        if intent.task.revision.run.status == 'cancelled':
            intent.status = 'cancelled'
            intent.save(update_fields=['status', 'updated_at'])
            return
        intent.status = 'claimed'
        intent.claimed_at = timezone.now()
        intent.attempts += 1
        intent.save(update_fields=['status', 'claimed_at', 'attempts', 'updated_at'])

    registry = build_phase_one_registry()
    try:
        evidence = registry.dispatch(
            intent.task.skill_name,
            intent.task.revision.run.initiated_by,
            intent.task.normalized_arguments,
        )
    except SkillRegistryError as error:
        _mark_intent_failed(intent_id, str(error))
        return

    with transaction.atomic():
        intent = AlphaDispatchIntent.objects.select_for_update().select_related('task__revision').get(pk=intent_id)
        if intent.status != 'claimed':
            return
        task = intent.task
        task.status = 'succeeded'
        task.evidence = dict(evidence)
        task.save(update_fields=['status', 'evidence', 'updated_at'])
        intent.status = 'dispatched'
        intent.dispatched_at = timezone.now()
        intent.lease_expires_at = None
        intent.save(update_fields=['status', 'dispatched_at', 'lease_expires_at', 'updated_at'])
        revision_id = task.revision_id
    _queue_ready_read_tasks(revision_id, registry)
    _maybe_begin_reflection(revision_id)


def _mark_intent_failed(intent_id: int, message: str) -> None:
    with transaction.atomic():
        intent = AlphaDispatchIntent.objects.select_for_update().select_related('task').get(pk=intent_id)
        if intent.status != 'claimed':
            return
        intent.status = 'failed'
        intent.error_message = message
        intent.save(update_fields=['status', 'error_message', 'updated_at'])
        task = intent.task
        task.status = 'failed'
        task.error_message = message
        task.save(update_fields=['status', 'error_message', 'updated_at'])
    logger.warning('Alpha dispatch intent failed: intent_id=%s reason=%s', intent_id, message)


def _queue_ready_read_tasks(revision_id: int, registry) -> None:
    intent_ids: list[int] = []
    with transaction.atomic():
        tasks = (
            AlphaTaskNode.objects.select_for_update()
            .filter(revision_id=revision_id, status='pending')
            .prefetch_related('dependencies__depends_on')
            .order_by('display_order', 'id')
        )
        for task in tasks:
            if not all(dependency.depends_on.status == 'succeeded' for dependency in task.dependencies.all()):
                continue
            definition = registry.get(task.skill_name)
            if definition.requires_confirmation:
                continue
            intent = AlphaDispatchIntent.objects.create(
                task=task,
                idempotency_key=_intent_key(revision_id, task.id, task.arguments_hash),
            )
            task.status = 'dispatched'
            task.save(update_fields=['status', 'updated_at'])
            intent_ids.append(intent.id)
    for ready_intent_id in intent_ids:
        enqueue_dispatch_intent(ready_intent_id)


def _maybe_begin_reflection(revision_id: int) -> None:
    with transaction.atomic():
        revision = AlphaPlanRevision.objects.select_for_update().select_related('run').get(pk=revision_id)
        run = AlphaRun.objects.select_for_update().get(pk=revision.run_id)
        if run.status != 'executing' or run.active_revision_id != revision.id:
            return
        if revision.task_nodes.exclude(status='succeeded').exists():
            return
        run.status = 'reflecting'
        run.state_version += 1
        run.save(update_fields=['status', 'state_version', 'updated_at'])
        transaction.on_commit(lambda: enqueue_alpha_reflection(revision.id))