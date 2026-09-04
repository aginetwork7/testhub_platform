import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from asgiref.sync import sync_to_async
from django.db import DatabaseError, models, transaction


logger = logging.getLogger('django')

ACTION_CACHE_SCHEMA_VERSION = 'v5'


def _is_false_like(value):
    return str(value or '').strip().lower() in {'false', '0', 'no'}


@dataclass
class PyUICompatHistory:
    steps: list[dict] = field(default_factory=list)
    planner_trace: dict = field(default_factory=dict)
    artifacts: list[dict] = field(default_factory=list)
    cache_stats: dict = field(default_factory=dict)
    case_report: dict = field(default_factory=dict)


class PyUICompatAgent:
    """Initial pyuitest-inspired runtime scaffold for AI intelligent mode."""

    def __init__(self, execution_mode='planner_v2', enable_gif=False, case_name=None, use_cache=True, execution_user_id=None, environment_configuration=None, ai_project_id=None, execution_record_id=None, ai_case_id=None):
        self.execution_mode = execution_mode
        self.enable_gif = enable_gif
        self.case_name = case_name or 'Adhoc Task'
        self.use_cache = bool(use_cache)
        self.execution_user_id = execution_user_id
        self.environment_configuration = environment_configuration
        self.ai_project_id = ai_project_id
        self.execution_record_id = execution_record_id
        self.ai_case_id = ai_case_id
        self._cache_context_by_step = {}
        self._recent_network_events = []
        self._runtime_correlation_values = []
        self._recent_download_events = []
        self._execution_resources = []
        self._last_actionable_controls = []

    async def analyze_task(self, task_description, case_mode='freeform', task_steps=None):
        return self._build_planned_tasks(task_description, case_mode=case_mode, task_steps=task_steps)

    async def run_task(self, task_description, planned_tasks=None, callback=None, should_stop=None):
        tasks = planned_tasks or self._build_planned_tasks(task_description)
        if callback is not None:
            await self._emit(callback, {'type': 'log', 'content': 'planner_v2 runtime bootstrap: executor not implemented yet\n'})
        return tasks

    def _resolve_browser_executable(self):
        """Prefer a browser that can decode original HEVC event media."""
        configured = os.environ.get('PLAYWRIGHT_CHROMIUM_PATH', '').strip()
        candidates = [configured] if configured else []
        candidates.extend([
            '/usr/lib/chromium/chromium',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/usr/bin/google-chrome',
        ])
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    async def run_full_process(self, task_description, analysis_callback=None, step_callback=None, should_stop=None, case_mode='freeform', task_steps=None):
        execution_steps = task_steps
        resolved_case_mode = case_mode
        if case_mode == 'freeform':
            from apps.ai_testing.global_planner import GlobalTestPlanner

            execution_steps = await GlobalTestPlanner().create_plan(
                task_description,
                getattr(self.environment_configuration, 'id', None),
                use_cache=self.use_cache,
            )
            resolved_case_mode = 'hybrid'

        planned_tasks = self._build_planned_tasks(task_description, case_mode=resolved_case_mode, task_steps=execution_steps)
        if analysis_callback is not None:
            await self._emit(analysis_callback, planned_tasks)

        history = PyUICompatHistory(
            planner_trace={
                'case_mode': resolved_case_mode,
                'task_count': len(planned_tasks),
                'source': 'global_planner' if case_mode == 'freeform' else ('planner_v2_bootstrap' if case_mode != 'hybrid' else 'planner_v2_hybrid'),
                'step_retry_map': {},
                'environment_configuration': self._planner_configuration_trace(),
                'global_plan': self._planner_step_trace(execution_steps) if case_mode == 'freeform' else [],
            },
            cache_stats={
                'enabled': self.use_cache,
                'hit': 0,
                'miss': len(planned_tasks) if self.use_cache else 0,
                'ai_generated': 0,
                'write': 0,
                'fallback_replan': 0,
                'model_retries': 0,
                'model_attempts': 0,
                'experience_hit': 0,
                'experience_write': 0,
            },
            case_report={
                'case_id': self.case_name,
                'total_steps': len(planned_tasks),
                'success': True,
                'steps': [],
            },
        )

        await self._emit(
            step_callback,
            {
                'type': 'log',
                'content': 'planner_v2 runtime 已接管请求。\n',
            },
        )

        if resolved_case_mode not in {'structured', 'hybrid'} or not isinstance(execution_steps, list) or not execution_steps:
            await self._emit(
                step_callback,
                {
                    'type': 'log',
                    'content': 'planner_v2 当前仅支持结构化或混合步骤执行，请传入非空 task_steps。\n',
                },
            )
            return history

        normalized_steps = [self._normalize_step(raw_step, index) for index, raw_step in enumerate(execution_steps, start=1)]
        self._validate_normalized_steps(normalized_steps)
        artifact_dir, artifact_prefix = self._prepare_artifact_dir()
        if all(step.get('executor') in {'device_cli', 'data_factory'} for step in normalized_steps):
            return await self._run_device_only_plan(
                normalized_steps,
                history,
                step_callback,
                should_stop,
                artifact_dir,
                artifact_prefix,
                task_description,
                planned_tasks,
            )

        step_index_start = 1

        try:
            from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
        except ImportError as exc:
            await self._emit(
                step_callback,
                {
                    'type': 'log',
                    'content': f'planner_v2 无法启动: 缺少 playwright 依赖。{exc}\n',
                },
            )

        async with async_playwright() as playwright:
            launch_kwargs = {
                'headless': True,
                'args': [
                    '--use-gl=swiftshader',
                    '--ignore-gpu-blocklist',
                    '--no-sandbox',
                    '--enable-features=PlatformHEVCDecoderSupport',
                    '--autoplay-policy=no-user-gesture-required',
                ],
            }
            browser_executable = self._resolve_browser_executable()
            if browser_executable:
                launch_kwargs['executable_path'] = browser_executable
            browser = await playwright.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                viewport={'width': 1760, 'height': 900},
                accept_downloads=True,
            )
            page = await context.new_page()
            self._attach_runtime_observers(page)

            try:
                await self._bootstrap_pyuitest_session(page, step_callback)
                self._runtime_correlation_values = []

                for index, step in enumerate(normalized_steps, start=step_index_start):
                    if should_stop is not None and await self._check_stop(should_stop):
                        await self._emit(
                            step_callback,
                            {'type': 'log', 'content': 'planner_v2 收到停止信号，结束后续步骤执行。\n'},
                        )
                        break

                    history.planner_trace['step_retry_map'][str(index)] = 0
                    await self._emit(step_callback, {'task_id': index, 'status': 'in_progress'})
                    await self._emit(
                        step_callback,
                        {'type': 'log', 'content': f"[planner_v2] Step {index}: {step['description']}\n"},
                    )

                    started_at = time.perf_counter()
                    media_state_before = await self._capture_media_state(page)
                    from apps.ai_testing.execution.browser_observers import capture_canvas_frames, capture_visual_frames
                    visual_frames_before = await capture_visual_frames(page, step.get('assertions') or [])
                    canvas_frames_before = await capture_canvas_frames(page, step.get('assertions') or [])
                    status = 'completed'
                    error_message = None
                    last_executed_action = step.get('action')
                    action_source = 'direct'
                    screenshot_rel_path = None
                    ai_actions = None
                    action_output = None

                    try:
                        if step.get('executor') == 'device_cli':
                            device_result = await self._execute_device_cli_step(step)
                            status = 'completed' if device_result['status'] == 'PASSED' else 'failed'
                            error_message = device_result.get('stderr') or None
                            device_output = self._sanitize_device_output(
                                device_result.get('stdout'),
                                device_result.get('stderr'),
                            )
                            last_executed_action = 'device_cli'
                            action_source = 'device_cli'
                            history.artifacts.append(
                                {
                                    'type': 'command_receipt',
                                    'step': index,
                                    'device_id': step['device_id'],
                                    'operation': device_result.get('operation'),
                                    'status': device_result['status'],
                                    'exit_code': device_result.get('exit_code'),
                                    'duration_ms': device_result.get('duration_ms'),
                                    'output_preview': device_output,
                                }
                            )
                        elif step.get('executor') == 'data_factory':
                            action_output = await self._execute_data_factory_step(step)
                            self._execution_resources.append({
                                'resource_type': action_output['resource_type'],
                                'resource_id': action_output['resource_id'],
                                'resource': action_output.get('resource'),
                                'producer_step': index,
                            })
                            last_executed_action = 'create'
                            action_source = 'data_factory'
                            history.artifacts.append(
                                {
                                    'type': 'api_resource',
                                    'step': index,
                                    'resource_type': action_output['resource_type'],
                                    'resource_id': action_output['resource_id'],
                                    'resource': action_output['resource'],
                                }
                            )
                            history.artifacts.append({
                                'type': 'api_response',
                                'step': index,
                                'success': True,
                                'resource_type': action_output['resource_type'],
                                'resource_id': action_output['resource_id'],
                                'resource': action_output['resource'],
                            })
                            await self._emit(
                                step_callback,
                                {
                                    'type': 'log',
                                    'content': f"[planner_v2] Step {index} created resource {action_output['resource_type']}:{action_output['resource_id']}\n",
                                },
                            )
                        elif step.get('step_mode') == 'ai':
                            ai_actions, action_source = await self._get_ai_actions_for_step(
                                page,
                                step,
                                history,
                                step_callback=step_callback,
                                step_index=index,
                            )
                            last_executed_action = ai_actions[-1].get('action') if ai_actions else step.get('action')

                            try:
                                await self._execute_ai_actions(
                                    page,
                                    step,
                                    ai_actions,
                                    index,
                                    step_callback,
                                    PlaywrightTimeout,
                                    history=history,
                                )
                            except Exception:
                                if action_source in {'cache', 'experience'}:
                                    history.cache_stats['fallback_replan'] = history.cache_stats.get('fallback_replan', 0) + 1
                                    history.planner_trace['step_retry_map'][str(index)] = 1
                                    if action_source == 'cache':
                                        self._delete_cached_ai_actions(step)
                                    else:
                                        await self._invalidate_verified_experience(step)
                                    await self._emit(
                                        step_callback,
                                        {'type': 'log', 'content': f"[planner_v2] Step {index} reused plan failed, retrying with fresh AI plan.\n"},
                                    )
                                    ai_actions = await self._plan_ai_step(page, step)
                                    action_source = 'model'
                                    last_executed_action = ai_actions[-1].get('action') if ai_actions else step.get('action')
                                    history.cache_stats['ai_generated'] = history.cache_stats.get('ai_generated', 0) + len(ai_actions)
                                    await self._execute_ai_actions(
                                        page,
                                        step,
                                        ai_actions,
                                        index,
                                        step_callback,
                                        PlaywrightTimeout,
                                        history=history,
                                    )
                                else:
                                    raise
                        else:
                            await self._execute_step(page, step, timeout_error=PlaywrightTimeout)
                    except Exception as exc:
                        status = 'failed'
                        error_message = f'{type(exc).__name__}: {exc}'
                        await self._emit(
                            step_callback,
                            {'type': 'log', 'content': f"[planner_v2] Step {index} failed: {error_message}\n"},
                        )

                    await page.wait_for_timeout(300)
                    screenshot_path = await self._capture_screenshot(
                        page,
                        artifact_dir,
                        self._step_screenshot_filename(index),
                    )
                    if screenshot_path:
                        screenshot_rel_path = screenshot_path
                        history.artifacts.append(
                            {
                                'type': 'screenshot',
                                'step': index,
                                'status': status,
                                'path': screenshot_path,
                                'url': page.url,
                            }
                        )

                    persisted_attempt = await self._persist_step_attempt(
                        index,
                        step,
                        ai_actions[-1] if isinstance(ai_actions, list) and ai_actions else step,
                        status,
                        error_message,
                        action_output if step.get('executor') == 'data_factory' else device_output if step.get('executor') == 'device_cli' else None,
                        screenshot_rel_path,
                        page,
                        media_state_before,
                        visual_frames_before,
                        canvas_frames_before,
                    )
                    assertion_statuses = persisted_attempt.get('assertion_statuses', []) if persisted_attempt else []
                    required_statuses = self._required_assertion_statuses(step, assertion_statuses)
                    assertions_verified = self._step_assertions_are_verified(step, required_statuses)
                    action_completed = status == 'completed'
                    status = self._status_after_assertions(status, required_statuses)
                    if status != 'completed' and not error_message:
                        error_message = f'Required assertions were not verified: {", ".join(required_statuses)}.'
                    if self._should_retry_assertions(step, action_completed, assertions_verified, action_source):
                        retry_result = await self._retry_assertion_failure(
                            page, step, index, ai_actions, required_statuses, step_callback,
                            PlaywrightTimeout, history, artifact_dir,
                        )
                        if retry_result is not None:
                            status, error_message, last_executed_action, ai_actions, persisted_attempt, screenshot_rel_path = retry_result
                            assertion_statuses = persisted_attempt.get('assertion_statuses', []) if persisted_attempt else []
                            required_statuses = self._required_assertion_statuses(step, assertion_statuses)
                            assertions_verified = self._step_assertions_are_verified(step, required_statuses)
                    if action_source in {'cache', 'experience'} and assertions_verified:
                        history.cache_stats['revalidated'] = history.cache_stats.get('revalidated', 0) + 1
                        await self._record_successful_revalidation(step, persisted_attempt)
                    if (
                        status == 'completed'
                        and action_source == 'model'
                        and self.use_cache
                        and isinstance(ai_actions, list)
                        and assertions_verified
                    ):
                        await self._store_cached_ai_actions(step, ai_actions)
                        history.cache_stats['write'] = history.cache_stats.get('write', 0) + 1
                        experience_written = await self._store_verified_experience(step, ai_actions)
                        if experience_written:
                            history.cache_stats['experience_write'] = history.cache_stats.get('experience_write', 0) + 1

                    duration_seconds = round(time.perf_counter() - started_at, 2)
                    history.steps.append(
                        {
                            'step_num': index,
                            'step_description': step['description'],
                            'status': status,
                            'action': last_executed_action or step.get('action') or '-',
                            'element': step.get('selector'),
                            'thinking': self._step_thinking_text(
                                step.get('thinking'),
                                last_executed_action or step.get('action') or '-',
                            ),
                            'duration_seconds': duration_seconds,
                            'error': error_message,
                            'output': device_output if step.get('executor') == 'device_cli' else None,
                            'result': status == 'completed',
                            'source': action_source,
                            'executor': step.get('executor', 'browser'),
                            'retry_count': history.planner_trace['step_retry_map'].get(str(index), 0),
                            'step_screenshot': screenshot_rel_path,
                            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        }
                    )

                    history.case_report['steps'].append(
                        {
                            'step_num': index,
                            'step_description': step['description'],
                            'action': last_executed_action,
                            'result': status == 'completed',
                            'error': error_message,
                            'output': device_output if step.get('executor') == 'device_cli' else None,
                            'fail_screenshot': screenshot_rel_path if status == 'failed' else None,
                            'step_screenshot': screenshot_rel_path,
                            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source': action_source,
                            'executor': step.get('executor', 'browser'),
                            'retry_count': history.planner_trace['step_retry_map'].get(str(index), 0),
                        }
                    )

                    await self._emit(step_callback, {'task_id': index, 'status': status})

                    if status != 'completed':
                        history.case_report['success'] = False
                        break

                final_screenshot_path = await self._capture_screenshot(
                    page,
                    artifact_dir,
                    self._final_screenshot_filename(),
                )
                if final_screenshot_path:
                    history.artifacts.append(
                        {
                            'type': 'final_screenshot',
                            'path': final_screenshot_path,
                            'url': page.url,
                        }
                    )

                history.artifacts.append(
                    {
                        'type': 'page_state',
                        'url': page.url,
                        'title': await page.title(),
                    }
                )
                await self._teardown_pyuitest_session(page, step_callback)
                report_artifacts = self._write_case_report_artifacts(artifact_dir, artifact_prefix, history)
                if report_artifacts:
                    history.artifacts.extend(report_artifacts)
                history.planner_trace['case_report'] = history.case_report
            finally:
                try:
                    await asyncio.wait_for(context.close(), timeout=10)
                except Exception as exc:
                    logger.warning('planner_v2 context close timed out or failed: %s', exc)
                try:
                    await asyncio.wait_for(browser.close(), timeout=10)
                except Exception as exc:
                    logger.warning('planner_v2 browser close timed out or failed: %s', exc)

        for task in planned_tasks:
            if task.get('id') > len(history.steps):
                break

        return history

    def _planner_configuration_trace(self):
        configuration = self.environment_configuration
        if configuration is None:
            return None
        return {
            'id': configuration.id,
            'name': configuration.name,
            'environment': configuration.environment,
        }

    @staticmethod
    def _planner_step_trace(steps):
        return [
            {
                'executor': step.get('executor'),
                'description': step.get('description'),
                'device_id': step.get('device_id'),
                'has_command': bool(step.get('command')),
            }
            for step in steps
            if isinstance(step, dict)
        ]

    async def _run_device_only_plan(self, steps, history, step_callback, should_stop, artifact_dir, artifact_prefix, task_description, planned_tasks, start_index=1, finalize=True):
        for index, step in enumerate(steps, start=start_index):
            if should_stop is not None and await self._check_stop(should_stop):
                await self._emit(step_callback, {'type': 'log', 'content': 'Planner 收到停止信号，结束后续步骤执行。\n'})
                break
            await self._emit(step_callback, {'task_id': index, 'status': 'in_progress'})
            started_at = time.perf_counter()
            status = 'completed'
            error_message = None
            result = None
            device_output = None
            try:
                if step.get('executor') == 'data_factory':
                    resource = await self._execute_data_factory_step(step)
                    result = {
                        'status': 'PASSED',
                        'operation': 'create',
                        'stdout': f"resource={resource['resource_type']}:{resource['resource_id']}",
                        'stderr': '',
                    }
                else:
                    result = await self._execute_device_cli_step(step)
                status = 'completed' if result['status'] == 'PASSED' else 'failed'
                error_message = result.get('stderr') or None
                device_output = self._sanitize_device_output(result.get('stdout'), result.get('stderr'))
            except Exception as exc:
                status = 'failed'
                error_message = f'{type(exc).__name__}: {exc}'
            duration_seconds = round(time.perf_counter() - started_at, 2)
            history.artifacts.append({
                'type': 'command_receipt' if step.get('executor') == 'device_cli' else step.get('executor'),
                'step': index,
                'device_id': step.get('device_id'),
                'operation': (result or {}).get('operation', 'connection_check'),
                'status': (result or {}).get('status', 'ERROR'),
                'exit_code': (result or {}).get('exit_code'),
                'duration_ms': (result or {}).get('duration_ms'),
                'output_preview': device_output,
            })
            history.steps.append({
                'step_num': index,
                'step_description': step['description'],
                'status': status,
                'action': result.get('operation', step.get('executor')),
                'element': None,
                'thinking': f"executor={step.get('executor')}",
                'duration_seconds': duration_seconds,
                'error': error_message,
                'output': device_output,
                'result': status == 'completed',
                'source': step.get('executor'),
                'executor': step.get('executor'),
                'retry_count': 0,
                'step_screenshot': None,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            })
            history.case_report['steps'].append({
                'step_num': index,
                'step_description': step['description'],
                'action': result.get('operation', step.get('executor')),
                'result': status == 'completed',
                'error': error_message,
                'output': device_output,
                'source': step.get('executor'),
                'retry_count': 0,
            })
            await self._emit(step_callback, {'task_id': index, 'status': status})
            if status == 'failed':
                history.case_report['success'] = False
                break
        if finalize:
            report_artifacts = self._write_case_report_artifacts(artifact_dir, artifact_prefix, history)
            if report_artifacts:
                history.artifacts.extend(report_artifacts)
            history.planner_trace['case_report'] = history.case_report
        return history

    async def _execute_device_cli_step(self, step):
        if self.environment_configuration is None:
            raise ValueError('device_cli 步骤需要绑定全局环境配置。')
        from apps.core.device_cli_capability import DeviceCliCapability

        return await asyncio.to_thread(
            DeviceCliCapability().execute,
            self.environment_configuration,
            device_id=step['device_id'],
            operation=step.get('operation'),
            arguments=step.get('arguments'),
            command=step.get('command'),
            timeout_seconds=max(1, int(step.get('timeout_ms', 30000) / 1000)),
        )

    async def _execute_data_factory_step(self, step):
        action = str(step.get('action') or 'create').strip()
        if action == 'cleanup':
            resource_reference = step.get('resource_reference')
            if not isinstance(resource_reference, dict):
                raise ValueError('data_factory cleanup 步骤必须声明 resource_reference。')
            from apps.data_factory.resource_service import cleanup_resource

            result = await asyncio.to_thread(cleanup_resource, resource_reference)
        else:
            resource_type = str(step.get('resource_type') or '').strip()
            arguments = step.get('arguments')
            if not resource_type or not isinstance(arguments, dict):
                raise ValueError('data_factory 步骤必须声明 resource_type 和 arguments。')
            if self.environment_configuration is None:
                raise ValueError('data_factory 步骤需要绑定全局环境配置。')
            from apps.ai_testing.execution.data_factory_resources import create_configured_resource

            result = await asyncio.to_thread(
                create_configured_resource,
                self.environment_configuration,
                resource_type,
                arguments,
            )
        if not result.get('success'):
            raise AssertionError(result.get('error') or 'data factory resource operation failed')
        return result

    @staticmethod
    def _sanitize_device_output(stdout, stderr):
        output = '\n'.join(part for part in [str(stdout or '').strip(), str(stderr or '').strip()] if part)
        if not output:
            return None
        output = re.sub(r'(send\s+")[^"]+(\\r")', r'\1***\2', output, flags=re.IGNORECASE)
        output = re.sub(r'((?:password|token|authorization)\s*[:=]\s*)\S+', r'\1***', output, flags=re.IGNORECASE)
        return output[-8000:]

    async def _get_ai_actions_for_step(self, page, step, history, step_callback=None, step_index=None):
        page_context = await self._build_page_context(page)
        self._cache_context_by_step[self._step_context_key(step)] = page_context

        if self.use_cache:
            cached_actions = self._load_cached_ai_actions(step, page_context)
            if cached_actions:
                history.cache_stats['hit'] = history.cache_stats.get('hit', 0) + 1
                history.cache_stats['miss'] = max(0, history.cache_stats.get('miss', 0) - 1)
                return cached_actions, 'cache'

        experience_actions = await self._load_verified_experience(step, page_context)
        if experience_actions:
            history.cache_stats['experience_hit'] = history.cache_stats.get('experience_hit', 0) + 1
            return experience_actions, 'experience'

        ai_actions = await self._plan_ai_step_for_cacheable_step(page, step, history, step_callback=step_callback, step_index=step_index)
        return ai_actions, 'model'

    async def _plan_ai_step_for_cacheable_step(self, page, step, history, step_callback=None, step_index=None):
        ai_actions = await self._plan_ai_step_with_retries(
            page,
            step,
            history,
            step_callback=step_callback,
            step_index=step_index,
        )
        history.cache_stats['ai_generated'] = history.cache_stats.get('ai_generated', 0) + len(ai_actions)
        return ai_actions

    async def _plan_ai_step_with_retries(self, page, step, history, step_callback=None, step_index=None, max_attempts=4):
        last_error = None
        for attempt in range(1, max_attempts + 1):
            history.cache_stats['model_attempts'] = history.cache_stats.get('model_attempts', 0) + 1
            try:
                if attempt > 1:
                    history.cache_stats['model_retries'] = history.cache_stats.get('model_retries', 0) + 1
                    if step_index is not None:
                        history.planner_trace['step_retry_map'][str(step_index)] = attempt - 1
                    await self._emit(
                        step_callback,
                        {'type': 'log', 'content': f"[planner_v2] Step {step_index} planner retry {attempt}/{max_attempts}.\n"},
                    )
                planning_step = dict(step)
                if last_error is not None:
                    planning_step['_planner_failure'] = f'{type(last_error).__name__}: {last_error}'
                    planning_step['description'] = (
                        f"{step['description']}\n"
                        f"Previous plan was rejected: {type(last_error).__name__}: {last_error}. "
                        'Return a different valid action sequence based on the current screenshot.'
                    )
                    if 'selector is not visible' in str(last_error):
                        planning_step['_planner_force_visual_loc'] = True
                return await self._plan_ai_step(page, planning_step)
            except Exception as exc:
                last_error = exc
                history.artifacts.append(
                    {
                        'type': 'planner_attempt',
                        'step': step_index,
                        'attempt': attempt,
                        'status': 'failed',
                        'error': f'{type(exc).__name__}: {exc}',
                    }
                )
                if attempt >= max_attempts:
                    break
                await asyncio.sleep(min(1.0, 0.2 * attempt))

        raise ValueError(f'Hybrid AI step planner failed after {max_attempts} attempts: {last_error}')

    async def _execute_ai_actions(self, page, step, ai_actions, index, step_callback, timeout_error, history=None, remaining_replans=2):
        history_artifact = {
            'type': 'ai_plan',
            'step': index,
            'description': step['description'],
            'actions': ai_actions,
        }
        
        await self._emit(
            step_callback,
            {'type': 'log', 'content': f"[planner_v2] Step {index} planned {len(ai_actions)} direct action(s).\n"},
        )
        if history is not None:
            history.artifacts.append(history_artifact)
        for sub_index, ai_action in enumerate(ai_actions, start=1):
            if self.execution_record_id is not None:
                from apps.ai_testing.execution.capabilities import validate_browser_action

                allowed_capabilities = step.get('allowed_capabilities')
                if not isinstance(allowed_capabilities, list) or not allowed_capabilities:
                    raise ValueError('Persisted browser step is missing allowed_capabilities.')
                validate_browser_action(str(ai_action.get('action') or ''), allowed_capabilities)
            await self._emit(
                step_callback,
                {'type': 'log', 'content': f"[planner_v2] Step {index}.{sub_index}: {self._describe_action(ai_action)}\n"},
            )
            try:
                if ai_action.get('action') == 'assert' and not ai_action.get('assert_kind'):
                    action_result = None
                else:
                    action_result = await self._execute_step(page, ai_action, timeout_error=timeout_error)
                if history is not None and isinstance(action_result, dict) and action_result.get('before_path'):
                    history.artifacts.extend([
                        {'type': 'playback_before_forward', 'step': index, 'path': action_result['before_path']},
                        {'type': 'playback_after_forward', 'step': index, 'path': action_result['after_path']},
                    ])
                if history is not None and isinstance(action_result, dict) and action_result.get('download_dialog_path'):
                    history.artifacts.extend([
                        {'type': 'playback_download_dialog', 'step': index, 'path': action_result['download_dialog_path']},
                        {'type': 'playback_download_completed', 'step': index, 'path': action_result['download_completed_path']},
                    ])
            except Exception as error:
                if remaining_replans <= 0:
                    raise

                if self.execution_record_id is not None:
                    await self._persist_replan_failure(index, step, ai_action, error, page)
                replanning_step = {
                    **step,
                    'description': (
                        f"{step['description']}\n"
                        f"Previous action failed: {type(error).__name__}: {error}. "
                        'Inspect the current page and choose a different valid action sequence.'
                    ),
                }
                replan_actions = await self._plan_ai_step_with_retries(
                    page,
                    replanning_step,
                    history,
                    step_callback=step_callback,
                    step_index=index,
                )
                if history is not None:
                    history.artifacts.append({
                        'type': 'ai_replan',
                        'step': index,
                        'failed_action': ai_action,
                        'error': f'{type(error).__name__}: {error}',
                        'actions': replan_actions,
                    })
                if self.execution_record_id is not None:
                    from apps.ai_testing.execution.plan_persistence import persist_replanned_step

                    await sync_to_async(persist_replanned_step)(
                        self.execution_record_id,
                        index,
                        ai_action,
                        f'{type(error).__name__}: {error}',
                        replan_actions,
                    )
                    bindings = replan_actions[0].get('assertion_bindings', []) if replan_actions else []
                    if bindings:
                        from apps.ai_testing.execution.plan_persistence import persist_bound_step

                        await sync_to_async(persist_bound_step)(self.execution_record_id, index, bindings)
                        bound_step = self._bind_step_assertions(step, bindings)
                        step.clear()
                        step.update(bound_step)
                await self._emit(
                    step_callback,
                    {'type': 'log', 'content': f"[planner_v2] Step {index}.{sub_index}: replanning from current page.\n"},
                )
                await self._execute_ai_actions(
                    page,
                    step,
                    replan_actions,
                    index,
                    step_callback,
                    timeout_error,
                    history=history,
                    remaining_replans=remaining_replans - 1,
                )
                return

    async def _persist_replan_failure(self, step_index, step, action, error, page):
        """Record the failed action in the prior immutable plan revision."""
        await self._persist_step_attempt(
            step_index,
            step,
            action,
            'failed',
            f'{type(error).__name__}: {error}',
            None,
            None,
            page,
            None,
        )

    def _cache_file_path(self):
        try:
            from django.conf import settings

            base_dir = Path(getattr(settings, 'BASE_DIR', Path.cwd())).resolve().parent
            cache_dir = base_dir / 'Data' / 'Cache'
        except Exception:
            cache_dir = Path.cwd() / 'Data' / 'Cache'

        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / 'action_cache.json'

    def _cache_key_for_step(self, step, page_context=None):
        description = str(step.get('description') or '').strip()
        step_no = int(step.get('index') or 0)
        digest = hashlib.md5(description.encode('utf-8')).hexdigest()[:12] if description else 'no_desc'
        safe_case_name = self._safe_name(self.case_name)
        context = page_context or self._cache_context_by_step.get(self._step_context_key(step), {})
        context_payload = json.dumps(
            {
                'project_id': self.ai_project_id,
                'environment': self._experience_environment_key(),
                'permission_fingerprint': hashlib.sha256(
                    str(self.execution_user_id or '').encode('utf-8')
                ).hexdigest(),
                'page_fingerprint': context.get('fingerprint', ''),
                'application_version': context.get('application_version', ''),
                'assertion_contract': step.get('assertions', []),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        context_digest = hashlib.sha256(context_payload.encode('utf-8')).hexdigest()[:12]
        return f'{ACTION_CACHE_SCHEMA_VERSION}::{safe_case_name}::step{step_no}::{digest}::{context_digest}'

    def _read_action_cache(self):
        cache_file = self._cache_file_path()
        if not cache_file.exists():
            return {}

        try:
            payload = json.loads(cache_file.read_text(encoding='utf-8'))
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            logger.warning('planner_v2 failed to read action cache: %s', exc)
            return {}

    def _write_action_cache(self, payload):
        cache_file = self._cache_file_path()
        try:
            cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            logger.warning('planner_v2 failed to write action cache: %s', exc)

    def _load_cached_ai_actions(self, step, page_context=None):
        cache = self._read_action_cache()
        item = cache.get(self._cache_key_for_step(step, page_context))
        if not isinstance(item, dict):
            return None

        actions = item.get('actions')
        if not isinstance(actions, list) or not actions:
            return None

        return [action for action in actions if isinstance(action, dict)]

    async def _store_cached_ai_actions(self, step, actions, page_context=None):
        safe_actions = self._safe_experience_actions(actions)
        if not safe_actions:
            return

        cache = self._read_action_cache()
        context = page_context or self._cache_context_by_step.get(self._step_context_key(step), {})
        cache[self._cache_key_for_step(step, context)] = {
            'case_name': self.case_name,
            'step_num': int(step.get('index') or 0),
            'step_description': str(step.get('description') or '').strip(),
            'page_url': context.get('url', ''),
            'page_fingerprint': context.get('fingerprint', ''),
            'environment_key': self._experience_environment_key(),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'actions': safe_actions,
        }
        self._write_action_cache(cache)

    def _delete_cached_ai_actions(self, step, page_context=None):
        cache = self._read_action_cache()
        removed = cache.pop(self._cache_key_for_step(step, page_context), None)
        if removed is not None:
            self._write_action_cache(cache)

    @staticmethod
    def _step_context_key(step):
        return f"{int(step.get('index') or 0)}::{str(step.get('description') or '').strip()}"

    def _experience_environment_key(self):
        configuration = self.environment_configuration
        return str(getattr(configuration, 'environment', '') or '').strip()

    async def _build_page_context(self, page):
        if page is None:
            return {}
        raw_url = str(getattr(page, 'url', '') or '').strip()
        parsed_url = urlsplit(raw_url)
        normalized_url = urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', ''))
        page_title = ''
        page_text = ''
        application_version = ''
        try:
            page_title = str(await page.title()).strip()
            page_text = str(await page.locator('body').inner_text(timeout=1000)).strip()
            version_meta = page.locator('meta[name="application-version"]')
            version_node = page.locator('[data-app-version]')
            if await version_meta.count():
                application_version = str(
                    await version_meta.first.get_attribute('content', timeout=1000) or ''
                ).strip()
            elif await version_node.count():
                application_version = str(
                    await version_node.first.get_attribute('data-app-version', timeout=1000) or ''
                ).strip()
        except (AttributeError, RuntimeError, TypeError, TimeoutError):
            pass
        fingerprint_source = json.dumps(
            {'url': normalized_url, 'title': page_title, 'text': re.sub(r'\s+', ' ', page_text)[:4000]},
            ensure_ascii=True,
            sort_keys=True,
        )
        return {
            'url': normalized_url[:1000],
            'fingerprint': hashlib.sha256(fingerprint_source.encode('utf-8')).hexdigest(),
            'application_version': application_version,
        }

    @staticmethod
    def _intent_hash(step):
        description = re.sub(r'\s+', ' ', str(step.get('description') or '').strip().lower())
        return hashlib.sha256(description.encode('utf-8')).hexdigest()

    def _permission_fingerprint(self):
        return hashlib.sha256(str(self.execution_user_id or '').encode('utf-8')).hexdigest()

    @staticmethod
    def _assertion_contract_hash(step):
        contract = step.get('assertions', []) if isinstance(step, dict) else []
        serialized = json.dumps(contract, ensure_ascii=True, separators=(',', ':'), sort_keys=True)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    @staticmethod
    def _safe_experience_actions(actions):
        if not isinstance(actions, list) or not actions:
            return []
        serialized = json.loads(json.dumps(actions))
        for action in serialized:
            selector = str(action.get('selector') or '').lower()
            if action.get('action') == 'fill' and any(token in selector for token in ('password', 'secret', 'token')):
                return []
        return [action for action in serialized if isinstance(action, dict)]

    async def _load_verified_experience(self, step, page_context):
        if not self.ai_project_id:
            return None

        def find_experience():
            from apps.ai_testing.models import AIExecutionExperience

            queryset = AIExecutionExperience.objects.filter(
                project_id=self.ai_project_id,
                intent_hash=self._intent_hash(step),
                permission_fingerprint=self._permission_fingerprint(),
                assertion_contract_hash=self._assertion_contract_hash(step),
                status='verified',
                confidence__gte=0.7,
            )
            if page_context.get('fingerprint'):
                queryset = queryset.filter(page_fingerprint=page_context['fingerprint'])
            environment_key = self._experience_environment_key()
            if environment_key:
                queryset = queryset.filter(environment_key=environment_key)
            experience = queryset.order_by('-confidence', '-last_verified_at').first()
            return experience.action_sequence if experience is not None else None

        try:
            actions = await sync_to_async(find_experience, thread_sensitive=True)()
        except DatabaseError as error:
            logger.warning('planner_v2 failed to load verified experience: %s', error)
            return None
        return actions if isinstance(actions, list) and actions else None

    async def _store_verified_experience(self, step, actions):
        if not self.ai_project_id:
            return False
        safe_actions = self._safe_experience_actions(actions)
        if not safe_actions:
            return False
        page_context = self._cache_context_by_step.get(self._step_context_key(step), {})

        def save_experience():
            from apps.ai_testing.models import AIExecutionExperience

            lookup = {
                'project_id': self.ai_project_id,
                'intent_hash': self._intent_hash(step),
                'page_fingerprint': page_context.get('fingerprint', ''),
                'environment_key': self._experience_environment_key(),
                'permission_fingerprint': self._permission_fingerprint(),
                'assertion_contract_hash': self._assertion_contract_hash(step),
            }
            with transaction.atomic():
                experience = AIExecutionExperience.objects.select_for_update().filter(**lookup).first()
                if experience is None:
                    AIExecutionExperience.objects.create(
                        **lookup,
                        ai_case_id=self.ai_case_id,
                        execution_record_id=self.execution_record_id,
                        step_description=str(step.get('description') or '').strip(),
                        page_url=page_context.get('url', ''),
                        action_sequence=safe_actions,
                        status='pending',
                        review_status='pending',
                    )
                    return True
                experience.ai_case_id = self.ai_case_id
                experience.execution_record_id = self.execution_record_id
                experience.page_url = page_context.get('url', '')
                experience.action_sequence = safe_actions
                if experience.status == 'verified':
                    experience.success_count += 1
                    experience.confidence = min(0.95, 0.7 + experience.success_count * 0.05)
                experience.save()
                return True

        try:
            return await sync_to_async(save_experience, thread_sensitive=True)()
        except DatabaseError as error:
            logger.warning('planner_v2 failed to store verified experience: %s', error)
            return False

    async def _record_successful_revalidation(self, step, audit):
        if not self.ai_project_id or not isinstance(audit, dict):
            return
        page_context = self._cache_context_by_step.get(self._step_context_key(step), {})

        def update_experience():
            from apps.ai_testing.models import AIExecutionExperience

            return AIExecutionExperience.objects.filter(
                project_id=self.ai_project_id,
                intent_hash=self._intent_hash(step),
                page_fingerprint=page_context.get('fingerprint', ''),
                environment_key=self._experience_environment_key(),
                permission_fingerprint=self._permission_fingerprint(),
                assertion_contract_hash=self._assertion_contract_hash(step),
                status='verified',
            ).update(
                last_verified_plan_revision=audit.get('plan_revision'),
                last_verified_attempt=audit.get('attempt_number'),
                last_verified_evidence_hashes=audit.get('evidence_hashes', []),
            )

        await sync_to_async(update_experience, thread_sensitive=True)()

    async def _invalidate_verified_experience(self, step):
        if not self.ai_project_id:
            return
        page_context = self._cache_context_by_step.get(self._step_context_key(step), {})

        def invalidate_experience():
            from apps.ai_testing.models import AIExecutionExperience

            experience = AIExecutionExperience.objects.select_for_update().filter(
                project_id=self.ai_project_id,
                intent_hash=self._intent_hash(step),
                page_fingerprint=page_context.get('fingerprint', ''),
                environment_key=self._experience_environment_key(),
                permission_fingerprint=self._permission_fingerprint(),
                assertion_contract_hash=self._assertion_contract_hash(step),
                status='verified',
            ).first()
            if experience is None:
                return 0
            experience.status = 'invalid'
            experience.failure_count += 1
            experience.confidence = max(0.0, experience.confidence - 0.2)
            experience.save(update_fields=['status', 'failure_count', 'confidence', 'updated_at'])
            return 1

        try:
            await sync_to_async(invalidate_experience, thread_sensitive=True)()
        except DatabaseError as error:
            logger.warning('planner_v2 failed to invalidate reused experience: %s', error)

    def _write_case_report_artifacts(self, artifact_dir, artifact_prefix, history):
        if artifact_dir is None:
            return []

        artifacts = []
        try:
            jsonl_path = artifact_dir / f'{artifact_prefix}_report.jsonl'
            with jsonl_path.open('w', encoding='utf-8') as handle:
                handle.write(json.dumps(history.case_report, ensure_ascii=False) + '\n')
            artifacts.append({'type': 'report_jsonl', 'path': self._relative_media_path(jsonl_path)})
        except Exception as exc:
            logger.warning('planner_v2 failed to write jsonl report artifact: %s', exc)

        try:
            html_path = artifact_dir / f'{artifact_prefix}_report.html'
            html_path.write_text(self._build_case_report_html(history.case_report), encoding='utf-8')
            artifacts.append({'type': 'report_html', 'path': self._relative_media_path(html_path)})
        except Exception as exc:
            logger.warning('planner_v2 failed to write html report artifact: %s', exc)

        return artifacts

    def _build_case_report_html(self, case_report):
        steps = case_report.get('steps') or []
        rows = []
        for step in steps:
            status = 'passed' if step.get('result') else 'failed'
            rows.append(
                '<tr>'
                f"<td>{step.get('step_num')}</td>"
                f"<td>{step.get('step_description', '')}</td>"
                f"<td>{step.get('source', '')}</td>"
                f"<td>{step.get('retry_count', 0)}</td>"
                f"<td>{status}</td>"
                f"<td>{step.get('error', '') or ''}</td>"
                '</tr>'
            )

        title = str(case_report.get('case_id') or self.case_name)
        total_steps = int(case_report.get('total_steps') or len(steps))
        success = bool(case_report.get('success', False))
        return (
            '<html><head><meta charset="utf-8"><title>planner_v2 report</title>'
            '<style>body{font-family:Arial,sans-serif;margin:24px;}table{border-collapse:collapse;width:100%;}'
            'th,td{border:1px solid #ddd;padding:8px;text-align:left;}th{background:#f5f5f5;}</style></head><body>'
            f'<h1>{title}</h1>'
            f'<p>Total steps: {total_steps}</p>'
            f'<p>Status: {"passed" if success else "failed"}</p>'
            '<table><thead><tr><th>#</th><th>Description</th><th>Source</th><th>Retries</th><th>Status</th><th>Error</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></body></html>'
        )

    def _relative_media_path(self, path):
        try:
            from django.conf import settings

            return str(Path(path).relative_to(Path(settings.MEDIA_ROOT))).replace('\\', '/')
        except Exception:
            return str(path)

    def _prepare_artifact_dir(self):
        try:
            from django.conf import settings

            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            case_id_token = self._case_id_token()
            relative_dir = Path('ai_testing') / 'planner_v2' / f'{case_id_token}_{timestamp}'
            artifact_dir = Path(settings.MEDIA_ROOT) / relative_dir
            artifact_dir.mkdir(parents=True, exist_ok=True)
            return artifact_dir, case_id_token
        except Exception as exc:
            logger.warning('planner_v2 failed to prepare artifact directory: %s', exc)
            return None, self._case_id_token()

    def _case_id_token(self):
        match = re.search(r'(TC[_-]?\d+)', str(self.case_name or ''), re.IGNORECASE)
        if match:
            return self._safe_name(match.group(1).upper())
        return self._safe_name(self.case_name)

    def _step_screenshot_filename(self, step_index):
        return f'{self._case_id_token()}_step_{int(step_index):02d}.png'

    def _final_screenshot_filename(self):
        return f'{self._case_id_token()}_final.png'

    def _step_thinking_text(self, thinking, action_name):
        normalized = str(thinking or '').strip()
        if normalized:
            matched = re.fullmatch(r'planner_v2 executed action=\s*([a-z][a-z0-9_]*)\s*', normalized)
            if matched:
                return f'action={matched.group(1)}'
            return normalized

        action_value = str(action_name or '').strip()
        if action_value and action_value != '-':
            return f'action={action_value}'
        return None

    async def _persist_step_attempt(
        self,
        step_index,
        step,
        executed_action,
        status,
        error_message,
        output,
        screenshot_path,
        page,
        media_state_before,
        visual_frames_before=None,
        canvas_frames_before=None,
    ):
        if self.execution_record_id is None:
            return []

        from apps.ai_testing.execution.runtime_persistence import persist_step_attempt

        page_url = page.url or ''
        try:
            page_text = await page.locator('body').text_content(timeout=3000)
        except Exception as error:
            logger.warning('planner_v2 failed to capture DOM evidence: %s', error)
            page_text = None
        from apps.ai_testing.execution.browser_observers import BrowserObservationContext, collect_browser_observations

        environment_value = str(getattr(self.environment_configuration, 'id', '') or page_url or '')
        permission_value = str(self.execution_user_id or '')
        artifacts = [
            {'type': 'url_snapshot', 'url': page_url},
            {'type': 'page_state', 'url': page_url},
            {'type': 'planner_actionable_controls', 'controls': self._last_actionable_controls},
        ]
        artifacts.extend([
            {'type': 'network_response', **event}
            for event in self._recent_network_events[-10:]
            if isinstance(event, dict)
        ])
        if page_text is not None:
            artifacts.append({'type': 'dom_snapshot', 'text': str(page_text)})
        try:
            artifacts.extend(await collect_browser_observations(
                page,
                step.get('assertions') or [],
                BrowserObservationContext(
                    native_media_before=media_state_before,
                    visual_frames_before=tuple(visual_frames_before or []),
                    canvas_frames_before=tuple(canvas_frames_before or []),
                    download_events=tuple(self._recent_download_events),
                ),
            ))
        except Exception as error:
            logger.warning('planner_v2 failed to collect browser observations: %s', error)
        if screenshot_path:
            artifacts.append({'type': 'screenshot', 'path': screenshot_path, 'url': page_url})
        if step.get('executor') == 'data_factory' and isinstance(output, dict):
            resource_type = output.get('resource_type')
            resource_id = output.get('resource_id')
            resource = output.get('resource')
            if resource_type and resource_id is not None and isinstance(resource, dict):
                artifacts.extend([
                    {
                        'type': 'api_resource',
                        'resource_type': resource_type,
                        'resource_id': resource_id,
                        'resource': resource,
                    },
                    {
                        'type': 'api_response',
                        'success': True,
                        'resource_type': resource_type,
                        'resource_id': resource_id,
                        'resource': resource,
                    },
                ])

        persisted_attempt = await sync_to_async(persist_step_attempt)(
            self.execution_record_id,
            step_index,
            self._audit_action_payload(executed_action, step),
            {'output': output} if output is not None else {},
            'completed' if status == 'completed' else status,
            error_message or '',
            hashlib.sha256(environment_value.encode('utf-8')).hexdigest(),
            hashlib.sha256(permission_value.encode('utf-8')).hexdigest(),
            artifacts,
        )
        return {
            **persisted_attempt,
            'assertion_statuses': await self._evaluate_persisted_assertions(step_index),
        }

    @staticmethod
    def _audit_action_payload(executed_action, step):
        action = executed_action if isinstance(executed_action, dict) else {}
        return {
            'action': str(action.get('action') or executed_action or step.get('action') or ''),
            'selector': str(action.get('selector') or ''),
            'url': str(action.get('url') or ''),
            'param': str(action.get('param') or ''),
            'assert_kind': str(action.get('assert_kind') or ''),
            'value_present': bool(action.get('value')),
            'source': step.get('step_mode') or 'direct',
            'executor': step.get('executor') or 'browser',
        }

    @staticmethod
    def _bind_step_assertions(step, bindings):
        bound_step = dict(step)
        assertions = [dict(assertion) for assertion in step.get('assertions', [])]
        for binding in bindings:
            assertion = assertions[int(binding['assertion_index']) - 1]
            semantic_intent = assertion.get('target', {})
            while isinstance(semantic_intent, dict) and 'intent' in semantic_intent:
                semantic_intent = semantic_intent['intent']
            if isinstance(semantic_intent, dict) and set(semantic_intent) == {'locator'}:
                semantic_intent = semantic_intent['locator']
            assertion['target'] = {'locator': binding['locator'], 'intent': semantic_intent}
        bound_step['assertions'] = assertions
        return bound_step

    async def _evaluate_persisted_assertions(self, step_index):
        from apps.ai_testing.execution.assertion_persistence import evaluate_step_assertions

        statuses = await sync_to_async(evaluate_step_assertions)(self.execution_record_id, step_index)
        if statuses:
            logger.info('planner_v2 evaluated persisted assertions: step=%s statuses=%s', step_index, statuses)
        return statuses

    @staticmethod
    def _assertions_are_verified(statuses):
        return bool(statuses) and all(status == 'passed' for status in statuses)

    @staticmethod
    def _required_assertion_statuses(step, statuses):
        assertions = step.get('assertions', []) if isinstance(step, dict) else []
        if not isinstance(assertions, list) or not assertions:
            return list(statuses)
        return [
            status
            for assertion, status in zip(assertions, statuses)
            if not isinstance(assertion, dict) or assertion.get('required', True) is not False
        ]

    @staticmethod
    def _step_assertions_are_verified(step, required_statuses):
        assertions = step.get('assertions', []) if isinstance(step, dict) else []
        has_required_assertion = any(
            not isinstance(assertion, dict) or assertion.get('required', True) is not False
            for assertion in assertions
        )
        return not has_required_assertion or PyUICompatAgent._assertions_are_verified(required_statuses)

    @staticmethod
    def _should_retry_assertions(step, action_completed, assertions_verified, action_source):
        return (
            step.get('verification_required', True) is not False
            and action_completed
            and not assertions_verified
            and action_source == 'model'
        )

    @staticmethod
    def _status_after_assertions(action_status, assertion_statuses):
        if action_status != 'completed' or not assertion_statuses:
            return action_status
        if 'failed' in assertion_statuses:
            return 'failed'
        if any(status in {'inconclusive', 'invalid_evidence'} for status in assertion_statuses):
            return 'inconclusive'
        return action_status

    async def _retry_assertion_failure(self, page, step, step_index, actions, assertion_statuses, step_callback, timeout_error, history, artifact_dir):
        if self.execution_record_id is None:
            return None
        failure = f'Required assertions were not verified: {", ".join(assertion_statuses)}.'
        replan_limit = self._assertion_replan_limit()
        prior_actions = [self._audit_action_payload(action, step) for action in actions[-8:]]
        for attempt in range(1, replan_limit + 1):
            replanning_step = {
                **step,
                '_planner_failure': failure,
            '_prior_actions': prior_actions[-16:],
                'description': (
                    f"{step['description']}\n"
                    f'{failure} Inspect the current page evidence and choose a different action sequence.'
                ),
            }
            replan_actions = await self._plan_ai_step_with_retries(
                page, replanning_step, history, step_callback=step_callback, step_index=step_index,
            )
            from apps.ai_testing.execution.plan_persistence import persist_replanned_step

            await sync_to_async(persist_replanned_step)(
                self.execution_record_id, step_index, actions[-1] if actions else {}, failure, replan_actions,
            )
            bindings = replan_actions[0].get('assertion_bindings', []) if replan_actions else []
            if bindings:
                from apps.ai_testing.execution.plan_persistence import persist_bound_step

                await sync_to_async(persist_bound_step)(self.execution_record_id, step_index, bindings)
                bound_step = self._bind_step_assertions(step, bindings)
                step.clear()
                step.update(bound_step)
            await self._emit(
                step_callback,
                {'type': 'log', 'content': f'[planner_v2] Step {step_index}: replanning after assertion failure ({attempt}/{replan_limit}).\n'},
            )
            media_state_before = await self._capture_media_state(page)
            from apps.ai_testing.execution.browser_observers import capture_canvas_frames, capture_visual_frames
            visual_frames_before = await capture_visual_frames(page, step.get('assertions') or [])
            canvas_frames_before = await capture_canvas_frames(page, step.get('assertions') or [])
            try:
                await self._execute_ai_actions(
                    page, step, replan_actions, step_index, step_callback, timeout_error, history=history,
                )
                action_status = 'completed'
                error_message = ''
            except Exception as error:
                action_status = 'failed'
                error_message = f'{type(error).__name__}: {error}'
            screenshot_path = await self._capture_screenshot(
                page, artifact_dir, self._step_screenshot_filename(step_index),
            )
            persisted_attempt = await self._persist_step_attempt(
                step_index, step, replan_actions[-1] if replan_actions else {}, action_status,
                error_message, None, screenshot_path, page, media_state_before, visual_frames_before,
                canvas_frames_before,
            )
            statuses = persisted_attempt.get('assertion_statuses', []) if persisted_attempt else []
            required_statuses = self._required_assertion_statuses(step, statuses)
            status = self._status_after_assertions(action_status, required_statuses)
            if self._step_assertions_are_verified(step, required_statuses) or action_status != 'completed':
                return status, error_message, replan_actions[-1].get('action') if replan_actions else '', replan_actions, persisted_attempt, screenshot_path
            failure = f'Required assertions were not verified: {", ".join(required_statuses)}.'
            actions = replan_actions
            prior_actions.extend(self._audit_action_payload(action, step) for action in replan_actions)
        return status, failure, actions[-1].get('action') if actions else '', actions, persisted_attempt, screenshot_path

    def _assertion_replan_limit(self):
        settings = getattr(self.environment_configuration, 'runtime_settings', {}) or {}
        browser = settings.get('ai_testing_browser', {}) if isinstance(settings, dict) else {}
        try:
            return max(1, min(12, int(browser.get('assertion_replan_limit', 8))))
        except (TypeError, ValueError):
            return 8

    async def _capture_media_state(self, page):
        try:
            return await page.locator('video, audio').evaluate_all(
                """
                elements => elements.map(element => ({
                    tag: element.tagName.toLowerCase(),
                    paused: Boolean(element.paused),
                    ended: Boolean(element.ended),
                    readyState: Number(element.readyState),
                    networkState: Number(element.networkState),
                    currentTime: Number(element.currentTime),
                    duration: Number.isFinite(element.duration) ? Number(element.duration) : null,
                    videoWidth: Number(element.videoWidth || 0),
                    videoHeight: Number(element.videoHeight || 0),
                    currentSrc: String(element.currentSrc || element.src || ''),
                }))
                """
            )
        except Exception as error:
            logger.warning('planner_v2 failed to capture media evidence: %s', error)
            return None

    @staticmethod
    def _media_progress_seconds(before, after):
        if not isinstance(before, list) or not isinstance(after, list):
            return None
        before_times = [item.get('currentTime') for item in before if isinstance(item, dict)]
        after_times = [item.get('currentTime') for item in after if isinstance(item, dict)]
        for before_time, after_time in zip(before_times, after_times):
            try:
                return max(0.0, float(after_time) - float(before_time))
            except (TypeError, ValueError):
                continue
        return None

    def _build_planned_tasks(self, task_description, case_mode='freeform', task_steps=None):
        if case_mode in {'structured', 'hybrid'} and isinstance(task_steps, list) and task_steps:
            planned_tasks = []
            for index, step in enumerate(task_steps, start=1):
                if isinstance(step, dict):
                    description = str(step.get('description') or step.get('task') or step.get('name') or '').strip()
                    planned_task = dict(step)
                else:
                    description = str(step).strip()
                    planned_task = {}
                planned_task.update({
                    'id': index,
                    'description': description or f'步骤 {index}',
                    'status': 'pending',
                })
                planned_tasks.append(planned_task)
            return planned_tasks

        normalized_lines = [line.strip() for line in str(task_description or '').splitlines() if line.strip()]
        if not normalized_lines and str(task_description or '').strip():
            normalized_lines = [str(task_description).strip()]

        return [
            {
                'id': index,
                'description': line,
                'status': 'pending',
            }
            for index, line in enumerate(normalized_lines, start=1)
        ]

    def _describe_action(self, action):
        """Build a human-readable one-line label for a planned sub-action.

        Falls back from a meaningful author-provided description to a label
        synthesised from the action kind and its primary target, so the log no
        longer shows the generic placeholder '步骤 N' for deterministic actions.
        """
        if not isinstance(action, dict):
            return str(action)

        description = str(action.get('description') or action.get('name') or '').strip()
        if description and not re.fullmatch(r'步骤\s*\d+', description):
            return description

        kind = str(action.get('action') or '').strip() or 'action'
        assert_kind = str(action.get('assert_kind') or '').strip()
        label = f'{kind} {assert_kind}'.strip() if assert_kind else kind

        target = (
            action.get('param')
            or action.get('url')
            or action.get('value')
            or action.get('selector')
            or action.get('loc')
        )
        target = str(target).strip() if target else ''
        if len(target) > 60:
            target = f'{target[:57]}...'
        return f'{label} → {target}' if target else label

    def _normalize_step(self, raw_step, index):
        if not isinstance(raw_step, dict):
            return {
                'index': index,
                'action': 'unsupported',
                'description': str(raw_step),
            }

        action = str(
            raw_step.get('action')
            or raw_step.get('type')
            or raw_step.get('keyword')
            or ''
        ).strip().lower()
        description = str(raw_step.get('description') or raw_step.get('name') or f'步骤 {index}').strip()
        step_mode = str(raw_step.get('step_mode') or 'direct').strip().lower()
        if not action and step_mode == 'direct':
            step_mode = 'ai'
        selector = raw_step.get('selector') or raw_step.get('locator') or raw_step.get('target')
        expected = raw_step.get('expected') or raw_step.get('assert_value')
        assert_kind = str(raw_step.get('assert_kind') or '').strip().lower()
        return {
            'index': index,
            'executor': str(raw_step.get('executor') or 'browser').strip().lower(),
            'step_mode': step_mode,
            'action': action,
            'description': description,
            'allowed_capabilities': raw_step.get('allowed_capabilities') or self._direct_action_capabilities(action),
            'assertions': raw_step.get('assertions') or [],
            'verification_required': raw_step.get('verification_required', True) is not False,
            'selector': selector,
            'loc': raw_step.get('loc'),
            'param': raw_step.get('param'),
            'url': raw_step.get('url') or raw_step.get('target_url'),
            'value': raw_step.get('value') or raw_step.get('text') or raw_step.get('input_value'),
            'expected': raw_step.get('expected') or expected,
            'assert_kind': assert_kind,
            'assertion_bindings': raw_step.get('assertion_bindings') or [],
            'fields': raw_step.get('fields'),
            'selector_candidates': raw_step.get('selector_candidates'),
            'environment_id': raw_step.get('environment_id'),
            'device_id': raw_step.get('device_id'),
            'command': raw_step.get('command'),
            'resource_type': raw_step.get('resource_type'),
            'resource_reference': raw_step.get('resource_reference'),
            'operation': raw_step.get('operation'),
            'arguments': raw_step.get('arguments') or {},
            'device': raw_step.get('device'),
            'camera_index': raw_step.get('camera_index'),
            'media_path': raw_step.get('media_path'),
            'vehicle_color': raw_step.get('vehicle_color'),
            'min_count': raw_step.get('min_count'),
            'min_x': raw_step.get('min_x'),
            'min_y': raw_step.get('min_y'),
            'min_width': raw_step.get('min_width'),
            'min_height': raw_step.get('min_height'),
            'timeout_ms': int(raw_step.get('timeout_ms') or raw_step.get('wait_time') or 10000),
            'thinking': raw_step.get('thinking'),
        }

    @staticmethod
    def _direct_action_capabilities(action):
        normalized_action = str(action or '').strip().lower()
        if normalized_action == 'assert':
            return ['browser.inspect']
        if normalized_action == 'navigate':
            return ['browser.navigate']
        if normalized_action:
            return ['browser.act']
        return []

    @staticmethod
    def _validate_normalized_steps(steps):
        allowed_actions = {
            'navigate', 'click', 'double_click', 'right_click', 'hover',
            'fill', 'press', 'select', 'scroll', 'wait', 'assert',
        }
        from apps.ai_testing.execution.capabilities import validate_browser_action

        for index, step in enumerate(steps, start=1):
            if step.get('executor') != 'browser' or step.get('step_mode') == 'ai':
                continue
            action = str(step.get('action') or '').strip().lower()
            if action not in allowed_actions:
                raise ValueError(f'Planner step {index} uses unsupported browser action {action}.')
            if step.get('loc'):
                raise ValueError(f'Planner step {index} must not use fixed coordinates.')
            validate_browser_action(action, step.get('allowed_capabilities') or [])

    async def _plan_ai_step(self, page, step):
        current_url = page.url or ''
        try:
            page_title = await page.title()
        except Exception:
            page_title = ''

        try:
            page_text = await page.locator('body').text_content(timeout=3000)
        except Exception:
            page_text = ''

        normalized_text = str(page_text or '').strip()
        if len(normalized_text) > 1600:
            normalized_text = normalized_text[:1600]

        from apps.ai_testing.global_planner import VisualStepReplanner

        actionable_controls = await self._build_actionable_controls(page)
        self._last_actionable_controls = [
            {
                key: control.get(key)
                for key in ('selector', 'url', 'name', 'tag', 'role', 'rect', 'group_size', 'group_ordinal', 'top_layer', 'blocking_layer', 'z_index', 'container_text')
            }
            for control in actionable_controls[:300]
            if isinstance(control, dict)
        ]
        observable_elements = await self._build_observable_elements(page)
        try:
            page_metrics = await page.evaluate(
                """() => {
                    const selectorFor = element => {
                        const parts = [];
                        let current = element;
                        while (current && current !== document.body) {
                            const siblings = Array.from(current.parentElement.children).filter(sibling => sibling.tagName === current.tagName);
                            parts.unshift(`${current.tagName.toLowerCase()}:nth-of-type(${siblings.indexOf(current) + 1})`);
                            if (current.parentElement === document.body) return `body > ${parts.join(' > ')}`;
                            current = current.parentElement;
                        }
                        return '';
                    };
                    const scrollContainers = Array.from(document.querySelectorAll('body *')).filter(element => {
                        const style = getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0 && element.scrollHeight > element.clientHeight + 1;
                    }).map(element => ({
                        selector: selectorFor(element),
                        scroll_top: element.scrollTop,
                        scroll_height: element.scrollHeight,
                        client_height: element.clientHeight,
                        remaining: element.scrollHeight - element.clientHeight - element.scrollTop,
                    })).filter(item => item.selector && item.remaining > 1).sort((left, right) => right.remaining - left.remaining).slice(0, 20);
                    return { scroll_y: window.scrollY, scroll_height: document.documentElement.scrollHeight, viewport_height: window.innerHeight, scroll_containers: scrollContainers };
                }"""
            )
        except Exception:
            page_metrics = {}

        actions = await VisualStepReplanner().create_actions(
            step['description'],
            {
                'url': current_url,
                'title': page_title,
                'visible_text': normalized_text,
                'actionable_controls': actionable_controls,
                'observable_elements': observable_elements,
                'page_metrics': page_metrics,
                'allowed_capabilities': step.get('allowed_capabilities') or [],
                'assertions': step.get('assertions') or [],
                'execution_resources': [
                    *self._execution_resources,
                    {
                        'resource_type': 'mutation_response',
                        'resource': {
                            'result_correlation': {
                                'match_values': self._runtime_correlation_values[-50:],
                            },
                        },
                    },
                ],
                'prior_actions': step.get('_prior_actions') or [],
                'require_assertion_bindings': step.get('_require_assertion_bindings') is True,
                'error': step.get('_planner_failure', ''),
                'screenshot': await self._capture_inline_screenshot_data(page),
            },
        )
        normalized_actions = []
        for offset, action in enumerate(actions, start=1):
            normalized_action = self._normalize_step(
                {
                    **action,
                    'step_mode': 'direct',
                    'description': action.get('description') or f"{step['description']} - action {offset}",
                },
                offset,
            )
            normalized_action['thinking'] = 'planned_by=planner_vision'
            normalized_actions.append(normalized_action)
        self._validate_planned_actions(
            normalized_actions,
            step['description'],
            step.get('allowed_capabilities') or [],
        )
        return normalized_actions

    async def _build_actionable_controls(self, page):
        try:
            return await page.locator('body *').evaluate_all(
                """
                elements => elements.filter(element => {
                    const style = getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    const nativeControl = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName);
                    const interactiveRole = ['button', 'link', 'option', 'menuitem', 'row'].includes(element.getAttribute('role'));
                    const frameworkListener = Object.getOwnPropertySymbols(element).some(symbol => {
                        const value = element[symbol];
                        return String(symbol.description || '').includes('_vei') && value && typeof value === 'object' && Object.keys(value).length > 0;
                    }) || Object.getOwnPropertyNames(element).some(property => {
                        const value = element[property];
                        return property.startsWith('__reactProps') && value && typeof value === 'object' && Object.keys(value).some(key => /^on[A-Z]/.test(key));
                    });
                    const interactive = nativeControl || interactiveRole || element.hasAttribute('tabindex') || element.hasAttribute('onclick') || frameworkListener || style.cursor === 'pointer';
                    const hitTarget = document.elementFromPoint(
                        rect.left + rect.width / 2,
                        rect.top + rect.height / 2,
                    );
                    return interactive && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0 && (hitTarget === element || element.contains(hitTarget));
                }).filter(element => {
                    const rect = element.getBoundingClientRect();
                    const containsInteractive = Array.from(element.querySelectorAll('*')).some(child => {
                        const childStyle = getComputedStyle(child);
                        const childFrameworkListener = Object.getOwnPropertySymbols(child).some(symbol => String(symbol.description || '').includes('_vei')) || Object.getOwnPropertyNames(child).some(property => property.startsWith('__reactProps'));
                        return ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(child.tagName) || ['button', 'link', 'option', 'menuitem', 'row'].includes(child.getAttribute('role')) || child.hasAttribute('onclick') || childFrameworkListener || childStyle.cursor === 'pointer';
                    });
                    const nativeControl = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName);
                    const viewportRatio = (rect.width * rect.height) / Math.max(1, window.innerWidth * window.innerHeight);
                    return nativeControl || !containsInteractive || viewportRatio < 0.25;
                }).map((element, index) => {
                    const title = element.getAttribute('title');
                    const href = element.getAttribute('href');
                    const semanticChild = element.querySelector('[aria-label], [title], [alt], [data-icon], [data-lucide], svg title, svg, use');
                    const semanticClass = semanticChild && typeof semanticChild.getAttribute('class') === 'string'
                        ? semanticChild.getAttribute('class').split(/\\s+/).find(token => /icon$/i.test(token)) || ''
                        : '';
                    const semanticName = semanticChild ? (
                        semanticChild.getAttribute('aria-label')
                        || semanticChild.getAttribute('title')
                        || semanticChild.getAttribute('alt')
                        || semanticChild.getAttribute('data-icon')
                        || semanticChild.getAttribute('data-lucide')
                        || semanticChild.textContent
                        || semanticChild.getAttribute('href')
                        || semanticChild.getAttribute('xlink:href')
                        || semanticClass
                        || ''
                    ) : '';
                    const name = (element.getAttribute('aria-label') || title || element.innerText || element.value || href || semanticName || '').trim().slice(0, 120);
                    const uniqueId = element.id && document.querySelectorAll(`#${CSS.escape(element.id)}`).length === 1;
                    const attributeSelector = (attribute, value) => `[${attribute}=${JSON.stringify(value)}]`;
                    const structuralSelector = () => {
                        const parts = [];
                        let current = element;
                        while (current && current !== document.body) {
                            const siblings = Array.from(current.parentElement.children).filter(sibling => sibling.tagName === current.tagName);
                            const position = siblings.indexOf(current) + 1;
                            parts.unshift(`${current.tagName.toLowerCase()}:nth-of-type(${position})`);
                            if (current.parentElement === document.body) {
                                const candidate = `body > ${parts.join(' > ')}`;
                                if (document.querySelectorAll(candidate).length === 1) return candidate;
                            }
                            current = current.parentElement;
                        }
                        return '';
                    };
                    const selector = uniqueId ? `#${CSS.escape(element.id)}` : element.dataset.testid ? attributeSelector('data-testid', element.dataset.testid) : element.getAttribute('aria-label') ? attributeSelector('aria-label', element.getAttribute('aria-label')) : title ? attributeSelector('title', title) : href ? attributeSelector('href', href) : structuralSelector();
                    const url = href ? new URL(href, document.baseURI).href : '';
                    const rect = element.getBoundingClientRect();
                    const depth = (() => { let value = 0; let current = element; while (current && current !== document.body) { value += 1; current = current.parentElement; } return value; })();
                    const nativeControl = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName);
                    const containerText = (element.parentElement?.innerText || '').trim().slice(0, 240);
                    const className = typeof element.className === 'string' ? element.className.trim() : '';
                    const group = className ? Array.from(element.parentElement.children).filter(sibling => sibling.tagName === element.tagName && sibling.className === element.className) : [element];
                    const dialog = element.closest('[role="dialog"], dialog, [aria-modal="true"]');
                    const positioned = (() => { let current = element; while (current && current !== document.body) { const style = getComputedStyle(current); const zIndex = Number.parseInt(style.zIndex, 10) || 0; if (['fixed', 'sticky'].includes(style.position) || zIndex > 0) return current; current = current.parentElement; } return null; })();
                    const positionedRect = positioned?.getBoundingClientRect();
                    const positionedRatio = positionedRect ? (positionedRect.width * positionedRect.height) / Math.max(1, window.innerWidth * window.innerHeight) : 0;
                    const zIndex = Number.parseInt(getComputedStyle(dialog || positioned || element).zIndex, 10) || 0;
                    const topLayer = Boolean(dialog || positioned || zIndex > 0);
                    const blockingLayer = Boolean(dialog || (positioned && getComputedStyle(positioned).position === 'fixed' && positionedRatio >= 0.3));
                    return { index, tag: element.tagName.toLowerCase(), role: element.getAttribute('role') || '', name, selector, url, native_control: nativeControl, editable: !element.hasAttribute('readonly') && !element.hasAttribute('disabled'), depth, container_text: containerText, group_size: group.length, group_ordinal: group.indexOf(element), top_layer: topLayer, blocking_layer: blockingLayer, z_index: zIndex, rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) } };
                }).filter(control => control.selector || control.name).sort((left, right) => {
                    const blockingLayerRank = Number(right.blocking_layer) - Number(left.blocking_layer);
                    const namedRank = Number(Boolean(right.name)) - Number(Boolean(left.name));
                    const nativeRank = Number(right.native_control) - Number(left.native_control);
                    const topLayerRank = Number(right.top_layer) - Number(left.top_layer);
                    const repeatedRank = Number(right.group_size > 1) - Number(left.group_size > 1);
                    return blockingLayerRank || namedRank || nativeRank || topLayerRank || right.z_index - left.z_index || repeatedRank || left.rect.y - right.rect.y || left.rect.x - right.rect.x || left.depth - right.depth;
                }).slice(0, 300);
                """
            )
        except Exception:
            return []

    async def _build_observable_elements(self, page):
        try:
            return await page.locator('body *').evaluate_all(
                """
                elements => elements.filter(element => {
                    const style = getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    const text = (element.getAttribute('aria-label') || element.getAttribute('title') || element.getAttribute('alt') || element.innerText || element.value || '').trim();
                    const ratio = (rect.width * rect.height) / Math.max(1, window.innerWidth * window.innerHeight);
                    return element.parentElement !== document.body && text && text.length <= 240 && ratio < 0.25 && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                }).slice(0, 200).map((element, index) => {
                    const structuralSelector = () => {
                        const parts = [];
                        let current = element;
                        while (current && current !== document.body) {
                            const siblings = Array.from(current.parentElement.children).filter(sibling => sibling.tagName === current.tagName);
                            parts.unshift(`${current.tagName.toLowerCase()}:nth-of-type(${siblings.indexOf(current) + 1})`);
                            if (current.parentElement === document.body) {
                                const candidate = `body > ${parts.join(' > ')}`;
                                if (document.querySelectorAll(candidate).length === 1) return candidate;
                            }
                            current = current.parentElement;
                        }
                        return '';
                    };
                    const text = (element.getAttribute('aria-label') || element.getAttribute('title') || element.getAttribute('alt') || element.innerText || element.value || '').trim().slice(0, 240);
                    const rect = element.getBoundingClientRect();
                    return { index, tag: element.tagName.toLowerCase(), text, selector: structuralSelector(), rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) } };
                }).filter(element => element.selector);
                """
            )
        except Exception:
            return []

    async def _capture_inline_screenshot_data(self, page):
        try:
            screenshot_bytes = await page.screenshot(type='png', full_page=False, timeout=10000)
        except Exception as exc:
            logger.warning('planner_v2 failed to capture inline screenshot for vision planning: %s', exc)
            screenshot_bytes = await self._capture_inline_screenshot_via_cdp(page)
            if screenshot_bytes is None:
                return None

        encoded = base64.b64encode(screenshot_bytes).decode('ascii')
        return f'data:image/png;base64,{encoded}'

    async def _capture_inline_screenshot_via_cdp(self, page):
        try:
            context = page.context
            session = await context.new_cdp_session(page)
            payload = await session.send('Page.captureScreenshot', {'format': 'png'})
            data = payload.get('data')
            if not data:
                return None
            return base64.b64decode(data)
        except Exception as exc:
            logger.warning('planner_v2 failed to capture inline screenshot via CDP: %s', exc)
            return None

    def _extract_response_content(self, response):
        choices = response.get('choices') or []
        if not choices:
            return ''
        message = choices[0].get('message') or {}
        content = message.get('content')
        if isinstance(content, list):
            return ''.join(part.get('text', '') for part in content if isinstance(part, dict))
        return str(content or '')

    def _parse_ai_actions(self, content):
        normalized = str(content or '').strip()
        if not normalized:
            raise ValueError('Hybrid AI step planner returned empty content')

        decoder = json.JSONDecoder()
        candidates = []

        fence_matches = re.findall(r'```(?:json)?\s*(\[.*?\])\s*```', normalized, re.S)
        candidates.extend(fence_matches)

        for match in re.finditer(r'\[', normalized):
            try:
                parsed, end = decoder.raw_decode(normalized[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                candidates.append(normalized[match.start():match.start() + end])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict) and isinstance(parsed.get('actions'), list):
                return [item for item in parsed.get('actions', []) if isinstance(item, dict)]

        try:
            parsed = json.loads(normalized.lstrip('\ufeff'))
        except json.JSONDecodeError as exc:
            preview = normalized[:240].replace('\n', '\\n')
            raise ValueError(f'Hybrid AI step planner returned non-JSON content: {preview}') from exc

        if isinstance(parsed, dict) and isinstance(parsed.get('actions'), list):
            return [item for item in parsed.get('actions', []) if isinstance(item, dict)]
        if not isinstance(parsed, list):
            raise ValueError('Hybrid AI step planner must return a JSON array')
        return [item for item in parsed if isinstance(item, dict)]

    @staticmethod
    def _validate_planned_actions(actions, step_description='', allowed_capabilities=None):
        allowed_actions = {
            'navigate', 'click', 'double_click', 'right_click', 'hover',
            'fill', 'press', 'select', 'scroll', 'wait', 'assert',
        }
        from apps.ai_testing.execution.capabilities import validate_browser_action

        for index, action in enumerate(actions, start=1):
            name = str(action.get('action') or '').strip()
            if not name:
                raise ValueError(f'Planner action {index} is missing action')
            if name not in allowed_actions:
                raise ValueError(f'Planner action {index} uses unsupported action {name}')
            if action.get('loc'):
                raise ValueError(f'Planner action {index} must not use fixed coordinates')
            if name in {'click', 'double_click', 'right_click', 'hover'} and not str(action.get('selector') or '').strip():
                raise ValueError(f'Planner action {index} {name} requires selector')
            if name == 'navigate' and not action.get('url'):
                raise ValueError(f'Planner action {index} navigate requires url')
            if name in {'fill', 'press', 'select'} and not action.get('value'):
                raise ValueError(f'Planner action {index} {name} requires value')
            if allowed_capabilities is not None:
                validate_browser_action(name, allowed_capabilities)

    def _normalize_text_for_contains(self, text):
        return re.sub(r'\s+', '', str(text or '').strip())

    def _attach_runtime_observers(self, page):
        self._recent_network_events = []
        self._recent_download_events = []

        async def on_response(response):
            try:
                request = response.request
                method = str(request.method or '').upper()
                if method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
                    return
                url = str(response.url or '')
                lowered_url = url.lower()
                if any(fragment in lowered_url for fragment in ('/v1/traces', 'apm', 'sentry', 'telemetry', 'analytics')):
                    return
                self._recent_network_events.append(
                    {
                        'ts': time.time(),
                        'method': method,
                        'url': url,
                        'status': int(response.status),
                        'ok': bool(response.ok),
                    }
                )
                self._recent_network_events = self._recent_network_events[-50:]
                if response.ok:
                    try:
                        payload = await response.json()
                    except (TypeError, ValueError):
                        payload = None
                    self._runtime_correlation_values.extend(self._extract_correlation_values(payload))
                    self._runtime_correlation_values = list(dict.fromkeys(self._runtime_correlation_values))[-50:]
            except Exception:
                logger.debug('planner_v2 failed to record runtime response', exc_info=True)

        page.on('response', on_response)

    @staticmethod
    def _extract_correlation_values(payload):
        values = []
        sensitive_keys = {'access', 'authorization', 'credential', 'password', 'refresh', 'secret', 'token'}

        def collect(value, key=''):
            if any(term in key.casefold() for term in sensitive_keys):
                return
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    collect(child_value, str(child_key))
                return
            if isinstance(value, list):
                for child_value in value[:50]:
                    collect(child_value, key)
                return
            if isinstance(value, bool) or value is None:
                return
            text = str(value).strip()
            if 3 <= len(text) <= 128:
                values.append(text)

        collect(payload)
        return values[:50]

        def on_download(download):
            async def capture_download_result():
                try:
                    failure = await download.failure()
                    self._recent_download_events.append({
                        'status': 'failed' if failure else 'completed',
                        'filename': str(download.suggested_filename or ''),
                    })
                except Exception as error:
                    self._recent_download_events.append({'status': 'failed', 'error': type(error).__name__})
                self._recent_download_events = self._recent_download_events[-20:]

            asyncio.create_task(capture_download_result())

        page.on('download', on_download)

    def _parse_point(self, raw_value):
        text = str(raw_value or '').strip()
        match = re.match(r'^\(?\s*(\d+)\s*,\s*(\d+)\s*\)?$', text)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    async def _resolve_locator(self, page, selector):
        target = str(selector or '').strip()
        if not target:
            return None
        text_target = target[5:].strip() if target.startswith('text=') else target
        try:
            locator = page.locator(target)
            try:
                await locator.first.wait_for(state='visible', timeout=3000)
            except Exception:
                pass
            visible_locator = await self._first_visible_locator(locator)
            if visible_locator is not None:
                return visible_locator
        except Exception:
            pass
        try:
            text_locator = page.get_by_text(text_target, exact=False)
            try:
                await text_locator.first.wait_for(state='visible', timeout=3000)
            except Exception:
                pass
            return await self._first_visible_locator(text_locator)
        except Exception:
            return None

    @staticmethod
    async def _first_visible_locator(locator):
        count = await locator.count()
        for index in range(count):
            candidate = locator.nth(index) if hasattr(locator, 'nth') else locator.first
            is_visible = getattr(candidate, 'is_visible', None)
            if not callable(is_visible):
                return candidate
            try:
                if await is_visible():
                    return candidate
            except Exception:
                continue
        return None

    async def _has_visible_text_candidate(self, page, text):
        if not text:
            return False
        try:
            locator = page.get_by_text(str(text), exact=False)
            count = await locator.count()
            for idx in range(count):
                try:
                    if await locator.nth(idx).is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _sidebar_hover_keywords(self, step):
        haystack = ' '.join(
            str(step.get(key) or '')
            for key in ('description', 'selector', 'param', 'value', 'expected')
        ).lower()

        if any(token in haystack for token in ('组织', 'organization', 'site', 'team', '三个人')):
            return ['Organization', 'Site', 'Team']
        return []

    async def _hover_sidebar_icon_fallback(self, page, step):
        keywords = self._sidebar_hover_keywords(step)
        if not keywords:
            return False

        icon_locator = page.locator('svg')
        icon_count = await icon_locator.count()
        for idx in range(icon_count):
            icon = icon_locator.nth(idx)
            try:
                if not await icon.is_visible():
                    continue
                box = await icon.bounding_box()
            except Exception:
                continue

            if not box:
                continue
            if box.get('x', 9999) > 96:
                continue
            if box.get('width', 0) < 12 or box.get('height', 0) < 12:
                continue

            await page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            await page.wait_for_timeout(300)

            for keyword in keywords:
                if await self._has_visible_text_candidate(page, keyword):
                    return True
        return False

    async def _execute_step(self, page, step, timeout_error):
        action = step['action']
        timeout_ms = int(step.get('timeout_ms') or 10000)
        selector = str(step.get('selector') or '').strip()
        loc = step.get('loc')
        param = step.get('param')

        if action in {'navigate', 'navigate_to', 'goto'}:
            target_url = str(step.get('url') or step.get('value') or '').strip()
            if not target_url:
                raise ValueError('navigate step requires url')
            await page.goto(target_url, wait_until='commit', timeout=timeout_ms)
            try:
                await page.wait_for_load_state('domcontentloaded', timeout=min(timeout_ms, 15000))
            except timeout_error:
                logger.warning('planner_v2 navigate domcontentloaded timeout, continue with current page state')
            return

        if action in {'click'}:
            locator = await self._resolve_locator(page, selector) if selector else None
            point = self._parse_point(loc) or self._parse_point(param)
            if locator is not None:
                await locator.click(timeout=timeout_ms)
            elif point is not None:
                await page.mouse.click(point[0], point[1])
            elif selector:
                raise ValueError(f'click selector did not resolve on the current page: {selector}')
            else:
                raise ValueError('click step requires selector or loc')
            return

        if action in {'double_click'}:
            locator = await self._resolve_locator(page, selector) if selector else None
            point = self._parse_point(loc) or self._parse_point(param)
            if locator is not None:
                await locator.dblclick(timeout=timeout_ms)
            elif point is not None:
                await page.mouse.dblclick(point[0], point[1])
            else:
                raise ValueError('double_click step requires selector or loc')
            return

        if action in {'right_click'}:
            locator = await self._resolve_locator(page, selector) if selector else None
            point = self._parse_point(loc) or self._parse_point(param)
            if locator is not None:
                await locator.click(timeout=timeout_ms, button='right')
            elif point is not None:
                await page.mouse.click(point[0], point[1], button='right')
            else:
                raise ValueError('right_click step requires selector or loc')
            return

        if action in {'hover'}:
            locator = await self._resolve_locator(page, selector) if selector else None
            point = self._parse_point(loc) or self._parse_point(param)
            if locator is not None:
                try:
                    await locator.hover(timeout=timeout_ms)
                except Exception:
                    if point is None and await self._hover_sidebar_icon_fallback(page, step):
                        return
                    raise
            elif point is not None:
                await page.mouse.move(point[0], point[1])
            elif await self._hover_sidebar_icon_fallback(page, step):
                return
            else:
                raise ValueError('hover step requires selector or loc')
            return

        if action in {'type', 'fill', 'input'}:
            value = str(step.get('value') or param or '').strip()
            locator = await self._resolve_locator(page, selector) if selector else None
            point = self._parse_point(loc)
            if locator is not None:
                await locator.fill(value, timeout=timeout_ms)
            elif point is not None:
                await page.mouse.click(point[0], point[1])
                await page.keyboard.type(value)
            else:
                raise ValueError('type/fill step requires selector or loc')
            return

        if action in {'press', 'keyboard_press', 'key', 'hotkey'}:
            value = str(step.get('value') or param or '').strip()
            locator = await self._resolve_locator(page, selector) if selector else None
            if not value:
                raise ValueError('press step requires value')
            if locator is not None:
                await locator.press(value, timeout=timeout_ms)
            else:
                await page.keyboard.press(value)
            return

        if action in {'select', 'select_option'}:
            selector = str(step.get('selector') or '').strip()
            value = str(step.get('value') or '').strip()
            if not selector:
                raise ValueError('select step requires selector')
            if not value:
                raise ValueError('select step requires value')
            await page.locator(selector).first.select_option(value, timeout=timeout_ms)
            return

        if action in {'wait', 'sleep'}:
            raw_wait = step.get('value') or param
            try:
                wait_ms = max(0, int(str(raw_wait).strip())) if raw_wait not in (None, '') else max(0, timeout_ms)
            except (TypeError, ValueError):
                wait_ms = max(0, timeout_ms)
            await page.wait_for_timeout(wait_ms)
            return

        if action in {'scroll'}:
            direction = str(param or step.get('value') or 'down').strip().lower()
            if selector:
                delta = -0.8 if direction in {'up', 'pageup'} else 0.8
                await page.locator(selector).first.evaluate(
                    '(element, ratio) => element.scrollBy({ top: element.clientHeight * ratio, behavior: "instant" })',
                    delta,
                )
                return
            key = 'PageDown' if direction in {'down', 'pagedown'} else 'PageUp'
            await page.keyboard.press(key)
            return

        if action in {'assert'}:
            assert_kind = str(step.get('assert_kind') or '').strip().lower()
            from apps.ai_testing.execution.assertion_registry import ASSERTION_KINDS

            if assert_kind in ASSERTION_KINDS:
                return
            expected = str(step.get('expected') or param or '').strip()
            if assert_kind == 'text_visible':
                target_text = str(param or step.get('value') or '').strip()
                locator = page.get_by_text(target_text, exact=False).first
                if str(expected or 'True').lower() in {'false', '0', 'no'}:
                    try:
                        await locator.wait_for(state='hidden', timeout=timeout_ms)
                    except Exception:
                        pass
                    if await locator.is_visible():
                        raise AssertionError(f"text '{target_text}' is still visible")
                else:
                    await locator.wait_for(state='visible', timeout=timeout_ms)
                return

            if assert_kind == 'url_contains':
                current_url = page.url or ''
                if str(param or expected) not in current_url:
                    raise AssertionError(f"current url '{current_url}' does not contain '{param or expected}'")
                return

            if assert_kind == 'placeholder_equals':
                locator = await self._resolve_locator(page, selector or "input")
                if locator is None:
                    raise AssertionError('placeholder_equals requires a resolvable selector')
                placeholder = str(await locator.get_attribute('placeholder') or '')
                value = str(await locator.input_value() or '')
                target = str(param or expected).strip()
                if target not in placeholder and target not in value:
                    raise AssertionError(f"placeholder/value does not contain '{target}'")
                return

            if assert_kind == 'selector_non_empty':
                selector_candidates = step.get('selector_candidates') or []
                min_count = int(step.get('min_count') or 1)
                min_x = step.get('min_x')
                min_y = step.get('min_y')
                min_width = step.get('min_width')
                min_height = step.get('min_height')
                visible_count = 0
                for candidate in selector_candidates:
                    try:
                        locator = page.locator(str(candidate))
                        count = await locator.count()
                        for idx in range(min(count, 20)):
                            try:
                                item = locator.nth(idx)
                                if not await item.is_visible(timeout=300):
                                    continue
                                if any(value is not None for value in (min_x, min_y, min_width, min_height)):
                                    box = await item.bounding_box()
                                    if not isinstance(box, dict):
                                        continue
                                    if min_x is not None and float(box.get('x') or 0) < float(min_x):
                                        continue
                                    if min_y is not None and float(box.get('y') or 0) < float(min_y):
                                        continue
                                    if min_width is not None and float(box.get('width') or 0) < float(min_width):
                                        continue
                                    if min_height is not None and float(box.get('height') or 0) < float(min_height):
                                        continue
                                visible_count += 1
                            except Exception:
                                continue
                        if not _is_false_like(expected) and visible_count >= min_count:
                            return
                    except Exception:
                        continue
                if _is_false_like(expected):
                    if visible_count > 0:
                        raise AssertionError(f'selector_non_empty expected no visible matches, got {visible_count}')
                    return
                raise AssertionError(f'selector_non_empty failed: visible_count={visible_count}, min_count={min_count}')

            if assert_kind == 'field_values_match':
                fields = step.get('fields') or []
                if not isinstance(fields, list) or not fields:
                    raise AssertionError('field_values_match requires non-empty fields')

                def normalize_text(value):
                    return str(value or '').strip()

                def normalize_phone_digits(value):
                    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
                    return digits[1:] if digits.startswith('1') and len(digits) == 11 else digits

                for field in fields:
                    name = str(field.get('name') or field.get('selector') or 'field')
                    field_selector = str(field.get('selector') or '').strip()
                    expected_value = str(field.get('expected') or '').strip()
                    match_mode = str(field.get('match') or 'exact').strip().lower()
                    if not field_selector:
                        raise AssertionError(f'{name} is missing selector')
                    locator = page.locator(field_selector).first
                    if expected_value:
                        try:
                            await page.wait_for_function(
                                """
                                ([selector, expected]) => {
                                  const el = document.querySelector(selector);
                                  if (!el) return false;
                                  const value = typeof el.value === 'string' ? el.value.trim() : '';
                                  const text = (el.textContent || '').trim();
                                  return value === expected || text === expected || value.length > 0 || text.length > 0;
                                }
                                """,
                                arg=[field_selector, expected_value],
                                timeout=min(timeout_ms, 5000),
                            )
                        except Exception:
                            pass

                    actual_value = str(await locator.input_value(timeout=timeout_ms) or '')
                    if not actual_value:
                        actual_value = str(await locator.evaluate("el => (typeof el.value === 'string' && el.value) || el.getAttribute('value') || el.textContent || ''") or '')

                    if match_mode == 'phone_digits':
                        if normalize_phone_digits(actual_value) != normalize_phone_digits(expected_value):
                            raise AssertionError(f"{name} value '{actual_value}' does not match '{expected_value}'")
                        continue

                    if normalize_text(actual_value) != normalize_text(expected_value):
                        raise AssertionError(f"{name} value '{actual_value}' does not match '{expected_value}'")
                return

            if assert_kind == 'video_visible':
                expected_video = str(param or expected or '').strip()
                video_selector = selector or 'video'
                locator = page.locator(video_selector)
                count = await locator.count()
                for idx in range(min(count, 10)):
                    item = locator.nth(idx)
                    try:
                        if not await item.is_visible(timeout=300):
                            continue
                        if not expected_video:
                            return
                        src = (await item.get_attribute('src')) or ''
                        poster = (await item.get_attribute('poster')) or ''
                        if expected_video in f'{src} {poster}':
                            return
                    except Exception:
                        continue
                raise AssertionError(f"video_visible failed for '{expected_video}'")

            if assert_kind == 'stream_active':
                await self._assert_stream_active(page, timeout_ms)
                return

            if assert_kind == 'page_dark_theme':
                    expected_true = not _is_false_like(expected)
                    is_dark = await page.evaluate(
                            """
                            () => {
                                const root = document.documentElement;
                                const body = document.body;
                                const darkClassPattern = /(dark|night|theme-dark)/i;

                                const hasDarkClass =
                                    (root && darkClassPattern.test(root.className || '')) ||
                                    (body && darkClassPattern.test(body.className || ''));

                                const parseRgb = (raw) => {
                                    if (!raw) return null;
                                    const match = String(raw).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
                                    if (!match) return null;
                                    return [Number(match[1]), Number(match[2]), Number(match[3])];
                                };

                                const pickColor = (el) => {
                                    if (!el) return null;
                                    const c = window.getComputedStyle(el).backgroundColor;
                                    const rgb = parseRgb(c);
                                    if (!rgb) return null;
                                    const [r, g, b] = rgb;
                                    const isTransparent = r === 0 && g === 0 && b === 0 && /rgba\(0,\s*0,\s*0,\s*0\)/i.test(String(c));
                                    return isTransparent ? null : rgb;
                                };

                                const rgb = pickColor(body) || pickColor(root);
                                let luminance = null;
                                let bgColor = null;
                                if (rgb) {
                                    const [r, g, b] = rgb;
                                    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
                                    bgColor = `rgb(${r}, ${g}, ${b})`;
                                }

                                const darkByColor = luminance !== null ? luminance < 110 : false;
                                return {
                                    isDark: Boolean(hasDarkClass || darkByColor),
                                    hasDarkClass: Boolean(hasDarkClass),
                                    bgColor,
                                    luminance,
                                };
                            }
                            """
                    )
                    actual_dark = bool((is_dark or {}).get('isDark'))
                    if actual_dark != expected_true:
                            raise AssertionError(
                                    'page_dark_theme failed: '
                                    f"expected_dark={expected_true}, actual_dark={actual_dark}, details={is_dark}"
                            )
                    return

            raise ValueError(f'unsupported assert kind: {assert_kind}')

        raise ValueError(f"unsupported planner_v2 action: {action}")

    async def _assert_stream_active(self, page, timeout_ms):
        loading_markers = ['Loading streaming...', 'No Signal', 'Reconnect', 'Stream unavailable']

        async def visible_loading_marker():
            for marker in loading_markers:
                locator = page.get_by_text(marker, exact=False)
                try:
                    if await locator.count() and await locator.first.is_visible():
                        return marker
                except Exception:
                    continue
            return None

        # Wait for the player to finish buffering before judging liveness. A live
        # stream can briefly show a loading/reconnect placeholder right after the
        # camera is opened; only treat it as failed if the marker is still present
        # once the load budget is exhausted.
        load_deadline = time.monotonic() + min(max(timeout_ms, 15000), 30000) / 1000.0
        marker = await visible_loading_marker()
        while marker and time.monotonic() < load_deadline:
            await page.wait_for_timeout(1000)
            marker = await visible_loading_marker()
        if marker:
            raise AssertionError(f"stream is not active: visible marker '{marker}'")

        video_locator = page.locator('video')
        video_count = await video_locator.count()
        for idx in range(min(video_count, 5)):
            target = video_locator.nth(idx)
            try:
                state = await target.evaluate(
                    """
                    el => ({
                      currentTime: Number(el.currentTime || 0),
                      paused: Boolean(el.paused),
                      ended: Boolean(el.ended),
                      readyState: Number(el.readyState || 0),
                      videoWidth: Number(el.videoWidth || 0),
                      videoHeight: Number(el.videoHeight || 0)
                    })
                    """
                )
            except Exception:
                continue
            if (
                isinstance(state, dict)
                and not bool(state.get('paused', True))
                and not bool(state.get('ended', False))
                and float(state.get('currentTime') or 0) > 0
                and int(state.get('readyState') or 0) >= 2
                and int(state.get('videoWidth') or 0) > 0
                and int(state.get('videoHeight') or 0) > 0
            ):
                return

        candidate_box = None
        candidate_media = None
        surface_deadline = time.monotonic() + max(timeout_ms, 1000) / 1000.0
        while time.monotonic() < surface_deadline and candidate_box is None:
            media_locator = page.locator('img, canvas, video')
            candidate_area = 0.0
            for idx in range(min(await media_locator.count(), 20)):
                target = media_locator.nth(idx)
                try:
                    if not await target.is_visible(timeout=300):
                        continue
                    box = await target.bounding_box()
                    if not isinstance(box, dict):
                        continue
                    width = float(box.get('width') or 0)
                    height = float(box.get('height') or 0)
                    if (
                        float(box.get('x') or 0) >= 420
                        and float(box.get('y') or 0) >= 60
                        and width >= 600
                        and height >= 320
                    ):
                        area = width * height
                        if area > candidate_area:
                            candidate_area = area
                            candidate_box = box
                            candidate_media = target
                except Exception:
                    continue
            if candidate_box is None:
                await page.wait_for_timeout(500)

        if candidate_box is None:
            raise AssertionError('stream is not active: no large visible media surface found')

        # Confirm genuine playback by sampling the rendered media region for real
        # motion. The loading markers are already gone at this point, so any
        # animated loading spinner is no longer on screen; a live, decoding stream
        # keeps producing new frames (its burned-in timestamp ticks every second),
        # while a frozen single-frame snapshot, poster image, or stalled player
        # yields identical samples. A clipped page screenshot is used because it
        # composites GPU-backed canvas/video layers (an element screenshot can
        # return a stale backing buffer). Network/websocket traffic is deliberately
        # NOT used as a signal: data can keep arriving while buffering without the
        # video ever decoding, which would be a false pass.
        clip = {
            'x': float(candidate_box.get('x') or 0),
            'y': float(candidate_box.get('y') or 0),
            'width': float(candidate_box.get('width') or 0),
            'height': float(candidate_box.get('height') or 0),
        }
        sample_interval_ms = 1000
        sample_deadline = time.monotonic() + min(max(timeout_ms, 12000), 20000) / 1000.0
        hashes = set()
        # Require several distinct frames so transient compression noise on an
        # otherwise static image cannot be mistaken for live playback.
        required_distinct = 3
        while True:
            if hasattr(page, 'screenshot'):
                screenshot_bytes = await page.screenshot(type='png', clip=clip)
            elif candidate_media is not None:
                screenshot_bytes = await candidate_media.screenshot(type='png')
            else:
                raise AssertionError('stream preview could not be captured')
            hashes.add(hashlib.md5(screenshot_bytes).hexdigest())
            if len(hashes) >= required_distinct:
                return
            if time.monotonic() >= sample_deadline:
                break
            await page.wait_for_timeout(sample_interval_ms)

        raise AssertionError(
            'stream preview did not change '
            f'(only {len(hashes)} distinct frame(s) across samples)'
        )

    async def _bootstrap_pyuitest_session(self, page, step_callback):
        from apps.core.browser_auth import resolve_browser_login

        login = resolve_browser_login(self.environment_configuration)
        if login is None:
            return

        current_url = str(page.url or '').strip()
        if '/dashboard/' in current_url:
            return

        await self._emit(step_callback, {'type': 'log', 'content': f'[planner_v2] Bootstrap navigate: {login.login_url}\n'})
        navigation_committed = False
        try:
            await page.goto(login.login_url, wait_until='commit', timeout=60000)
            navigation_committed = True
        except Exception as exc:
            current_url = str(page.url or '').strip()
            navigation_committed = current_url.startswith(login.login_url)
            logger.warning(
                'planner_v2 bootstrap load wait timeout, current_url=%s committed=%s: %s',
                current_url,
                navigation_committed,
                exc,
            )
            if not navigation_committed:
                await page.goto(login.login_url, wait_until='commit', timeout=60000)

        try:
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
        except Exception:
            logger.warning('planner_v2 bootstrap domcontentloaded timeout, continue probing login form')

        await page.wait_for_timeout(5000)

        login_ready = await self._wait_login_page_ready(page, timeout_ms=180000)
        if not login_ready:
            if '/dashboard/' not in str(page.url or ''):
                logger.warning('planner_v2 login form not detected after extended wait, reload once and retry')
                await page.reload(wait_until='commit', timeout=60000)
                login_ready = await self._wait_login_page_ready(page, timeout_ms=240000)
            if '/dashboard/' in str(page.url or ''):
                return
            if not login_ready:
                await self._capture_bootstrap_debug(page, step_callback, 'login_form_not_ready')
            raise AssertionError('planner_v2 bootstrap could not find login form')

        if login.username and login.password:
            last_login_error = None
            for login_attempt in range(1, 4):
                await page.locator('input[id="login_email"], input[type="email"], input[name*="email" i], input[placeholder*="email" i]').first.fill(login.username, timeout=10000)
                await page.locator('input[id="login_password"], input[type="password"], input[name*="password" i], input[placeholder*="password" i]').first.fill(login.password, timeout=10000)
                await page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Login"), button:has-text("Log in")').first.click(timeout=10000)
                await page.wait_for_timeout(1000)
                terms_prompt = page.get_by_text('I have read and agree to the Terms of Use.', exact=False).first
                if await terms_prompt.is_visible():
                    await terms_prompt.click(timeout=10000)
                    await page.get_by_text('Continue', exact=True).first.click(timeout=10000)

                try:
                    await self._wait_dashboard_ready(page, timeout=20000)
                    last_login_error = None
                    break
                except Exception as exc:
                    last_login_error = exc
                    if login_attempt < 3:
                        logger.warning('planner_v2 bootstrap login attempt %s/3 did not reach dashboard', login_attempt)
                        await page.goto(login.login_url, wait_until='commit', timeout=60000)
                        await self._wait_login_page_ready(page, timeout_ms=30000)
            if last_login_error is not None:
                raise AssertionError(f'planner_v2 bootstrap login did not reach dashboard: {last_login_error}') from last_login_error

            await self._emit(step_callback, {'type': 'log', 'content': '[planner_v2] Bootstrap login complete.\n'})

    async def _teardown_pyuitest_session(self, page, step_callback):
        current_url = str(page.url or '').strip()
        if not current_url or '/login' in current_url:
            return

        sign_out_candidates = [
            'text=Sign Out',
            'text=Logout',
            'text=Log out',
            'button:has-text("Sign Out")',
            'button:has-text("Logout")',
            '[role="menuitem"]:has-text("Sign Out")',
        ]
        menu_candidates = [
            'text=Profile',
            'text=Usage',
            '[aria-label*="profile" i]',
            '[class*="avatar"]',
        ]

        try:
            visible_sign_out = await self._find_visible_locator(page, sign_out_candidates)
            if visible_sign_out is not None:
                await self._emit(step_callback, {'type': 'log', 'content': '[planner_v2] Teardown logout via visible Sign Out.\n'})
                await visible_sign_out.click(timeout=5000)
                await page.wait_for_url('**/login**', timeout=15000)
                return

            for selector in menu_candidates:
                locator = await self._resolve_locator(page, selector)
                if locator is None:
                    continue
                if await locator.count() <= 0:
                    continue
                await locator.click(timeout=5000)
                await page.wait_for_timeout(1000)
                for sign_out_selector in sign_out_candidates:
                    sign_out_locator = await self._resolve_locator(page, sign_out_selector)
                    if sign_out_locator is None:
                        continue
                    if await sign_out_locator.count() <= 0:
                        continue
                    await self._emit(step_callback, {'type': 'log', 'content': '[planner_v2] Teardown logout after opening account menu.\n'})
                    await sign_out_locator.click(timeout=5000)
                    await page.wait_for_url('**/login**', timeout=15000)
                    return
        except Exception as exc:
            logger.warning('planner_v2 teardown logout skipped: %s', exc)

    async def _find_visible_locator(self, page, selectors):
        for selector in selectors:
            locator = await self._resolve_locator(page, selector)
            if locator is None:
                continue
            try:
                if await locator.count() <= 0:
                    continue
                if await locator.first.is_visible():
                    return locator.first
            except Exception:
                continue
        return None

    async def _wait_login_page_ready(self, page, timeout_ms=20000):
        selector_groups = {
            'email': 'input[id="login_email"], input[type="email"], input[name*="email" i], input[placeholder*="email" i]',
            'password': 'input[id="login_password"], input[type="password"], input[name*="password" i], input[placeholder*="password" i]',
            'submit': 'button[type="submit"], button:has-text("Sign in"), button:has-text("Login"), button:has-text("Log in")',
        }

        deadline = time.monotonic() + max(timeout_ms, 1000) / 1000
        last_counts = {'email': 0, 'password': 0, 'submit': 0}
        last_body_preview = ''

        while time.monotonic() < deadline:
            for name, selector in selector_groups.items():
                try:
                    last_counts[name] = await page.locator(selector).count()
                except Exception:
                    last_counts[name] = 0

            if all(last_counts.values()):
                return True

            if '/dashboard/' in str(page.url or ''):
                return False

            try:
                last_body_preview = await page.evaluate(
                    '() => (document.body ? document.body.innerText : "").slice(0, 240)'
                )
            except Exception:
                last_body_preview = ''

            await page.wait_for_timeout(1000)

        logger.warning(
            'planner_v2 login form not ready: counts=%s url=%s body=%r',
            last_counts,
            page.url,
            last_body_preview,
        )
        return False

    async def _wait_dashboard_ready(self, page, timeout=60000):
        await page.wait_for_url('**/dashboard/**', wait_until='commit', timeout=timeout)
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            logger.warning('planner_v2 wait_for_load_state(networkidle) timeout, continue with current page state')

    async def _capture_bootstrap_debug(self, page, step_callback, label):
        try:
            body_preview = await page.evaluate('() => (document.body ? document.body.innerText : "").slice(0, 500)')
        except Exception:
            body_preview = ''

        await self._emit(
            step_callback,
            {
                'type': 'log',
                'content': f'[planner_v2] Bootstrap debug {label}: url={page.url} body={body_preview}\n',
            },
        )

    async def _capture_screenshot(self, page, artifact_dir, filename):
        if artifact_dir is None:
            return None

        try:
            target_path = artifact_dir / filename
            await page.screenshot(path=str(target_path), full_page=True)

            from django.conf import settings

            return str(target_path.relative_to(Path(settings.MEDIA_ROOT))).replace('\\', '/')
        except Exception as exc:
            logger.warning('planner_v2 failed to capture screenshot %s: %s', filename, exc)
            return None

    def _safe_name(self, value):
        normalized = ''.join(char if char.isalnum() or char in {'_', '-'} else '_' for char in str(value or 'planner_v2'))
        return normalized.strip('_') or 'planner_v2'

    async def _emit(self, callback, payload):
        if callback is None:
            return
        if asyncio.iscoroutinefunction(callback):
            await callback(payload)
            return
        callback(payload)

    async def _check_stop(self, should_stop):
        if asyncio.iscoroutinefunction(should_stop):
            return await should_stop()
        return bool(should_stop())
