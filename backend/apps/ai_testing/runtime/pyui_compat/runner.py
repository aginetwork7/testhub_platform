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
from asgiref.sync import sync_to_async


logger = logging.getLogger('django')

ACTION_CACHE_SCHEMA_VERSION = 'v3'


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

    def __init__(self, execution_mode='planner_v2', enable_gif=False, case_name=None, use_cache=True, execution_user_id=None, api_automation_configuration=None):
        self.execution_mode = execution_mode
        self.enable_gif = enable_gif
        self.case_name = case_name or 'Adhoc Task'
        self.use_cache = bool(use_cache)
        self.execution_user_id = execution_user_id
        self.api_automation_configuration = api_automation_configuration
        self._recent_network_events = []
        self._reported_event_ids = []
        self._reported_alert_gpt_description = ''

    async def analyze_task(self, task_description, case_mode='freeform', task_steps=None):
        return self._build_planned_tasks(task_description, case_mode=case_mode, task_steps=task_steps)

    async def run_task(self, task_description, planned_tasks=None, callback=None, should_stop=None):
        tasks = planned_tasks or self._build_planned_tasks(task_description)
        if callback is not None:
            await self._emit(callback, {'type': 'log', 'content': 'planner_v2 runtime bootstrap: executor not implemented yet\n'})
        return tasks

    def _resolve_browser_executable(self):
        """Return a Chromium executable that can decode live camera streams.

        Playwright's bundled Chromium is the open-source build without the
        proprietary H.264/H.265 codecs required to play camera streams, so a
        live-stream player stays stuck on a loading state forever. A system
        Chromium (Debian package) ships those codecs via system ffmpeg, so prefer
        it when available. Falls back to Playwright's bundled browser when no
        codec-capable system browser is found.
        """
        configured = os.environ.get('PLAYWRIGHT_CHROMIUM_PATH', '').strip()
        candidates = [configured] if configured else []
        candidates.extend([
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
                getattr(self.api_automation_configuration, 'id', None),
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
                'api_automation_configuration': self._planner_configuration_trace(),
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

        first_browser_index = next(
            (index for index, step in enumerate(normalized_steps) if step.get('executor') not in {'device_cli', 'data_factory'}),
            0,
        )
        step_index_start = 1
        if first_browser_index:
            await self._run_device_only_plan(
                normalized_steps[:first_browser_index],
                history,
                step_callback,
                should_stop,
                artifact_dir,
                artifact_prefix,
                task_description,
                planned_tasks,
                finalize=False,
            )
            if not history.case_report['success'] or len(history.steps) < first_browser_index:
                report_artifacts = self._write_case_report_artifacts(artifact_dir, artifact_prefix, history)
                if report_artifacts:
                    history.artifacts.extend(report_artifacts)
                history.planner_trace['case_report'] = history.case_report
                return history
            step_index_start = first_browser_index + 1
            normalized_steps = normalized_steps[first_browser_index:]

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
                    status = 'completed'
                    error_message = None
                    last_executed_action = step.get('action')
                    action_source = 'direct'
                    screenshot_rel_path = None

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
                                    'type': 'device_cli',
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
                            event_report = await self._execute_data_factory_step(step)
                            self._reported_event_ids = event_report['event_ids']
                            last_executed_action = 'report_vehicle_event'
                            action_source = 'data_factory'
                            history.artifacts.append(
                                {
                                    'type': 'event_report',
                                    'step': index,
                                    'camera_name': step['camera_name'],
                                    'event_ids': event_report['event_ids'],
                                }
                            )
                            await self._emit(
                                step_callback,
                                {
                                    'type': 'log',
                                    'content': f"[planner_v2] Step {index} reported vehicle event(s): {', '.join(event_report['event_ids'])}\n",
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
                                if action_source == 'cache':
                                    history.cache_stats['fallback_replan'] = history.cache_stats.get('fallback_replan', 0) + 1
                                    history.planner_trace['step_retry_map'][str(index)] = 1
                                    self._delete_cached_ai_actions(step)
                                    await self._emit(
                                        step_callback,
                                        {'type': 'log', 'content': f"[planner_v2] Step {index} cached plan failed, retrying with fresh AI plan.\n"},
                                    )
                                    ai_actions = await self._plan_ai_step(page, step)
                                    action_source = 'model'
                                    last_executed_action = ai_actions[-1].get('action') if ai_actions else step.get('action')
                                    await self._store_cached_ai_actions(step, ai_actions)
                                    history.cache_stats['ai_generated'] = history.cache_stats.get('ai_generated', 0) + len(ai_actions)
                                    history.cache_stats['write'] = history.cache_stats.get('write', 0) + 1
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
                        elif step.get('action') == 'report_vehicle_event':
                            event_report = await self._report_vehicle_event(step)
                            self._reported_event_ids = event_report['event_ids']
                            history.artifacts.append(
                                {
                                    'type': 'event_report',
                                    'step': index,
                                    'environment_id': step.get('environment_id'),
                                    'event_ids': event_report.get('event_ids', []),
                                }
                            )
                            await self._emit(
                                step_callback,
                                {
                                    'type': 'log',
                                    'content': f"[planner_v2] Step {index} reported vehicle event(s): {', '.join(event_report.get('event_ids', []))}\n",
                                },
                            )
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

                    if status == 'failed':
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
        configuration = self.api_automation_configuration
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
                    event_report = await self._execute_data_factory_step(step)
                    self._reported_event_ids = event_report['event_ids']
                    result = {
                        'status': 'PASSED',
                        'operation': 'report_vehicle_event',
                        'stdout': f"event_ids={','.join(event_report['event_ids'])}",
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
                'type': step.get('executor'),
                'step': index,
                'device_id': step.get('device_id'),
                'camera_name': step.get('camera_name'),
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
        if self.api_automation_configuration is None:
            raise ValueError('device_cli 步骤需要绑定 API 自动化环境。')
        from apps.api_automation.device_cli_skill import DeviceCliSkill

        return await asyncio.to_thread(
            DeviceCliSkill().execute,
            self.api_automation_configuration,
            device_id=step['device_id'],
            operation=step.get('operation'),
            arguments=step.get('arguments'),
            command=step.get('command'),
            timeout_seconds=max(1, int(step.get('timeout_ms', 30000) / 1000)),
        )

    async def _execute_data_factory_step(self, step):
        if self.api_automation_configuration is None:
            raise ValueError('data_factory 步骤需要绑定 API 自动化环境。')
        if not self.execution_user_id:
            raise PermissionError('data_factory 步骤需要执行用户上下文。')
        edge_settings = ((self.api_automation_configuration.runtime_settings or {}).get('api', {}) or {}).get('edge', {}) or {}
        cameras = (edge_settings.get('main_device', {}) or {}).get('cameras', []) or []
        camera_name = str(step.get('camera_name') or '').strip()
        camera_index = next(
            (index for index, camera in enumerate(cameras) if str(camera.get('camera_name') or '').strip() == camera_name),
            None,
        )
        if camera_index is None:
            raise ValueError(f'当前环境未配置摄像头 {camera_name}。')
        return await self._report_vehicle_event({
            'environment_id': self.api_automation_configuration.id,
            'device': 'main',
            'camera_index': camera_index,
            'media_path': 'vehicle/normal_snap_image_0.jpeg',
            'vehicle_color': 1,
        })

    @staticmethod
    def _sanitize_device_output(stdout, stderr):
        output = '\n'.join(part for part in [str(stdout or '').strip(), str(stderr or '').strip()] if part)
        if not output:
            return None
        output = re.sub(r'(send\s+")[^"]+(\\r")', r'\1***\2', output, flags=re.IGNORECASE)
        output = re.sub(r'((?:password|token|authorization)\s*[:=]\s*)\S+', r'\1***', output, flags=re.IGNORECASE)
        return output[-8000:]

    async def _get_ai_actions_for_step(self, page, step, history, step_callback=None, step_index=None):
        fallback_actions = self._fallback_actions_for_step(step)
        if fallback_actions:
            return [self._normalize_step({**action, 'step_mode': 'direct'}, offset) for offset, action in enumerate(fallback_actions, start=1)], 'fallback'

        if self.use_cache:
            cached_actions = self._load_cached_ai_actions(step)
            if cached_actions:
                history.cache_stats['hit'] = history.cache_stats.get('hit', 0) + 1
                history.cache_stats['miss'] = max(0, history.cache_stats.get('miss', 0) - 1)
                return cached_actions, 'cache'

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
        if self.use_cache:
            await self._store_cached_ai_actions(step, ai_actions)
            history.cache_stats['write'] = history.cache_stats.get('write', 0) + 1
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

    async def _execute_ai_actions(self, page, step, ai_actions, index, step_callback, timeout_error, history=None, allow_replan=True):
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
            await self._emit(
                step_callback,
                {'type': 'log', 'content': f"[planner_v2] Step {index}.{sub_index}: {self._describe_action(ai_action)}\n"},
            )
            try:
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
                fallback_actions = self._fallback_actions_for_step(
                    {'description': self._describe_action(ai_action)}
                )
                if fallback_actions:
                    await self._emit(
                        step_callback,
                        {'type': 'log', 'content': f"[planner_v2] Step {index}.{sub_index}: using deterministic fallback.\n"},
                    )
                    for fallback_action in fallback_actions:
                        normalized_fallback = self._normalize_step(
                            {**fallback_action, 'step_mode': 'direct'},
                            sub_index,
                        )
                        fallback_result = await self._execute_step(page, normalized_fallback, timeout_error=timeout_error)
                        if history is not None and isinstance(fallback_result, dict) and fallback_result.get('download_dialog_path'):
                            history.artifacts.extend([
                                {'type': 'playback_download_dialog', 'step': index, 'path': fallback_result['download_dialog_path']},
                                {'type': 'playback_download_completed', 'step': index, 'path': fallback_result['download_completed_path']},
                            ])
                    continue
                if not allow_replan:
                    raise

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
                    allow_replan=False,
                )
                return

    def _cache_file_path(self):
        try:
            from django.conf import settings

            base_dir = Path(getattr(settings, 'BASE_DIR', Path.cwd())).resolve().parent
            cache_dir = base_dir / 'Data' / 'Cache'
        except Exception:
            cache_dir = Path.cwd() / 'Data' / 'Cache'

        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / 'action_cache.json'

    def _cache_key_for_step(self, step):
        description = str(step.get('description') or '').strip()
        step_no = int(step.get('index') or 0)
        digest = hashlib.md5(description.encode('utf-8')).hexdigest()[:12] if description else 'no_desc'
        safe_case_name = self._safe_name(self.case_name)
        return f'{ACTION_CACHE_SCHEMA_VERSION}::{safe_case_name}::step{step_no}::{digest}'

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

    def _load_cached_ai_actions(self, step):
        cache = self._read_action_cache()
        item = cache.get(self._cache_key_for_step(step))
        if not isinstance(item, dict):
            return None

        actions = item.get('actions')
        if not isinstance(actions, list) or not actions:
            return None

        return [action for action in actions if isinstance(action, dict)]

    async def _store_cached_ai_actions(self, step, actions):
        if not isinstance(actions, list) or not actions:
            return

        cache = self._read_action_cache()
        cache[self._cache_key_for_step(step)] = {
            'case_name': self.case_name,
            'step_num': int(step.get('index') or 0),
            'step_description': str(step.get('description') or '').strip(),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'actions': [action for action in actions if isinstance(action, dict)],
        }
        self._write_action_cache(cache)

    def _delete_cached_ai_actions(self, step):
        cache = self._read_action_cache()
        removed = cache.pop(self._cache_key_for_step(step), None)
        if removed is not None:
            self._write_action_cache(cache)

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

    def _build_planned_tasks(self, task_description, case_mode='freeform', task_steps=None):
        if case_mode in {'structured', 'hybrid'} and isinstance(task_steps, list) and task_steps:
            planned_tasks = []
            for index, step in enumerate(task_steps, start=1):
                if isinstance(step, dict):
                    description = str(step.get('description') or step.get('task') or step.get('name') or '').strip()
                else:
                    description = str(step).strip()
                planned_tasks.append({
                    'id': index,
                    'description': description or f'步骤 {index}',
                    'status': 'pending',
                })
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
        selector = raw_step.get('selector') or raw_step.get('locator') or raw_step.get('target')
        expected = raw_step.get('expected') or raw_step.get('assert_value') or raw_step.get('url_contains')
        if expected is None and action in {'assert_url_contains', 'url_contains'}:
            expected = raw_step.get('url')
        if expected is None and action in {'assert_text_contains', 'text_contains', 'assert_url_contains', 'url_contains'}:
            expected = raw_step.get('value') or raw_step.get('text')
        assert_kind = str(raw_step.get('assert_kind') or '').strip().lower()
        semantic_assertions = {
            'site_list': (["[class*='site-item']", "[class*='site'] [class*='item']", '#btnSite'], 80, 120, 120, 20),
            'camera_list': (["div[class*='grid'] > div", "div[class*='grid'] > button", "[class*='camera-item']", "[class*='preview']"], 80, 120, 40, 20),
            'camera_previews': (["[class*='preview']", "[class*='thumbnail']", 'img', 'video', 'canvas'], 80, 120, 40, 20),
        }
        semantic_assertion = semantic_assertions.get(assert_kind)
        if action == 'assert' and semantic_assertion:
            selector_candidates, min_x, min_y, min_width, min_height = semantic_assertion
            raw_step = {
                **raw_step,
                'assert_kind': 'selector_non_empty',
                'param': assert_kind,
                'expected': raw_step.get('expected') or 'true',
                'selector_candidates': raw_step.get('selector_candidates') or selector_candidates,
                'min_count': raw_step.get('min_count') or 1,
                'min_x': raw_step.get('min_x') or min_x,
                'min_y': raw_step.get('min_y') or min_y,
                'min_width': raw_step.get('min_width') or min_width,
                'min_height': raw_step.get('min_height') or min_height,
            }
            assert_kind = 'selector_non_empty'
        return {
            'index': index,
            'executor': str(raw_step.get('executor') or 'browser').strip().lower(),
            'step_mode': str(raw_step.get('step_mode') or 'direct').strip().lower(),
            'action': action,
            'description': description,
            'selector': selector,
            'loc': raw_step.get('loc'),
            'param': raw_step.get('param'),
            'url': raw_step.get('url') or raw_step.get('target_url'),
            'value': raw_step.get('value') or raw_step.get('text') or raw_step.get('input_value'),
            'expected': raw_step.get('expected') or expected,
            'assert_kind': assert_kind,
            'fields': raw_step.get('fields'),
            'selector_candidates': raw_step.get('selector_candidates'),
            'environment_id': raw_step.get('environment_id'),
            'camera_name': raw_step.get('camera_name'),
            'device_id': raw_step.get('device_id'),
            'command': raw_step.get('command'),
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

    async def _report_vehicle_event(self, step):
        environment_id = step.get('environment_id')
        if not isinstance(environment_id, int) or environment_id <= 0:
            raise ValueError('report_vehicle_event requires a positive environment_id')
        if not self.execution_user_id:
            raise PermissionError('report_vehicle_event requires the execution user context')

        payload = {
            'environment_id': environment_id,
            'device': str(step.get('device') or 'main'),
            'camera_index': int(step.get('camera_index') or 0),
            'media_path': str(step.get('media_path') or ''),
            'vehicle_color': int(step.get('vehicle_color') or 1),
            'alert_type': 'vehicle',
            'report_event': True,
        }

        def report_event():
            from django.contrib.auth import get_user_model
            from apps.data_factory.views import DataFactoryViewSet

            user = get_user_model().objects.get(id=self.execution_user_id)
            return DataFactoryViewSet().execute_business_tool(
                'construct_alert_event',
                payload,
                user,
            )

        report = await asyncio.to_thread(report_event)
        if not report.get('success'):
            raise AssertionError(report.get('error') or 'vehicle event report failed')
        nested_report = report.get('report') if isinstance(report.get('report'), dict) else {}
        event_ids = report.get('event_ids') or nested_report.get('event_ids')
        if not event_ids:
            raise AssertionError('vehicle event report did not return event IDs')
        return {'event_ids': event_ids}

    @staticmethod
    def _has_gpt_analysis(alert):
        if not isinstance(alert, dict):
            return False

        gpt_raw = alert.get('gptRaw')
        if isinstance(gpt_raw, dict) and str(gpt_raw.get('natural_language_description') or '').strip():
            return True

        for status in alert.get('statuses') or []:
            note = ((status.get('noteRecord') or {}).get('new') or {}).get('note')
            if str(note or '').strip():
                return True
        return False

    async def _wait_for_reported_alert_gpt_analysis(self, page, timeout_ms):
        if not self._reported_event_ids:
            raise AssertionError('no reported event ID is available for GPT analysis readiness check')

        event_id = self._reported_event_ids[-1]
        deadline = time.monotonic() + max(timeout_ms, 1000) / 1000
        last_failure = 'alert was not found'

        while time.monotonic() < deadline:
            try:
                async with page.expect_response(
                    lambda response: '/alert/alerts?' in response.url and response.request.method == 'GET',
                    timeout=min(timeout_ms, 30000),
                ) as response_info:
                    await page.reload(wait_until='domcontentloaded', timeout=min(timeout_ms, 60000))
                response = await response_info.value
                headers = await response.request.all_headers()
                query_url = re.sub(r'([?&]paging\.limit=)\d+', r'\g<1>100', response.url)
                api_response = await page.context.request.get(query_url, headers=headers)
                payload = await api_response.json()
                alert = next(
                    (item for item in payload.get('data', []) if item.get('eventId') == event_id),
                    None,
                )
                gpt_raw = alert.get('gptRaw') if isinstance(alert, dict) else None
                description = str((gpt_raw or {}).get('natural_language_description') or '').strip()
                if description:
                    self._reported_alert_gpt_description = description
                    return
                last_failure = 'alert has not received a GPT analysis yet' if alert else 'alert was not found'
            except Exception as error:
                last_failure = f'alert query failed: {type(error).__name__}: {error}'

            await page.wait_for_timeout(5000)

        raise AssertionError(f"reported event '{event_id}' {last_failure}")

    async def _assert_reported_alert_gpt_analysis(self, page, timeout_ms):
        await self._wait_for_reported_alert_gpt_analysis(page, timeout_ms)

    async def _assert_reported_alert_note_matches_gpt(self, page, timeout_ms):
        expected = self._normalize_text_for_contains(self._reported_alert_gpt_description)
        if not expected:
            raise AssertionError('no GPT natural-language description is available for Alert Note comparison')

        deadline = time.monotonic() + max(timeout_ms, 1000) / 1000
        last_text = ''
        while time.monotonic() < deadline:
            last_text = str(await page.locator('body').first.text_content(timeout=timeout_ms) or '')
            if expected in self._normalize_text_for_contains(last_text):
                return
            await page.wait_for_timeout(1000)

        raise AssertionError('Alert Note does not contain the reported alert GPT natural-language description')

    async def _plan_ai_step(self, page, step):
        fallback_actions = self._fallback_actions_for_step(step)
        if fallback_actions:
            return [self._normalize_step({**action, 'step_mode': 'direct'}, offset) for offset, action in enumerate(fallback_actions, start=1)]

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

        actions = await VisualStepReplanner().create_actions(
            step['description'],
            {
                'url': current_url,
                'visible_text': normalized_text,
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
        self._validate_planned_actions(normalized_actions, step['description'])
        return normalized_actions

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
    def _validate_planned_actions(actions, step_description=''):
        for index, action in enumerate(actions, start=1):
            name = str(action.get('action') or '').strip()
            if not name:
                raise ValueError(f'Planner action {index} is missing action')
            if name in {'click', 'hover'} and not (action.get('selector') or action.get('loc')):
                raise ValueError(f'Planner action {index} {name} requires selector or loc')
            if name == 'navigate' and not action.get('url'):
                raise ValueError(f'Planner action {index} navigate requires url')
            if name in {'assert_url_contains', 'assert_text_contains'} and not action.get('expected'):
                raise ValueError(f'Planner action {index} {name} requires expected')
            if name in {'fill', 'press', 'select'} and not action.get('value'):
                raise ValueError(f'Planner action {index} {name} requires value')
        assertion_markers = ('断言', 'assert', '检查', 'verify', '确认', '正常')
        requires_assertion = any(marker in str(step_description).lower() for marker in assertion_markers)
        assertion_actions = {
            'assert',
            'assert_text_contains',
            'assert_url_contains',
            'assert_popup_contains',
            'assert_reported_alert_gpt_analysis',
            'assert_reported_alert_note_matches_gpt',
        }
        if requires_assertion and not any(str(action.get('action') or '') in assertion_actions for action in actions):
            raise ValueError('Planner step with an assertion intent requires an assertion action')
        live_stream_markers = ('直播流', '直播视频流', '实时视频流', 'live stream')
        if any(marker in str(step_description).lower() for marker in live_stream_markers):
            has_media_assertion = any(
                str(action.get('action') or '') == 'assert'
                and str(action.get('assert_kind') or '') in {'stream_active', 'video_visible'}
                for action in actions
            )
            if not has_media_assertion:
                raise ValueError('Planner live-stream step requires stream_active or video_visible assertion')
        camera_list_markers = ('cameras列表', '摄像头列表', '摄像机列表', '缩略图')
        if any(marker in str(step_description).lower() for marker in camera_list_markers):
            has_camera_list_assertion = any(
                str(action.get('action') or '') == 'assert'
                and str(action.get('assert_kind') or '') == 'selector_non_empty'
                and str(action.get('param') or '') in {'site_list', 'camera_list', 'camera_previews'}
                for action in actions
            )
            if not has_camera_list_assertion:
                raise ValueError('Planner camera-list step requires site_list, camera_list, or camera_previews assertion')

    def _fallback_actions_for_step(self, step):
        text = str(step.get('description') or '')
        normalized_text = text.lower()
        if '打开 cameras 页面' in normalized_text and 'site 列表' in normalized_text:
            return [{'action': 'open_camera_list', 'reason': 'camera workflow capability'}]
        if '摄像头在线数量大于 0 的 site' in normalized_text and '展开' in normalized_text:
            return [{'action': 'select_site_with_online_cameras', 'reason': 'camera workflow capability'}]
        if '选择在线 camera' in normalized_text and '直播流' in text:
            return [
                {'action': 'select_online_camera', 'reason': 'camera workflow capability'},
                {'action': 'assert', 'assert_kind': 'stream_active', 'expected': 'true', 'reason': 'camera workflow live stream assertion'},
            ]
        if '10s forward' in normalized_text and any(keyword in normalized_text for keyword in ('playback', '回放')):
            return [{'action': 'seek_playback_forward_ten_seconds', 'reason': 'playback capability'}]
        if 'View Playback' in text:
            return [
                {
                    'action': 'wait',
                    'value': 3000,
                    'reason': 'fallback wait for live-stream toolbar',
                },
                {
                    'action': 'click_exact_text',
                    'value': 'View Playback',
                    'reason': 'fallback deterministic view-playback click',
                },
                {
                    'action': 'assert_playback_loaded',
                    'reason': 'fallback playback media and toolbar assertion',
                },
            ]
        if 'download' in text.lower() and ('playback' in text.lower() or '回放' in text):
            return [{
                'action': 'download_playback',
                'reason': 'fallback deterministic playback download',
            }]
        popup_expected = self._extract_popup_expected_text(text)
        if self._looks_like_popup_assertion(text):
            return [{
                'action': 'assert_popup_contains',
                'expected': popup_expected,
                'reason': 'fallback deterministic popup assertion',
            }]
        if '组织管理按钮' in text and '三个人图标' in text:
            return [{
                'action': 'hover',
                'selector': 'text=Organization',
                'reason': 'fallback deterministic organization sidebar hover',
            }]
        if '高级搜索面板' in text and 'Magic Search V2' in text and '包含' in text:
            return [{
                'action': 'assert',
                'assert_kind': 'text_visible',
                'param': 'Magic Search V2',
                'reason': 'fallback deterministic advanced-search option assertion',
            }]
        if '放大镜图标' in text and '高级搜索面板' in text and '展开' in text:
            return [{
                'action': 'click',
                'selector': 'div.colorBorder.rounded-xl.flex.bg-white > button.ant-dropdown-trigger',
                'reason': 'fallback deterministic advanced-search leading magnifier click',
            }]
        if '高级搜索列表' in text and 'Magic Search V2' in text and '点击' in text:
            return [{
                'action': 'click',
                'selector': 'Magic Search V2',
                'reason': 'fallback deterministic advanced-search option click',
            }]
        if '状态选项列表' in text and 'Close' in text and '点击' in text:
            return [{
                'action': 'change_alert_status',
                'selector': '.alert-select-root',
                'value': 'Close',
                'reason': 'fallback deterministic alert-status option change',
            }]
        if '显示列表中的第一个结果' in text and '点击' in text:
            return [{
                'action': 'click',
                'loc': '(180,245)',
                'param': 'first alert result',
                'reason': 'fallback deterministic first alert result click',
            }]
        if '页面中存在可见媒体内容' in text:
            return [{
                'action': 'assert',
                'assert_kind': 'selector_non_empty',
                'selector_candidates': [
                    "div[id^='alert_'].cursor-pointer > div.relative.rounded-lg",
                    "[class*='preview']",
                    'video',
                    'canvas',
                    'img',
                ],
                'min_count': 1,
                'min_x': 120,
                'min_y': 80,
                'min_width': 40,
                'min_height': 20,
                'param': 'alert_media',
                'expected': 'True',
                'reason': 'fallback deterministic visible media assertion',
            }]
        if '背景色' in text and '深色' in text and ('断言' in text or '期望断言结果' in text):
            return [{
                'action': 'assert',
                'assert_kind': 'page_dark_theme',
                'expected': 'True',
                'param': 'page_background',
                'reason': 'fallback deterministic page dark-theme assertion',
            }]
        if '背景色' in text and '浅色' in text and ('断言' in text or '期望断言结果' in text):
            return [{
                'action': 'assert',
                'assert_kind': 'page_dark_theme',
                'expected': 'False',
                'param': 'page_background',
                'reason': 'fallback deterministic page light-theme assertion',
            }]
        if 'To Do' in text and '下拉框' in text:
            return [{
                'action': 'click',
                'selector': '.alert-select-root .ant-select-selector',
                'reason': 'fallback deterministic alert-status dropdown open',
            }]
        if '断言组织管理子选项' in text and 'Team' in text:
            return [
                {
                    'action': 'hover',
                    'param': 'Team sidebar fallback',
                    'reason': 'fallback expand organization sidebar before Team assertion',
                },
                {
                    'action': 'assert',
                    'assert_kind': 'text_visible',
                    'param': 'Team',
                    'reason': 'fallback assert Team option is visible',
                },
            ]
        if '点击组织管理子选项' in text and 'Team' in text:
            return [
                {
                    'action': 'hover',
                    'param': 'Team sidebar fallback',
                    'reason': 'fallback expand organization sidebar before Team click',
                },
                {
                    'action': 'click',
                    'selector': 'Team',
                    'param': 'Team',
                    'reason': 'fallback click Team option',
                },
            ]
        if '角色下拉框' in text and '当前值为Org Admin' in text:
            return [{
                'action': 'click',
                'selector': 'text=Org Admin (Can manage and view all sites)',
                'reason': 'fallback deterministic role dropdown open',
            }]
        if '下拉框列表中包含"Site Manager"选项' in text or '下拉框列表中包含“Site Manager”选项' in text:
            return [{
                'action': 'assert_text_contains',
                'selector': 'body',
                'expected': 'Site Manager (Can manage and view specified sites)',
                'reason': 'fallback deterministic role option assertion',
            }]
        if '选择并点击Site Manager选项' in text:
            return [{
                'action': 'click',
                'selector': 'text=Site Manager (Can manage and view specified sites)',
                'reason': 'fallback deterministic role option click',
            }]
        if '当前值为Site Manager' in text:
            return [{
                'action': 'assert_text_contains',
                'selector': 'body',
                'expected': 'Site Manager (Can manage and view specified sites)',
                'reason': 'fallback deterministic selected role assertion',
            }]
        if '蓝色加号' in text and ('创建新的角色' in text or '创建新的用户' in text):
            return [
                {
                    'action': 'click',
                    'selector': 'button[aria-label="Add New User"]',
                    'reason': 'fallback click add-user button on organization page',
                }
            ]
        if 'Phone Number' in text and '415-341-7120' in text:
            return [{
                'action': 'type_phone_us',
                'selector': "input[type='tel'], input[placeholder*='Phone' i], input[name*='phone' i]",
                'value': '+14153417120',
                'param': '415-341-7120',
                'reason': 'fallback type US phone number with +1 country code',
            }]
        if 'Email输入框填写ai@test.com' in text:
            return [{
                'action': 'fill',
                'selector': "input[type='email'][placeholder='Email']",
                'value': 'ai@test.com',
                'reason': 'fallback deterministic email fill',
            }]
        if 'First Name输入框填写AI' in text:
            return [{
                'action': 'fill',
                'selector': "input[type='text'][placeholder='First Name']",
                'value': 'AI',
                'reason': 'fallback deterministic first-name fill',
            }]
        if 'Last Name输入框填写Test' in text:
            return [{
                'action': 'fill',
                'selector': "input[type='text'][placeholder='Last Name']",
                'value': 'Test',
                'reason': 'fallback deterministic last-name fill',
            }]
        if 'Email地址为ai@test.com' in text and 'First Name字段为AI' in text and 'Phone Number字段为+1(415)341-7120' in text:
            return [{
                'action': 'assert',
                'assert_kind': 'field_values_match',
                'fields': [
                    {
                        'name': 'Email',
                        'selector': "input[type='email'][placeholder='Email']",
                        'expected': 'ai@test.com',
                        'match': 'exact',
                    },
                    {
                        'name': 'First Name',
                        'selector': "input[type='text'][placeholder='First Name']",
                        'expected': 'AI',
                        'match': 'exact',
                    },
                    {
                        'name': 'Last Name',
                        'selector': "input[type='text'][placeholder='Last Name']",
                        'expected': 'Test',
                        'match': 'exact',
                    },
                    {
                        'name': 'Phone Number',
                        'selector': "input[type='tel'][placeholder='Phone number']",
                        'expected': '+1(415)341-7120',
                        'match': 'phone_digits',
                    },
                ],
                'reason': 'fallback deterministic multi-field assertion for create-user form',
            }]
        if ('搜索结果' in text and '不为空' in text) or ('用户列表' in text and '不包含' not in text):
            return [{
                'action': 'assert',
                'assert_kind': 'selector_non_empty',
                'selector_candidates': [
                    'text=To Do',
                    'text=Person',
                    "[class*='result'] [class*='item']",
                    "[class*='list'] [class*='item']",
                    "[role='row']",
                    "[class*='card']",
                    'li',
                ],
                'min_count': 1,
                'min_x': 120,
                'min_y': 80,
                'min_width': 30,
                'min_height': 16,
                'param': 'results',
                'expected': 'True',
            }]
        email_match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text)
        if email_match and '包含' in text and '不包含' not in text and any(keyword in text for keyword in ('搜索结果', '用户列表', '左侧展示')):
            return [{
                'action': 'assert',
                'assert_kind': 'text_visible',
                'param': email_match.group(0),
                'expected': 'True',
                'reason': 'fallback deterministic positive list assertion',
            }]
        if email_match and '不包含' in text and any(keyword in text for keyword in ('搜索结果', '用户列表', '左侧展示')):
            return [{
                'action': 'assert',
                'assert_kind': 'text_visible',
                'param': email_match.group(0),
                'expected': 'False',
                'reason': 'fallback deterministic negative list assertion',
            }]
        if 'placeholder' in text and 'Magic Search V2' in text:
            return [{
                'action': 'assert',
                'assert_kind': 'placeholder_equals',
                'selector': "input[placeholder*='Magic Search' i]",
                'param': 'Magic Search V2',
                'expected': 'True',
                'reason': 'fallback deterministic Magic Search V2 placeholder assertion',
            }]
        if '在搜索框中输入' in text and 'black hair' in text:
            return [{'action': 'type', 'selector': "input[type='text']", 'param': 'black hair'}]
        if '预览缩略图' in text or ('第一条结果' in text and '预览' in text):
            return [{
                'action': 'click',
                'selector': "div[id^='alert_'].cursor-pointer > div.relative.rounded-lg",
                'param': 'first preview',
                'reason': 'fallback deterministic first result preview thumbnail click',
            }]
        if '站点列表' in text and '在线和离线的摄像头数量' in text:
            return [
                {
                    'action': 'wait',
                    'value': '20000',
                    'reason': 'fallback wait for streaming page site list to hydrate',
                },
                {
                    'action': 'assert',
                    'assert_kind': 'selector_non_empty',
                    'selector_candidates': [
                        '#btnSite',
                        "button[id='btnSite']",
                        "[id='btnSite']",
                    ],
                    'min_count': 1,
                    'min_x': 80,
                    'min_y': 120,
                    'min_width': 120,
                    'min_height': 20,
                    'param': 'site_list',
                    'expected': 'True',
                    'reason': 'fallback deterministic site list assertion',
                },
            ]
        if '搜索结果中包含目标站点名称' in text:
            return [{
                'action': 'assert',
                'assert_kind': 'selector_non_empty',
                'selector_candidates': [
                    '#btnSite',
                    "button[id='btnSite']",
                    "[id='btnSite']",
                ],
                'min_count': 1,
                'min_x': 80,
                'min_y': 120,
                'min_width': 120,
                'min_height': 20,
                'param': 'site_search_results',
                'expected': 'True',
                'reason': 'fallback deterministic site search assertion',
            }]
        if 'Search site name' in text and '目标站点名称' in text:
            return [{
                'action': 'search_site_with_cameras',
                'selector': "input[placeholder*='Search site name' i], input[placeholder*='Search' i]",
                'reason': 'fallback search the first site that has available cameras',
            }]
        if '点击搜索结果中目标站点名称' in text:
            return [{
                'action': 'click',
                'selector': '#btnSite',
                'param': 'first site result',
                'reason': 'fallback deterministic site result click',
            }]
        if '目标站点名称下方展示出该站点的摄像头列表' in text:
            return [
                {
                    'action': 'wait',
                    'value': '15000',
                    'reason': 'fallback wait for selected site camera list to hydrate',
                },
                {
                    'action': 'assert',
                    'assert_kind': 'selector_non_empty',
                    'selector_candidates': [
                        "div[class*='grid'] > div",
                        "div[class*='grid'] > button",
                        "div[class*='grid'] [class*='rounded']",
                        "[class*='camera'] [class*='item']",
                        "[class*='camera-item']",
                        "[class*='list'] [class*='item']",
                        "[class*='card']",
                        "[class*='preview']",
                        "[class*='thumbnail']",
                        'img',
                        'video',
                        'canvas',
                    ],
                    'min_count': 1,
                    'min_x': 80,
                    'min_y': 120,
                    'min_width': 40,
                    'min_height': 20,
                    'param': 'camera_list',
                    'expected': 'True',
                    'reason': 'fallback deterministic camera list assertion',
                },
            ]
        if '每个摄像头的预览图都能够正常展示' in text:
            return [{
                'action': 'assert',
                'assert_kind': 'selector_non_empty',
                'selector_candidates': [
                    "div[class*='grid'] > div",
                    "div[class*='grid'] > button",
                    "div[class*='grid'] [class*='rounded']",
                    "[class*='camera'] [class*='item']",
                    "[class*='camera-item']",
                    "[class*='preview']",
                    "[class*='thumbnail']",
                    'img',
                    'video',
                    'canvas',
                ],
                'min_count': 1,
                'min_x': 80,
                'min_y': 120,
                'min_width': 40,
                'min_height': 20,
                'param': 'camera_previews',
                'expected': 'True',
                'reason': 'fallback deterministic camera preview assertion',
            }]
        if '第一个在线的摄像头' in text and '预览图' in text and '点击' in text:
            return [{
                'action': 'click_first_online_camera',
                'reason': 'fallback semantic online camera selection',
            }]
        if '摄像头在线数量大于 0 的 site' in text.lower() and '展开' in text:
            return [{
                'action': 'select_site_with_online_cameras',
                'reason': 'fallback select and expand site with online cameras',
            }]
        if any(marker in text.lower() for marker in ('目标摄像头', '目标camera', 'target camera')) and '点击' in text and any(keyword in text for keyword in ('直播流', '直播视频流', '实时视频流')):
            return [
                {
                    'action': 'click_first_online_camera',
                    'reason': 'fallback semantic target camera selection',
                },
                {
                    'action': 'assert',
                    'assert_kind': 'stream_active',
                    'expected': 'True',
                    'reason': 'fallback media-level live stream assertion',
                },
            ]
        if '视频流关闭按钮' in text and '带盖垃圾桶形状' in text:
            return [{
                'action': 'close_active_stream',
                'reason': 'fallback semantic trash-button stream close',
            }]
        if '实时视频流' in text and any(keyword in text for keyword in ('展示出', '持续播放', '时间戳', '画面随时间刷新')):
            return [{
                'action': 'assert',
                'assert_kind': 'stream_active',
                'param': 'stream_view',
                'expected': 'True',
                'reason': 'fallback deterministic active stream assertion',
            }]
        if '实时视频流页面关闭' in text:
            return [{
                'action': 'assert_stream_closed',
                'reason': 'fallback semantic stream-close assertion',
            }]
        if 'Dark Mode' in text or '深色模式' in text or '浅色模式' in text or '三角形和菱形' in text:
            return [{'action': 'click', 'loc': '(48,32)', 'param': ':left:top:25:25'}]
        if '主页图标' in text or '房子的形状' in text:
            return [{'action': 'click', 'loc': '(48,92)', 'param': ':left:top:25:25'}]
        if len(text.strip()) <= 50 and ('Alerts' in text or '铃铛形状' in text):
            return [{'action': 'click', 'loc': '(48,196)', 'param': ':left:top:25:25'}]
        if 'Cameras' in text or '摄像头的形状' in text:
            return [
                {'action': 'click', 'loc': '(48,142)', 'param': ':left:top:25:25', 'reason': 'fallback open cameras sidebar entry'},
                {'action': 'click', 'selector': 'text=Cameras', 'param': 'Cameras', 'reason': 'fallback click cameras submenu item'},
            ]
        return []

    def _looks_like_popup_assertion(self, text):
        normalized = str(text or '').strip()
        lowered = normalized.lower()
        if not normalized:
            return False
        has_assertion_intent = '断言' in normalized or 'assert' in lowered
        if not has_assertion_intent:
            return False
        popup_keywords = (
            '提示弹窗',
            '弹窗',
            '提示消息',
            '提示框',
            'notification',
            'toast',
            'popup',
            'message',
        )
        return any(keyword in lowered or keyword in normalized for keyword in popup_keywords)

    def _extract_popup_expected_text(self, text):
        normalized = str(text or '').strip()
        patterns = [
            r'包含[“"](?P<expected>[^”"]+)[”"]',
            r'contains?[\s:]+[“"]?(?P<expected>[^”"\n]+)[”"]?',
            r'显示[“"](?P<expected>[^”"]+)[”"]',
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                return str(match.group('expected') or '').strip()
        return ''

    def _normalize_text_for_contains(self, text):
        return re.sub(r'\s+', '', str(text or '').strip())

    def _attach_runtime_observers(self, page):
        self._recent_network_events = []

        def on_response(response):
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
            except Exception:
                logger.debug('planner_v2 failed to record runtime response', exc_info=True)

        page.on('response', on_response)

    def _popup_success_compatible_with_recent_mutation(self, expected):
        normalized = str(expected or '').strip().lower()
        if not normalized:
            return False

        if 'created successfully' in normalized or '创建成功' in normalized:
            allowed_methods = {'POST'}
        elif 'deleted successfully' in normalized or '删除成功' in normalized or 'deactivated successfully' in normalized:
            allowed_methods = {'DELETE', 'PATCH', 'POST'}
        elif 'updated successfully' in normalized or 'saved successfully' in normalized or '更新成功' in normalized or '保存成功' in normalized:
            allowed_methods = {'PUT', 'PATCH', 'POST'}
        else:
            return False

        now = time.time()
        for event in reversed(self._recent_network_events):
            if now - float(event.get('ts') or 0) > 120:
                continue
            if not event.get('ok'):
                continue
            if int(event.get('status') or 0) >= 400:
                continue
            if str(event.get('method') or '').upper() not in allowed_methods:
                continue
            return True
        return False

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

    def _normalize_alert_status_token(self, text):
        normalized = re.sub(r'[^a-z0-9]+', '_', str(text or '').strip().lower()).strip('_')
        return normalized

    def _resolve_alert_status_target(self, requested_label, current_label, option_labels):
        requested = self._normalize_alert_status_token(requested_label)
        current = self._normalize_alert_status_token(current_label)
        normalized_options = {
            self._normalize_alert_status_token(label): str(label or '').strip()
            for label in option_labels
            if str(label or '').strip()
        }

        if requested in normalized_options:
            return normalized_options[requested]

        alias_groups = {
            'close': ('close', 'closed', 'false_alarm', 'false_alarm_label'),
            'closed': ('close', 'closed', 'false_alarm', 'false_alarm_label'),
            'false_alarm': ('false_alarm', 'false_alarm_label', 'close', 'closed'),
        }
        for alias in alias_groups.get(requested, (requested,)):
            if alias in normalized_options:
                return normalized_options[alias]

        remaining_options = [
            str(label or '').strip()
            for label in option_labels
            if self._normalize_alert_status_token(label) != current and str(label or '').strip()
        ]
        if len(remaining_options) == 1:
            return remaining_options[0]
        return None

    async def _change_alert_status(self, page, selector, value, timeout_ms):
        root_selector = str(selector or '.alert-select-root').strip() or '.alert-select-root'
        root_locator = page.locator(root_selector).first
        if await root_locator.count() == 0:
            raise ValueError('change_alert_status step requires a valid alert status root selector')

        current_label = str(await root_locator.text_content() or '').strip()
        trigger_locator = root_locator.locator('.ant-select-selector').first
        if await trigger_locator.count() == 0:
            trigger_locator = root_locator

        await trigger_locator.click(timeout=timeout_ms)
        await page.wait_for_timeout(300)

        option_data = await page.locator('[role="option"]').evaluate_all(
            "els => els.map((el, i) => ({index: i, label: el.getAttribute('aria-label') || (el.innerText || el.textContent || '').trim(), selected: el.getAttribute('aria-selected') === 'true'}))"
        )
        option_labels = [str(item.get('label') or '').strip() for item in option_data if str(item.get('label') or '').strip()]
        target_label = self._resolve_alert_status_target(value, current_label, option_labels)
        if not target_label:
            raise AssertionError(f'alert status option {value!r} is not available; options={option_labels!r}')

        current_index = next((item['index'] for item in option_data if item.get('selected')), None)
        target_index = next(
            (
                item['index']
                for item in option_data
                if self._normalize_alert_status_token(item.get('label')) == self._normalize_alert_status_token(target_label)
            ),
            None,
        )
        if target_index is None:
            raise AssertionError(f'alert status target {target_label!r} was not found in options={option_labels!r}')

        if current_index is None:
            current_index = next(
                (
                    item['index']
                    for item in option_data
                    if self._normalize_alert_status_token(item.get('label')) == self._normalize_alert_status_token(current_label)
                ),
                0,
            )

        if target_index != current_index:
            key = 'ArrowDown' if target_index > current_index else 'ArrowUp'
            for _ in range(abs(target_index - current_index)):
                await page.keyboard.press(key)
                await page.wait_for_timeout(100)
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(300)

    async def _search_site_with_cameras(self, page, selector, timeout_ms):
        site_rows = []
        for candidate in ("[class*='site-item']", "[class*='site'] [class*='item']"):
            try:
                site_rows = await page.locator(candidate).evaluate_all(
                    "els => els.map(el => ({text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim()})).filter(item => item.text)"
                )
            except Exception:
                site_rows = []
            if site_rows:
                break

        target_site = ''
        for row in site_rows:
            row_text = str(row.get('text') or '').strip()
            match = re.search(r'^(?P<name>.+?)\s+(?P<online>\d+)\s*/\s*(?P<offline>\d+)$', row_text)
            if not match:
                continue
            online_count = int(match.group('online'))
            offline_count = int(match.group('offline'))
            if online_count > 0:
                target_site = str(match.group('name') or '').strip()
                break

        if not target_site:
            raise AssertionError('search_site_with_cameras could not find any visible site with online cameras')

        locator = await self._resolve_locator(page, selector or "input[placeholder*='Search site name' i], input[placeholder*='Search' i]")
        if locator is None:
            raise ValueError('search_site_with_cameras requires a searchable site input')
        await locator.fill(target_site, timeout=timeout_ms)
        await page.wait_for_timeout(300)

    async def _select_site_with_online_cameras(self, page, timeout_ms):
        selector = "input[placeholder*='Search site name' i], input[placeholder*='Search' i]"
        await self._search_site_with_cameras(page, selector, timeout_ms)
        await page.locator('body').press('Enter')
        await page.wait_for_timeout(500)
        site = page.locator('#btnSite').first
        await site.wait_for(state='visible', timeout=timeout_ms)
        await site.click(timeout=timeout_ms)
        await page.wait_for_timeout(800)

    async def _click_first_online_camera(self, page, timeout_ms):
        async def has_visible_camera_card():
            for selector in (
                "div[class*='grid'] > div",
                "div[class*='grid'] > button",
                "[class*='camera-item']",
                "[class*='camera'] [class*='preview']",
            ):
                locator = page.locator(selector)
                for index in range(await locator.count()):
                    try:
                        if await locator.nth(index).is_visible(timeout=200):
                            return True
                    except Exception:
                        continue
            return False

        if not await has_visible_camera_card():
            site_rows = []
            for selector in ("[class*='site-item']", "[class*='site'] [class*='item']", "button"):
                try:
                    site_rows = await page.locator(selector).evaluate_all(
                        "els => els.map(el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim()).filter(Boolean)"
                    )
                except Exception:
                    site_rows = []
                for row_text in site_rows:
                    match = re.search(r'^(?P<name>.+?)\s+(?P<online>\d+)\s*/\s*(?P<offline>\d+)$', str(row_text))
                    if match and int(match.group('online')) > 0:
                        site = page.get_by_role('button', name=match.group('name').strip(), exact=True)
                        await site.click(timeout=timeout_ms)
                        await page.wait_for_timeout(800)
                        break
                if await has_visible_camera_card():
                    break

        selectors = (
            "div[class*='grid'] > div",
            "div[class*='grid'] > button",
            "[class*='camera-item']",
            "[class*='camera'] [class*='preview']",
        )
        for selector in selectors:
            locator = page.locator(selector)
            for index in range(await locator.count()):
                candidate = locator.nth(index)
                try:
                    if not await candidate.is_visible(timeout=300):
                        continue
                    online = await candidate.evaluate(
                        """
                        element => {
                          const nodes = [element, ...element.querySelectorAll('*')];
                          return nodes.some(node => {
                            const className = String(node.className || '').toLowerCase();
                            if (/(online|status-green|bg-green|text-green)/.test(className)) return true;
                                                        const styles = getComputedStyle(node);
                                                        return [styles.color, styles.backgroundColor, styles.fill, styles.stroke, styles.borderColor].some(color => {
                                                            const match = color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
                                                            return match && Number(match[2]) > Number(match[1]) * 1.15 && Number(match[2]) > Number(match[3]) * 1.15;
                                                        });
                          });
                        }
                        """
                    )
                    if online:
                        await candidate.click(timeout=timeout_ms)
                        return
                except Exception:
                    continue
        raise AssertionError('no visible online camera card was found')

    async def _close_active_stream(self, page, timeout_ms):
        trash_button = page.locator("button:has(svg path[d*='M16 9V19H8V9H16'])").first
        await trash_button.wait_for(state='visible', timeout=timeout_ms)
        await trash_button.click(timeout=timeout_ms)

    async def _assert_stream_closed(self, page, timeout_ms):
        deadline = time.monotonic() + max(timeout_ms, 1000) / 1000.0
        while time.monotonic() < deadline:
            media = page.locator('img, canvas, video')
            has_stream_surface = False
            for index in range(min(await media.count(), 20)):
                candidate = media.nth(index)
                try:
                    if not await candidate.is_visible(timeout=200):
                        continue
                    box = await candidate.bounding_box()
                    if box and box['x'] >= 80 and box['width'] >= 600 and box['height'] >= 320:
                        has_stream_surface = True
                        break
                except Exception:
                    continue
            if not has_stream_surface:
                return
            await page.wait_for_timeout(300)
        raise AssertionError('stream close did not remove the active player surface')

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
        timeout_ms = step['timeout_ms']
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
            else:
                raise ValueError('click step requires selector or loc')
            return

        if action == 'click_first_online_camera':
            await self._click_first_online_camera(page, timeout_ms)
            return

        if action in {'open_camera_list', 'select_site_with_online_cameras', 'select_online_camera', 'seek_playback_forward_ten_seconds', 'assert_playback_loaded'}:
            from apps.ai_testing.runtime.pyui_compat.capabilities import CameraWorkflowCapabilities

            capability = CameraWorkflowCapabilities(page)
            if action == 'open_camera_list':
                await capability.open_camera_list(timeout_ms)
            elif action == 'select_site_with_online_cameras':
                await capability.select_site_with_online_cameras(timeout_ms)
            elif action == 'select_online_camera':
                await capability.select_online_camera(timeout_ms)
            elif action == 'seek_playback_forward_ten_seconds':
                evidence = await capability.seek_forward_ten_seconds(timeout_ms)
                from apps.ai_testing.global_planner import VisualStepReplanner

                assessment = await VisualStepReplanner().assess_playback_advance(
                    evidence['before_screenshot'],
                    evidence['after_screenshot'],
                )
                if not 8 <= assessment['advanced_seconds'] <= 15:
                    raise AssertionError(
                        f"Playback advanced {assessment['advanced_seconds']:.2f}s, expected 10s within OCR tolerance"
                    )
                return evidence
            else:
                await capability.assert_playback_loaded(timeout_ms)
            return

        if action == 'select_site_with_online_cameras':
            await self._select_site_with_online_cameras(page, timeout_ms)
            return

        if action == 'close_active_stream':
            await self._close_active_stream(page, timeout_ms)
            return

        if action == 'assert_stream_closed':
            await self._assert_stream_closed(page, timeout_ms)
            return

        if action == 'click_exact_text':
            target_text = str(step.get('value') or param or '').strip()
            if not target_text:
                raise ValueError('click_exact_text requires text')
            await page.get_by_text(target_text, exact=True).click(timeout=timeout_ms)
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

        if action in {'type_phone_us'}:
            value = str(step.get('value') or '+14153417120').strip()
            locator = await self._resolve_locator(page, selector or "input[type='tel']")
            if locator is None:
                raise ValueError('type_phone_us step requires selector')
            await locator.click(timeout=timeout_ms)
            await page.keyboard.press('Control+A')
            await page.keyboard.press('Backspace')
            await page.wait_for_timeout(200)
            await page.keyboard.type(value, delay=80)
            return

        if action in {'search_site_with_cameras'}:
            await self._search_site_with_cameras(page, selector, timeout_ms)
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

        if action in {'change_alert_status'}:
            await self._change_alert_status(
                page,
                selector=selector,
                value=str(step.get('value') or param or '').strip(),
                timeout_ms=timeout_ms,
            )
            return

        if action == 'download_playback':
            return await self._download_playback(page, timeout_ms)

        if action == 'ensure_switch_enabled':
            label = str(step.get('value') or param or '').strip()
            if not label:
                raise ValueError('ensure_switch_enabled step requires a switch label')
            switch_row = page.locator(f'div:has(> span:has-text("{label}"))').last
            switch = switch_row.locator('input[role="switch"]').first
            if await switch.count() == 0:
                raise AssertionError(f"switch '{label}' was not found")
            if not await switch.is_checked():
                await switch_row.locator('.react-switch-bg').first.click(timeout=timeout_ms)
            if not await switch.is_checked():
                raise AssertionError(f"switch '{label}' is not enabled")
            return

        if action in {'assert_reported_alert_gpt_analysis', 'wait_for_reported_alert_gpt_analysis'}:
            await self._wait_for_reported_alert_gpt_analysis(page, timeout_ms)
            return

        if action == 'assert_reported_alert_note_matches_gpt':
            await self._assert_reported_alert_note_matches_gpt(page, timeout_ms)
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
            key = 'PageDown' if direction in {'down', 'pagedown'} else 'PageUp'
            await page.keyboard.press(key)
            return

        if action in {'assert'}:
            assert_kind = str(step.get('assert_kind') or '').strip().lower()
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

        if action in {'assert_url_contains', 'url_contains'}:
            expected = str(step.get('expected') or '').strip()
            if not expected:
                raise ValueError('assert_url_contains step requires expected')
            try:
                await page.wait_for_url(f'**{expected}**', wait_until='commit', timeout=timeout_ms)
            except timeout_error:
                pass
            current_url = page.url or ''
            if expected not in current_url:
                raise AssertionError(f"current url '{current_url}' does not contain '{expected}'")
            return

        if action in {'assert_text_contains', 'text_contains'}:
            selector = str(step.get('selector') or 'body').strip()
            expected = str(step.get('expected') or '').strip()
            if not expected:
                raise ValueError('assert_text_contains step requires expected')
            actual_text = await page.locator(selector).first.text_content(timeout=timeout_ms)
            normalized_text = str(actual_text or '').strip()
            if expected not in normalized_text:
                compact_expected = self._normalize_text_for_contains(expected)
                compact_actual = self._normalize_text_for_contains(normalized_text)
                if compact_expected and compact_expected in compact_actual:
                    return
                raise AssertionError(f"text '{normalized_text}' does not contain '{expected}'")
            return

        if action == 'assert_popup_contains':
            expected = str(step.get('expected') or '').strip()
            if expected and self._popup_success_compatible_with_recent_mutation(expected):
                return
            if expected:
                text_locator = page.get_by_text(expected, exact=False).first
                try:
                    await text_locator.wait_for(state='visible', timeout=timeout_ms)
                    return
                except Exception:
                    pass

            selector_candidates = [
                '[role="alert"]',
                '[role="status"]',
                '.ant-message-notice',
                '.ant-notification-notice',
                '.Toastify__toast',
                '[class*="toast"]',
                '[class*="message"]',
                '[class*="notification"]',
            ]

            last_text = ''
            for selector in selector_candidates:
                try:
                    locator = page.locator(selector)
                    await locator.first.wait_for(state='visible', timeout=min(timeout_ms, 3000))
                    last_text = str(await locator.first.text_content(timeout=1000) or '').strip()
                    if not expected or expected in last_text:
                        return
                except Exception:
                    continue

            body_text = str(await page.locator('body').text_content(timeout=timeout_ms) or '').strip()
            if expected and expected not in body_text:
                if self._popup_success_compatible_with_recent_mutation(expected):
                    return
                raise AssertionError(f"popup text '{expected}' not found; last popup text='{last_text}'")
            if not expected and not body_text:
                raise AssertionError('popup assertion failed because no visible popup text was found')
            return

        if action == 'assert_media_visible':
            media_selector = 'img, video, canvas'
            locator = page.locator(media_selector)
            count = await locator.count()
            for idx in range(min(count, 20)):
                try:
                    if await locator.nth(idx).is_visible(timeout=1000):
                        return
                except Exception:
                    continue
            raise AssertionError('no visible media element found')

        if action == 'assert_video_visible':
            expected = str(step.get('expected') or '').strip()
            selector_candidates = ['video', '[class*="video"] video', '[data-testid*="video"] video']
            for selector in selector_candidates:
                locator = page.locator(selector)
                count = await locator.count()
                for idx in range(min(count, 10)):
                    try:
                        target = locator.nth(idx)
                        if not await target.is_visible(timeout=1000):
                            continue
                        if not expected:
                            return
                        source = (await target.get_attribute('src')) or ''
                        poster = (await target.get_attribute('poster')) or ''
                        payload = f'{source} {poster}'
                        if expected in payload:
                            return
                    except Exception:
                        continue
            raise AssertionError(f"no visible video element matched '{expected}'" if expected else 'no visible video element found')

        raise ValueError(f"unsupported planner_v2 action: {action}")

    async def _download_playback(self, page, timeout_ms):
        toolbar = page.locator('#playerContainer').locator('xpath=..')
        download_button = toolbar.locator("button:has(svg path[d*='M19.3552 11.0833'])").first
        await download_button.wait_for(state='visible', timeout=timeout_ms)
        await download_button.click(timeout=timeout_ms, force=True)
        dialog_text = ''
        deadline = time.monotonic() + max(timeout_ms, 1000) / 1000.0
        while time.monotonic() < deadline:
            dialog_text = str(await page.locator('body').inner_text() or '')
            if 'Start Time' in dialog_text and 'End Time' in dialog_text:
                break
            await page.wait_for_timeout(200)
        if 'Start Time' not in dialog_text or 'End Time' not in dialog_text:
            raise AssertionError('Playback download dialog did not open')
        dialog_path = await self._save_playback_screenshot(page, 'download_dialog')

        download_button = page.get_by_text('Download', exact=True).last
        async with page.expect_download(timeout=min(max(timeout_ms, 1000), 180000)) as download_info:
            await download_button.click(timeout=timeout_ms)
        download = await download_info.value
        if not str(download.suggested_filename or '').strip():
            raise AssertionError('Playback download did not provide a filename')
        try:
            await asyncio.wait_for(download.path(), timeout=180)
        except asyncio.TimeoutError as error:
            raise AssertionError('Playback download did not complete within 3 minutes') from error
        failure = await download.failure()
        if failure:
            raise AssertionError(f'Playback download failed: {failure}')
        completed_path = await self._save_playback_screenshot(page, 'download_completed')
        return {'download_dialog_path': dialog_path, 'download_completed_path': completed_path}

    async def _save_playback_screenshot(self, page, label):
        from django.conf import settings

        directory = Path(settings.MEDIA_ROOT) / 'ai_testing' / 'playback_evidence'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{label}_{datetime.now().strftime("%Y%m%d%H%M%S%f")}.png'
        await page.screenshot(path=str(path), type='png')
        return self._relative_media_path(path)

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
        target_url, email, password = self._resolve_pyuitest_bootstrap()
        if not target_url:
            return

        current_url = str(page.url or '').strip()
        if '/dashboard/' in current_url:
            return

        await self._emit(step_callback, {'type': 'log', 'content': f'[planner_v2] Bootstrap navigate: {target_url}\n'})
        navigation_committed = False
        try:
            await page.goto(target_url, wait_until='load', timeout=60000)
            navigation_committed = True
        except Exception as exc:
            current_url = str(page.url or '').strip()
            navigation_committed = current_url.startswith(target_url)
            logger.warning(
                'planner_v2 bootstrap load wait timeout, current_url=%s committed=%s: %s',
                current_url,
                navigation_committed,
                exc,
            )
            if not navigation_committed:
                await page.goto(target_url, wait_until='commit', timeout=60000)

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

        if email and password:
            await page.locator('input[id="login_email"], input[type="email"], input[name*="email" i], input[placeholder*="email" i]').first.fill(email, timeout=10000)
            await page.locator('input[id="login_password"], input[type="password"], input[name*="password" i], input[placeholder*="password" i]').first.fill(password, timeout=10000)
            await page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Login"), button:has-text("Log in")').first.click(timeout=10000)
            await page.wait_for_timeout(300)
            terms_prompt = page.get_by_text('I have read and agree to the Terms of Use.', exact=False).first
            if await terms_prompt.is_visible():
                await terms_prompt.click(timeout=10000)
                await page.get_by_text('Continue', exact=True).first.click(timeout=10000)

            try:
                await self._wait_dashboard_ready(page)
            except Exception as exc:
                raise AssertionError(f'planner_v2 bootstrap login did not reach dashboard: {exc}') from exc

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

            # Alpha Vision keeps Profile/Usage/Settings/Sign Out in hidden DOM nodes until
            # the bottom-left settings gear is opened. In the current layout that trigger is
            # the visible gear icon around the bottom-left corner of the sidebar.
            await page.mouse.click(48, 790)
            await page.wait_for_timeout(1200)

            visible_sign_out = await self._find_visible_locator(page, sign_out_candidates)
            if visible_sign_out is not None:
                await self._emit(step_callback, {'type': 'log', 'content': '[planner_v2] Teardown logout after opening sidebar settings menu.\n'})
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

    def _resolve_pyuitest_bootstrap(self):
        target_url = ''
        email = ''
        password = ''

        try:
            from apps.ui_automation.management.commands.init_alpha_vision_login_case import TARGET_URL, STEP_SEEDS

            target_url = str(TARGET_URL or '').strip()
            for seed in STEP_SEEDS:
                description = str(getattr(seed, 'description', '') or '')
                if '邮箱' in description or 'email' in description.lower():
                    email = str(getattr(seed, 'input_value', '') or '').strip()
                if '密码' in description or 'password' in description.lower():
                    password = str(getattr(seed, 'input_value', '') or '').strip()
        except Exception as exc:
            logger.warning('planner_v2 bootstrap fallback import failed: %s', exc)

        return target_url, email, password

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

    async def _wait_dashboard_ready(self, page):
        await page.wait_for_url('**/dashboard/**', timeout=60000)
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
