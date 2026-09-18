"""Unified dispatch and execution of AI intelligent-test runs.

One execution body serves both entry points (case run and adhoc run) and both backends:

* ``thread``   – legacy in-process daemon thread (default, no infrastructure requirement)
* ``django_q`` – durable queue processed by the ``qcluster`` worker; survives web restarts and
                 serializes browser sessions according to the cluster's worker count.

Stop requests are honoured from any process: the in-memory signal is checked first, then the
persisted record status, so a stop issued to another worker still terminates the run.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import DatabaseError, connection
from django.utils import timezone

logger = logging.getLogger(__name__)

STOP_SIGNALS: dict[int, bool] = {}
STOP_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_TASK_TIMEOUT_SECONDS = 3 * 60 * 60
EXECUTION_BACKENDS = ('thread', 'django_q')
TASK_PATH = 'apps.ai_testing.execution.dispatch.execute_ai_record_task'


def _remember_verified_plan(execution_record, payload: dict[str, Any]) -> None:
    """Keep the plan a passing run used, in a table that clearing the reports does not touch.

    Never lets a bookkeeping problem fail a run that already passed: the plan is an optimisation, and the
    verdict is the thing the user asked for.
    """
    from apps.ai_testing.execution.verified_plan_persistence import record_verified_plan

    try:
        revision = (
            execution_record.plan_revisions.filter(reason='initial').order_by('revision_number').first()
        )
        if revision is None or not isinstance(revision.plan, dict):
            return
        record_verified_plan(
            revision.source_goal or execution_record.task_description or '',
            revision.plan,
            execution_record.environment_configuration_id,
            execution_record_id=execution_record.id,
            ai_case_id=payload.get('ai_case_id') or execution_record.ai_case_id,
            case_name=execution_record.case_name or '',
        )
    except Exception as error:  # noqa: BLE001 - bookkeeping must not change the run's verdict
        logger.warning('Could not record the verified plan for record %s: %s', execution_record.id, error)


def execution_backend() -> str:
    """Resolve the configured backend; unknown values fall back to the in-process thread."""
    value = str(
        os.getenv('AI_TESTING_EXECUTION_BACKEND')
        or getattr(settings, 'AI_TESTING_EXECUTION_BACKEND', '')
        or 'thread'
    ).strip().lower()
    return value if value in EXECUTION_BACKENDS else 'thread'


def dispatch_ai_execution(execution_record_id: int, payload: dict[str, Any]) -> dict[str, str]:
    """Start the run on the configured backend and stamp the record with how it was dispatched."""
    from apps.ai_testing.models import AIExecutionRecord

    backend = execution_backend()
    if backend == 'django_q':
        from django_q.tasks import async_task

        task_id = str(async_task(TASK_PATH, execution_record_id, payload, timeout=DEFAULT_TASK_TIMEOUT_SECONDS))
        AIExecutionRecord.objects.filter(pk=execution_record_id).update(
            dispatch_backend='django_q', dispatch_task_id=task_id,
        )
        return {'backend': backend, 'task_id': task_id}

    AIExecutionRecord.objects.filter(pk=execution_record_id).update(dispatch_backend='thread', dispatch_task_id='')
    thread = threading.Thread(target=execute_ai_record, args=(execution_record_id, payload), daemon=True)
    thread.start()
    return {'backend': backend, 'task_id': ''}


def launch_case_execution(ai_case, *, user, execution_mode='planner_v2', use_cache=True, environment_configuration=None, force_replan=False):
    """Create the execution record for an AI case and dispatch it exactly as the UI does."""
    from apps.ai_testing.models import AIExecutionRecord
    from apps.ai_testing.views import has_canonical_freeform_plan

    execution_record = AIExecutionRecord.objects.create(
        project=ai_case.project,
        ai_case=ai_case,
        environment_configuration=environment_configuration,
        case_name=ai_case.name,
        task_description=ai_case.task_description,
        execution_mode=execution_mode,
        status='running',
        executed_by=user,
        logs='正在分析任务...\n',
    )
    use_persisted_freeform_plan = (
        ai_case.case_mode == 'freeform'
        and has_canonical_freeform_plan(
            ai_case.planned_steps,
            environment_configuration.id if environment_configuration else None,
            ai_case.task_description,
        )
    )
    runtime_task_steps = (
        ai_case.planned_steps
        if ai_case.case_mode == 'freeform' and ai_case.planned_steps
        else ai_case.task_steps
    )
    dispatch_ai_execution(execution_record.id, {
        'task_description': ai_case.task_description,
        'execution_mode': execution_mode,
        'enable_gif': execution_mode == 'text',
        'case_name': ai_case.name,
        'case_mode': 'hybrid' if use_persisted_freeform_plan else ai_case.case_mode,
        'task_steps': runtime_task_steps,
        'use_cache': bool(use_cache),
        'force_replan': bool(force_replan),
        'execution_user_id': getattr(user, 'id', None),
        'ai_project_id': ai_case.project_id,
        'ai_case_id': ai_case.id,
        'legacy_plan_ignored': bool(
            ai_case.case_mode == 'freeform' and ai_case.planned_steps and not use_persisted_freeform_plan
        ),
    })
    return execution_record


def execute_ai_record_task(execution_record_id: int, payload: dict[str, Any]) -> None:
    """django-q entry point."""
    execute_ai_record(execution_record_id, payload)


def request_stop(execution_record_id: int) -> bool:
    """Flag a run for termination from any process; returns whether it was still running."""
    from apps.ai_testing.models import AIExecutionRecord

    if execution_record_id in STOP_SIGNALS:
        STOP_SIGNALS[execution_record_id] = True
    updated = AIExecutionRecord.objects.filter(pk=execution_record_id, status='running').update(
        status='stopped',
        end_time=timezone.now(),
    )
    return bool(updated)


def safe_save(record, update_fields=None, max_retries=3):
    """Save with a reconnect-and-retry for dropped MySQL connections."""
    for attempt in range(max_retries):
        try:
            record.save(update_fields=update_fields)
            return True
        except DatabaseError as error:
            error_text = str(error)
            if '2006' in error_text or 'MySQL server has gone away' in error_text or error_text == '0':
                if attempt < max_retries - 1:
                    logger.warning('数据库连接失败 (尝试 %s/%s): %s', attempt + 1, max_retries, error)
                    try:
                        connection.close()
                    except Exception:
                        pass
                    time.sleep(0.5)
                    continue
            raise
    return False


def process_gif_recording(execution_record) -> None:
    """Move browser-use's fixed-name GIF into media storage and remember its relative path."""
    try:
        default_gif_path = os.path.join(os.getcwd(), 'agent_history.gif')
        if not os.path.exists(default_gif_path):
            logger.warning('GIF file not found at: %s', default_gif_path)
            return
        gif_dir = os.path.join(settings.MEDIA_ROOT, settings.ALLURE_AI_RECORDING)
        os.makedirs(gif_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        safe_case_name = ''.join(
            c if c.isalnum() or c in (' ', '_', '-') else '_' for c in execution_record.case_name
        )
        new_gif_filename = f'{safe_case_name}_{timestamp}.gif'
        shutil.move(default_gif_path, os.path.join(gif_dir, new_gif_filename))
        execution_record.gif_path = f'{settings.ALLURE_AI_RECORDING}/{new_gif_filename}'
        logger.info('GIF recording saved to: %s', execution_record.gif_path)
    except Exception as error:
        logger.error('Failed to process GIF recording: %s', error)


def execute_ai_record(execution_record_id: int, payload: dict[str, Any]) -> None:
    """Run one execution record to completion and persist its final, gate-decided status."""
    from apps.ai_testing.ai_testing import run_full_process_sync
    from apps.ai_testing.execution.plan_persistence import persist_execution_plan
    from apps.ai_testing.execution.quality_gate_persistence import evaluate_execution_quality_gate
    from apps.ai_testing.models import AIExecutionRecord
    from apps.ai_testing.views import (
        append_execution_summary,
        extract_screenshot_sequence,
        extract_step_info,
        is_infrastructure_failure,
        mark_first_active_task,
        resolve_execution_status,
        sanitize_planned_tasks,
        summarize_planned_tasks,
        update_planned_task_status,
    )

    STOP_SIGNALS[execution_record_id] = False
    if not connection.in_atomic_block:
        # A worker/thread must not share the dispatching request's connection.
        try:
            connection.close()
        except Exception:
            pass
    os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

    execution_record = AIExecutionRecord.objects.select_related('environment_configuration').get(pk=execution_record_id)
    environment_configuration = execution_record.environment_configuration
    task_description = str(payload.get('task_description') or execution_record.task_description or '')
    stop_state = {'last_poll': 0.0, 'db_stopped': False}

    def stop_requested() -> bool:
        if STOP_SIGNALS.get(execution_record_id, False):
            return True
        now = time.monotonic()
        if now - stop_state['last_poll'] >= STOP_POLL_INTERVAL_SECONDS:
            stop_state['last_poll'] = now
            persisted_status = AIExecutionRecord.objects.filter(pk=execution_record_id).values_list('status', flat=True).first()
            stop_state['db_stopped'] = persisted_status == 'stopped'
        return stop_state['db_stopped']

    async def should_stop_async() -> bool:
        return await sync_to_async(stop_requested)()

    plan_context = {'fingerprint': ''}

    async def on_analysis_complete(planned_tasks):
        execution_record.planned_tasks = sanitize_planned_tasks(planned_tasks)
        await sync_to_async(persist_execution_plan)(
            execution_record.id,
            task_description,
            execution_record.planned_tasks,
            context_fingerprint=plan_context['fingerprint'],
        )
        execution_record.logs += '任务分析完成，开始执行...\n'
        execution_record.heartbeat_at = timezone.now()
        await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks', 'logs', 'heartbeat_at'])

    async def on_step_update(step_info):
        try:
            execution_record.heartbeat_at = timezone.now()
            if step_info.get('type') == 'plan_context':
                plan_context['fingerprint'] = str(step_info.get('fingerprint') or '')
                return
            if step_info.get('type') == 'log':
                content = step_info.get('content')
                if content:
                    execution_record.logs += content
                    await sync_to_async(safe_save)(execution_record, update_fields=['logs', 'heartbeat_at'])
                return
            task_id = step_info.get('task_id')
            task_status = step_info.get('status')
            if task_id and task_status:
                execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                if update_planned_task_status(execution_record.planned_tasks, task_id, task_status):
                    await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks', 'heartbeat_at'])
        except Exception as error:
            logger.error('更新步骤状态失败: %s', error, exc_info=True)

    try:
        if payload.get('legacy_plan_ignored'):
            execution_record.logs += '[planner_v2] Ignored legacy persisted plan that does not meet the current assertion and capability contract.\n'
            safe_save(execution_record, update_fields=['logs'])

        history = run_full_process_sync(
            task_description,
            analysis_callback=on_analysis_complete,
            step_callback=on_step_update,
            should_stop=should_stop_async,
            execution_mode=payload.get('execution_mode') or execution_record.execution_mode,
            enable_gif=bool(payload.get('enable_gif', False)),
            case_name=payload.get('case_name') or execution_record.case_name,
            case_mode=payload.get('case_mode') or 'freeform',
            task_steps=payload.get('task_steps') or [],
            use_cache=bool(payload.get('use_cache', True)),
            force_replan=bool(payload.get('force_replan', False)),
            execution_user_id=payload.get('execution_user_id'),
            environment_configuration=environment_configuration,
            ai_project_id=payload.get('ai_project_id'),
            execution_record_id=execution_record.id,
            ai_case_id=payload.get('ai_case_id'),
        )

        if stop_requested():
            execution_record.status = 'stopped'
            execution_record.logs += '\n[System] 任务已由用户停止。'
        else:
            execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
            quality_gate_result = evaluate_execution_quality_gate(execution_record.id)
            if quality_gate_result is None:
                execution_record.status, task_summary = resolve_execution_status(execution_record.planned_tasks)
            else:
                execution_record.status = quality_gate_result.status
                task_summary = summarize_planned_tasks(execution_record.planned_tasks)
            if execution_record.status == 'passed':
                execution_record.logs += '\n执行完成。'
                _remember_verified_plan(execution_record, payload)
            elif execution_record.status == 'inconclusive':
                execution_record.logs += '\n执行结束，但计划为空或仍有未完成子任务，无法证明通过。'
            else:
                execution_record.logs += '\n执行结束，但存在未完成或失败的子任务。'
            logger.info(
                'Task completion summary: %s/%s completed, %s failed, %s pending',
                task_summary['completed'], task_summary['total'], task_summary['failed'],
                task_summary['pending'] + task_summary['in_progress'],
            )

        execution_record.end_time = timezone.now()
        execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()

        steps = []
        if history:
            if hasattr(history, 'steps'):
                steps = [extract_step_info(step, index) for index, step in enumerate(history.steps)]
            if hasattr(history, 'planner_trace'):
                execution_record.planner_trace = history.planner_trace or {}
            if hasattr(history, 'artifacts'):
                execution_record.artifacts = history.artifacts or []
                execution_record.screenshots_sequence = extract_screenshot_sequence(execution_record.artifacts)
            if hasattr(history, 'cache_stats'):
                execution_record.cache_stats = history.cache_stats or {}
        execution_record.steps_completed = steps

        if execution_record.planned_tasks:
            execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
            execution_record.logs = append_execution_summary(
                execution_record.logs,
                summarize_planned_tasks(execution_record.planned_tasks),
            )

        if execution_record.execution_mode == 'text':
            process_gif_recording(execution_record)

        safe_save(execution_record)

    except Exception as error:
        from apps.ai_testing.runtime.pyui_compat.runner import EnvironmentBootstrapError

        error_message = str(error)
        logger.error('AI 执行异常: %s', error_message, exc_info=True)
        execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
        # The target application never came up: no step ran, so the product was not shown to fail.
        environment_failure = isinstance(error, EnvironmentBootstrapError)
        failed_task_id = None if environment_failure or is_infrastructure_failure(error_message) else mark_first_active_task(
            execution_record.planned_tasks, 'failed',
        )
        if stop_requested():
            execution_record.status = 'stopped'
        elif environment_failure:
            execution_record.status = 'inconclusive'
        else:
            execution_record.status = 'failed'
        if environment_failure:
            execution_record.logs += f'\n执行出错: 被测环境不可用，未执行任何步骤。{error_message}'
        elif 'Execution LLM unavailable' in error_message:
            execution_record.logs += f'\n执行出错: AI 执行模型连接失败。{error_message}'
        else:
            execution_record.logs += f'\n执行出错: {error_message}'
        if failed_task_id is not None:
            execution_record.logs += f'\n[System] 子任务 {failed_task_id} 已自动标记为失败。'
        execution_record.end_time = timezone.now()
        execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()
        execution_record.logs = append_execution_summary(
            execution_record.logs,
            summarize_planned_tasks(execution_record.planned_tasks),
        )
        try:
            safe_save(execution_record)
        except Exception as save_error:
            logger.error('保存失败状态时出错: %s', save_error)
    finally:
        STOP_SIGNALS.pop(execution_record_id, None)


def reconcile_stale_executions(stale_after_minutes: int = 30) -> list[int]:
    """Mark runs whose worker stopped reporting as failed so they do not stay 'running' forever."""
    from apps.ai_testing.models import AIExecutionRecord

    now = timezone.now()
    threshold = now - timedelta(minutes=max(1, int(stale_after_minutes)))
    reconciled: list[int] = []
    for record in AIExecutionRecord.objects.filter(status='running'):
        if record.id in STOP_SIGNALS:
            continue  # still owned by this process
        last_seen = record.heartbeat_at or record.start_time
        if last_seen is None or last_seen > threshold:
            continue
        record.status = 'failed'
        record.end_time = now
        record.duration = (now - record.start_time).total_seconds() if record.start_time else None
        record.logs = (record.logs or '') + (
            f'\n[System] 执行进程已丢失（最后心跳 {last_seen:%Y-%m-%d %H:%M:%S}），记录已由对账任务标记为失败。'
        )
        record.save(update_fields=['status', 'end_time', 'duration', 'logs'])
        reconciled.append(record.id)
    return reconciled
