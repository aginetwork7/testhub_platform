import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from asgiref.sync import sync_to_async
from django.db import DatabaseError, models, transaction
from django.utils import timezone

from apps.ai_testing.execution.intent_text import (
    continuing_collection_locator,
    display_value_from_target,
    exact_text_locator,
    expects_true,
    popup_intent_mismatch,
)
from apps.ai_testing.execution.environment_resources import default_device_camera_names, environment_device_resources, is_text_input, refers_to_target_device
from apps.ai_testing.execution.model_errors import is_transient_llm_error


logger = logging.getLogger('django')

ACTION_CACHE_SCHEMA_VERSION = 'v6'
ACTION_CACHE_TTL_DAYS = 30
ACTION_CACHE_VARIANTS_PER_STEP = 8
PAGE_SKELETON_JS = """() => {
    // Structural signature of the rendered page: tags, roles, stable anchors and state attributes of visible
    // elements, with repeated siblings collapsed. Text, counts and list lengths do not participate, so the same
    // page state keeps one fingerprint while a data refresh, an opened dialog or an expanded panel is still told apart.
    const MAX_NODES = 6000;
    const MAX_DEPTH = 14;
    const STATE_ATTRS = ['aria-expanded', 'aria-selected', 'aria-checked', 'aria-pressed', 'aria-disabled', 'aria-modal', 'data-state', 'disabled', 'open'];
    const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'LINK', 'META']);
    let visited = 0;
    const identity = (element) => {
        const tag = element.tagName.toLowerCase();
        let key = tag;
        const role = element.getAttribute('role');
        if (role) key += `[role=${role}]`;
        if (element.id && !/\\d{3,}/.test(element.id)) key += `#${element.id}`;
        const testId = element.getAttribute('data-testid');
        if (testId) key += `[testid=${testId.slice(0, 40)}]`;
        const label = element.getAttribute('aria-label');
        if (label) key += `[label=${label.slice(0, 40)}]`;
        if (tag === 'input') key += `[type=${element.getAttribute('type') || 'text'}]`;
        for (const attr of STATE_ATTRS) {
            const value = element.getAttribute(attr);
            if (value !== null) key += `[${attr}=${String(value).slice(0, 20)}]`;
        }
        return key;
    };
    const visible = (element) => {
        if (typeof element.checkVisibility === 'function') return element.checkVisibility();
        return element.getClientRects().length > 0;
    };
    const walk = (element, depth) => {
        if (depth > MAX_DEPTH) return '';
        const parts = [];
        const seen = new Map();
        for (const child of element.children) {
            if (visited++ > MAX_NODES) break;
            if (SKIP.has(child.tagName)) continue;
            const tag = child.tagName.toLowerCase();
            if (tag === 'svg') {
                if (!seen.has('svg')) { seen.set('svg', parts.length); parts.push('svg'); }
                continue;
            }
            if (!visible(child)) continue;
            const key = identity(child);
            if (seen.has(key)) {
                const index = seen.get(key);
                if (!parts[index].endsWith('*')) parts[index] += '*';
                continue;
            }
            seen.set(key, parts.length);
            const inner = walk(child, depth + 1);
            parts.push(inner ? `${key}(${inner})` : key);
        }
        return parts.join(',');
    };
    return `body(${walk(document.body, 0)})`;
}"""
EXPERIENCE_AUTO_VERIFY_SUCCESSES = 2

# Provider spikes (429/5xx) commonly last a few minutes: ten exponential retries capped at 45s wait about
# five minutes in total, still inside the default 600s step budget which is checked on every retry.
TRANSIENT_MODEL_RETRIES = 20
TRANSIENT_MODEL_BACKOFF_CAP_SECONDS = 45.0
ICON_TOOLTIP_PROBE_LIMIT = 20
IMAGE_RENDER_WAIT_MS = 45000
STREAM_START_WAIT_MS = 20000
CARD_APPEAR_WAIT_MS = 10000
RENDER_WAIT_BUDGET_PER_STEP_MS = 120000
# An intent that names a discrete control rather than a region. Binders that pick "the biggest thing that
# appeared" must not answer for these: a container satisfies them without the control existing at all.
NAMED_CONTROL_INTENT_PATTERN = re.compile(
    r'\b(button|btn|icon|checkbox|radio|toggle|switch|link|tab|menu item|menuitem)\b',
    re.IGNORECASE,
)

PLANNER_CONTROL_KEYS = ('selector', 'group_selector', 'url', 'name', 'tag', 'role', 'rect', 'group_size', 'group_ordinal', 'has_visual_content', 'top_layer', 'blocking_layer', 'blocking_layer_id', 'dialog_layer', 'z_index', 'container_text')
ICON_TOOLTIP_HOVER_MS = 350
# Returns the tooltip an element is described by (aria-describedby) plus every short top-layer text, so a
# hover can be attributed to the button that produced it even when the tooltip is a body-level portal.
TOOLTIP_PROBE_JS = """(selector) => {
    const texts = [];
    const push = (value) => {
        const text = String(value || '').replace(/\\s+/g, ' ').trim();
        if (text && text.length <= 80 && !texts.includes(text)) texts.push(text);
    };
    for (const element of document.querySelectorAll('[role="tooltip"]')) push(element.innerText);
    for (const element of document.body.children) {
        if (element.id === 'root' || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(element.tagName)) continue;
        push(element.innerText);
    }
    let described = '';
    if (selector) {
        let element = null;
        try { element = document.querySelector(selector); } catch (error) { element = null; }
        const describedBy = element ? (element.getAttribute('aria-describedby') || '') : '';
        for (const id of describedBy.split(/\\s+/).filter(Boolean)) {
            const target = document.getElementById(id);
            const text = target ? String(target.innerText || '').replace(/\\s+/g, ' ').trim() : '';
            if (text) { described = text.slice(0, 80); break; }
        }
    }
    return { described, texts };
}"""
MEDIA_INTENT_PATTERN = re.compile(
    r'\b(video|stream|streaming|player|playback|canvas|image|img|thumbnail|preview|picture|photo|snapshot|media|feed|frame|footage|live view|camera view)\b',
    re.IGNORECASE,
)
RENDERED_VISUAL_ELEMENTS_JS = """
() => {
    const structuralSelector = (target) => {
        const uniqueAnchor = (node) => {
            if (node.id && document.querySelectorAll(`#${CSS.escape(node.id)}`).length === 1) return `#${CSS.escape(node.id)}`;
            const testId = node.getAttribute('data-testid');
            if (testId && document.querySelectorAll(`[data-testid=${JSON.stringify(testId)}]`).length === 1) return `[data-testid=${JSON.stringify(testId)}]`;
            if (node.parentElement === document.body) {
                const classes = typeof node.className === 'string' ? node.className.split(/\\s+/).filter(Boolean) : [];
                if (classes.length) {
                    const candidate = `body > ${node.tagName.toLowerCase()}${classes.map(token => `.${CSS.escape(token)}`).join('')}`;
                    if (document.querySelectorAll(candidate).length === 1) return candidate;
                }
            }
            return '';
        };
        const parts = [];
        let current = target;
        while (current && current !== document.body) {
            const anchor = uniqueAnchor(current);
            if (anchor) {
                const anchored = parts.length ? `${anchor} > ${parts.join(' > ')}` : anchor;
                if (document.querySelectorAll(anchored).length === 1) return anchored;
            }
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
    const rendered = (element) => {
        if (element instanceof HTMLImageElement) return element.naturalWidth > 1 && element.naturalHeight > 1;
        if (element instanceof HTMLCanvasElement) return element.width > 1 && element.height > 1;
        if (element instanceof HTMLVideoElement) return element.readyState >= 2 && element.videoWidth > 1;
        return false;
    };
    const isTopLayer = (element) => {
        if (element.closest('[role="dialog"], dialog, [aria-modal="true"]')) return true;
        for (let current = element; current && current !== document.body; current = current.parentElement) {
            const style = getComputedStyle(current);
            if (['fixed', 'sticky'].includes(style.position) || (Number.parseInt(style.zIndex, 10) || 0) > 0) return true;
        }
        return false;
    };
    return Array.from(document.querySelectorAll('img, canvas, video')).filter(element => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 1 && rect.height > 1 && style.visibility !== 'hidden' && style.display !== 'none' && rendered(element);
    }).map(element => {
        const rect = element.getBoundingClientRect();
        // What picture this surface is showing. A filtered list reuses its containers, so the structural
        // selector of a thumbnail survives the swap while the image behind it is a different one entirely.
        const source = (element.currentSrc || element.getAttribute('src') || '').slice(-180);
        const intrinsic = element instanceof HTMLImageElement
            ? `${element.naturalWidth}x${element.naturalHeight}`
            : element instanceof HTMLVideoElement
                ? `${element.videoWidth}x${element.videoHeight}`
                : `${element.width}x${element.height}`;
        return { selector: structuralSelector(element), tag: element.tagName.toLowerCase(), area: Math.round(rect.width * rect.height), viewport_ratio: (rect.width * rect.height) / Math.max(1, window.innerWidth * window.innerHeight), top_layer: isTopLayer(element), content_key: `${source}|${intrinsic}`, rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) } };
    }).filter(item => item.selector).slice(0, 300);
}
"""

VISUAL_CONTENT_SETTLED_JS = """
(locators) => {
    const visible = (element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const rendered = (element) => {
        if (element instanceof HTMLImageElement) return element.naturalWidth > 1 && element.naturalHeight > 1;
        if (element instanceof HTMLCanvasElement) return element.width > 1 && element.height > 1;
        if (element instanceof HTMLVideoElement) return element.readyState >= 2 && element.videoWidth > 1;
        return getComputedStyle(element).backgroundImage !== 'none';
    };
    const pending = (element) => {
        if (element instanceof HTMLImageElement) return !element.complete && !(element.naturalWidth > 1);
        if (element instanceof HTMLVideoElement) return element.readyState < 2 && !element.error && Boolean(element.currentSrc || element.src || element.srcObject);
        return false;
    };
    if (locators.length) {
        return locators.every((locator) => {
            let element = null;
            try { element = document.querySelector(locator); } catch (error) { return true; }
            if (!element) return false;
            return [element, ...element.querySelectorAll('img, canvas, video, [style]')].some(rendered);
        });
    }
    return !Array.from(document.querySelectorAll('img, video')).filter(visible).some(pending);
}
"""


class _PointClickTarget:
    """Minimal locator stand-in that clicks a page coordinate recovered from observed geometry."""

    def __init__(self, page, x: float, y: float):
        self._page, self.x, self.y = page, x, y

    async def click(self, timeout=None, **kwargs):
        await self._page.mouse.click(self.x, self.y)


class EnvironmentBootstrapError(RuntimeError):
    """The target application could not be reached or logged into before any step ran (an environment outage)."""


class PlannerRetryExhaustedError(ValueError):
    """Raised when every model-generated action violates the planner contract."""


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

    def __init__(self, execution_mode='planner_v2', enable_gif=False, case_name=None, use_cache=True, execution_user_id=None, environment_configuration=None, ai_project_id=None, execution_record_id=None, ai_case_id=None, force_replan=False):
        self.execution_mode = execution_mode
        self.force_replan = bool(force_replan)
        self.enable_gif = enable_gif
        self.case_name = case_name or 'Adhoc Task'
        self.use_cache = bool(use_cache)
        self.execution_user_id = execution_user_id
        self.environment_configuration = environment_configuration
        self.ai_project_id = ai_project_id
        self.execution_record_id = execution_record_id
        self.ai_case_id = ai_case_id
        self._cache_context_by_step = {}
        self._cache_key_by_step = {}
        self._recent_network_events = []
        self._recent_download_events = []
        self._download_event_baseline = 0
        self._execution_resources = []
        self._last_actionable_controls = []
        self._rendered_visual_baseline = None
        self._rendered_visual_baseline_elements = None
        self._tooltip_name_cache = {}
        self._pre_action_url = ''
        self._pre_action_control_names = set()
        self._pre_action_blocking_layer = False
        self._last_click_box = None
        self._plan_context_fingerprint = ''
        self._step_deadline = None
        self._pre_action_visual_frames = None
        self._observed_canvas_baseline = None
        self._render_wait_spent_ms = {}
        self._runtime_events = []
        self._observable_baseline = None
        self._observable_baseline_texts = set()
        self._exhausted_binding_states = set()
        self._binding_verified_predecessors = []
        self._swallowed_action_retries = set()
        self._last_action_effect_note = ''
        self._last_accessibility_snapshot = {'snapshot_id': '', 'page_version': '', 'nodes': []}
        self._mcp_client = None
        self._active_planning_step = None

    async def analyze_task(self, task_description, case_mode='freeform', task_steps=None):
        return self._build_planned_tasks(task_description, case_mode=case_mode, task_steps=task_steps)

    async def run_task(self, task_description, planned_tasks=None, callback=None, should_stop=None):
        tasks = planned_tasks or self._build_planned_tasks(task_description)
        if callback is not None:
            await self._emit(callback, {'type': 'log', 'content': 'planner_v2 runtime bootstrap: executor not implemented yet\n'})
        return tasks

    @staticmethod
    def _freeform_planning_goal(task_description: str, task_steps: object) -> str:
        if not isinstance(task_steps, list):
            return task_description
        descriptions = [
            str(step.get('description') or '').strip()[:500]
            for step in task_steps[:20]
            if isinstance(step, dict) and str(step.get('description') or '').strip()
        ]
        if not descriptions:
            return task_description
        requirements = '\n'.join(f'{index}. {description}' for index, description in enumerate(descriptions, start=1))
        return (
            f'{task_description}\n\n'
            'Stored case step requirements contain explicit values that must be preserved while producing a new canonical plan. '
            'Treat them as requirement context only; do not reuse legacy selectors or action payloads:\n'
            f'{requirements}'
        )

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
        plan_source = 'persisted'
        self._seed_environment_resources()
        if case_mode == 'freeform':
            from apps.ai_testing.global_planner import GlobalTestPlanner

            planner = GlobalTestPlanner()
            execution_steps = await planner.create_plan(
                self._freeform_planning_goal(task_description, task_steps),
                getattr(self.environment_configuration, 'id', None),
                # force_replan bypasses only the plan cache; step action reuse stays governed by use_cache.
                use_cache=self.use_cache and not self.force_replan,
            )
            self._plan_context_fingerprint = str(getattr(planner, 'last_context_fingerprint', '') or '')
            plan_source = str(getattr(planner, 'last_plan_source', '') or 'model')
            resolved_case_mode = 'hybrid'

        planned_tasks = self._build_planned_tasks(task_description, case_mode=resolved_case_mode, task_steps=execution_steps)
        if self._plan_context_fingerprint:
            # Lets the persistence layer tag the initial plan with the context it was generated under.
            await self._emit(step_callback, {'type': 'plan_context', 'fingerprint': self._plan_context_fingerprint})
        if analysis_callback is not None:
            await self._emit(analysis_callback, planned_tasks)

        history = PyUICompatHistory(
            planner_trace={
                'case_mode': resolved_case_mode,
                'task_count': len(planned_tasks),
                'source': 'global_planner' if case_mode == 'freeform' else ('planner_v2_bootstrap' if case_mode != 'hybrid' else 'planner_v2_hybrid'),
                'plan_source': plan_source,
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
                'stale_skip': 0,
                'write_skipped': 0,
                'plan_source': plan_source,
                # A plan reused from the proven-plan table is as much a cache hit as one reused from a
                # previous execution record; counting only the latter understated the hit rate.
                'plan_cache_hit': 1 if plan_source in {'cache', 'verified'} else 0,
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
            mcp_step_context = {'step': None}

            try:
                await self._bootstrap_pyuitest_session(page, step_callback)
                from apps.ai_testing.execution.mcp_tools import (
                    BrowserMCPToolAdapter,
                    MCPInProcessClient,
                    MCPInProcessTransport,
                    MCPJsonRpcDispatcher,
                )

                async def observe_current_step():
                    current_step = self._active_planning_step or mcp_step_context['step']
                    if not isinstance(current_step, dict):
                        raise ValueError('No active browser step for MCP observation.')
                    return await self._collect_planner_observation(page, current_step)

                browser_tools = BrowserMCPToolAdapter(
                    lambda: (mcp_step_context['step'] or {}).get('allowed_capabilities') or [],
                    action_handler=lambda instruction: self._execute_step(
                        page,
                        instruction,
                        timeout_error=PlaywrightTimeout,
                    ),
                    observation_handler=observe_current_step,
                )
                dispatcher = MCPJsonRpcDispatcher(browser_tools)
                self._mcp_client = MCPInProcessClient(MCPInProcessTransport(dispatcher))

                for index, step in enumerate(normalized_steps, start=step_index_start):
                    if should_stop is not None and await self._check_stop(should_stop):
                        await self._emit(
                            step_callback,
                            {'type': 'log', 'content': 'planner_v2 收到停止信号，结束后续步骤执行。\n'},
                        )
                        break

                    mcp_step_context['step'] = step
                    history.planner_trace['step_retry_map'][str(index)] = 0
                    await self._emit(step_callback, {'task_id': index, 'status': 'in_progress'})
                    await self._emit(
                        step_callback,
                        {'type': 'log', 'content': f"[planner_v2] Step {index}: {step['description']}\n"},
                    )

                    started_at = time.perf_counter()
                    self._step_deadline = time.monotonic() + self._step_time_budget_seconds()
                    self._pre_action_visual_frames = None
                    self._download_event_baseline = len(self._recent_download_events)
                    media_state_before = await self._capture_media_state(page)
                    from apps.ai_testing.execution.browser_observers import capture_canvas_frames, capture_visual_frames
                    visual_frames_before = await capture_visual_frames(page, step.get('assertions') or [])
                    canvas_frames_before = await capture_canvas_frames(page, step.get('assertions') or [])
                    self._observed_canvas_baseline = None
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
                                    await self._invalidate_reused_actions(step, action_source)
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

                    await self._wait_for_assertion_observation(page, step)
                    if status == 'completed' and step.get('step_mode') == 'ai':
                        await self._bind_required_assertions_after_action(
                            page, step, index, ai_actions, step_callback, history,
                        )
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
                        self._pre_action_visual_frames or visual_frames_before,
                        canvas_frames_before,
                    )
                    assertion_statuses = persisted_attempt.get('assertion_statuses', []) if persisted_attempt else []
                    required_statuses = self._required_assertion_statuses(step, assertion_statuses)
                    assertions_verified = self._step_assertions_are_verified(step, required_statuses)
                    action_completed = status == 'completed'
                    status = self._status_after_assertions(status, required_statuses)
                    if status != 'completed' and not error_message:
                        error_message = f'Required assertions were not verified: {", ".join(required_statuses)}.'
                    if self._should_retry_assertions(
                        step, action_completed, assertions_verified, action_source, required_statuses,
                    ):
                        if action_source in {'cache', 'experience'}:
                            history.cache_stats['fallback_replan'] = history.cache_stats.get('fallback_replan', 0) + 1
                            await self._invalidate_reused_actions(step, action_source)
                            action_source = 'model'
                            await self._emit(
                                step_callback,
                                {'type': 'log', 'content': f"[planner_v2] Step {index} reused plan evidence failed, retrying with fresh AI plan.\n"},
                            )
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
                        if await self._store_cached_ai_actions(step, ai_actions):
                            history.cache_stats['write'] = history.cache_stats.get('write', 0) + 1
                        else:
                            history.cache_stats['write_skipped'] = history.cache_stats.get('write_skipped', 0) + 1
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
                            'assertions': step.get('assertions') or [],
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
                self._mcp_client = None
                mcp_step_context['step'] = None
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
        self._cache_key_by_step[self._step_context_key(step)] = self._cache_key_for_step(step, page_context)

        if self.use_cache:
            cached_actions = await self._load_cached_ai_actions(step, page_context)
            if cached_actions:
                reason = await self._reused_actions_applicable(page, cached_actions)
                if reason:
                    # The page shape matched but the cached target is gone or covered: the entry is stale.
                    history.cache_stats['stale_skip'] = history.cache_stats.get('stale_skip', 0) + 1
                    logger.info('planner_v2 step %s cached actions skipped: %s', step_index, reason)
                    await self._delete_cached_ai_actions(step, page_context)
                else:
                    history.cache_stats['hit'] = history.cache_stats.get('hit', 0) + 1
                    history.cache_stats['miss'] = max(0, history.cache_stats.get('miss', 0) - 1)
                    return cached_actions, 'cache'

            # Experience reuse is part of the same opt-in; --no-cache means a fully fresh run.
            experience_actions = await self._load_verified_experience(step, page_context)
            if experience_actions:
                reason = await self._reused_actions_applicable(page, experience_actions)
                if reason:
                    history.cache_stats['stale_skip'] = history.cache_stats.get('stale_skip', 0) + 1
                    logger.info('planner_v2 step %s experience actions skipped: %s', step_index, reason)
                else:
                    history.cache_stats['experience_hit'] = history.cache_stats.get('experience_hit', 0) + 1
                    return experience_actions, 'experience'

        planning_step = {
            **step,
            '_verified_predecessors': self._verified_predecessor_context(history),
        }
        ai_actions = await self._plan_ai_step_for_cacheable_step(page, planning_step, history, step_callback=step_callback, step_index=step_index)
        return ai_actions, 'model'

    @staticmethod
    def _verified_predecessor_context(history):
        return [
            {
                'step_num': completed_step.get('step_num'),
                'description': completed_step.get('step_description'),
                'action': completed_step.get('action'),
                'executor': completed_step.get('executor'),
                'assertions': completed_step.get('assertions') or [],
            }
            for completed_step in getattr(history, 'steps', [])
            if completed_step.get('result') is True
        ]

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

    @staticmethod
    def _is_transient_llm_error(error) -> bool:
        """Provider overload, rate limiting and transport failures are retried; plan rejections are not."""
        return is_transient_llm_error(error)

    async def _plan_ai_step_with_retries(self, page, step, history, step_callback=None, step_index=None, max_attempts=4, max_transient_retries=TRANSIENT_MODEL_RETRIES):
        last_error = None
        attempt = 0
        transient_retries = 0
        while attempt < max_attempts:
            attempt += 1
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
                planned_actions = await self._plan_ai_step(page, planning_step)
                return planned_actions
            except Exception as exc:
                if self._is_transient_llm_error(exc):
                    transient_retries += 1
                    history.cache_stats['model_transient_retries'] = history.cache_stats.get('model_transient_retries', 0) + 1
                    history.artifacts.append({
                        'type': 'planner_attempt',
                        'step': step_index,
                        'attempt': attempt,
                        'status': 'transient_error',
                        'error': f'{type(exc).__name__}: {str(exc)[:300]}',
                    })
                    if transient_retries > max_transient_retries or self._step_budget_exhausted():
                        raise PlannerRetryExhaustedError(
                            f'Planner model unavailable after {transient_retries} transient errors: {str(exc)[:300]}'
                        ) from exc
                    delay = min(TRANSIENT_MODEL_BACKOFF_CAP_SECONDS, 2.0 ** transient_retries)
                    await self._emit(
                        step_callback,
                        {'type': 'log', 'content': f"[planner_v2] Step {step_index} planner model temporarily unavailable; retrying in {delay:.0f}s.\n"},
                    )
                    await asyncio.sleep(delay)
                    # Waiting out a provider outage is not test time: push the step deadline by the wait so the
                    # budget still bounds the page work while the model recovers.
                    if self._step_deadline is not None:
                        self._step_deadline += delay
                    attempt -= 1  # provider hiccups do not consume plan-quality attempts
                    continue
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
                if self._step_budget_exhausted():
                    logger.info('planner_v2 step %s time budget exhausted during planning', step_index)
                    break
                await asyncio.sleep(min(1.0, 0.2 * attempt))

        raise PlannerRetryExhaustedError(
            f'Hybrid AI step planner failed after {max_attempts} attempts: {last_error}'
        )

    async def _execute_ai_actions(self, page, step, ai_actions, index, step_callback, timeout_error, history=None, remaining_replans=2):
        from apps.ai_testing.execution.mcp_tools import (
            BrowserMCPToolAdapter,
            MCPInProcessClient,
            MCPInProcessTransport,
            MCPJsonRpcDispatcher,
        )

        await self._apply_assertion_bindings(index, step, ai_actions)
        self._rendered_visual_baseline = await self._capture_rendered_visual_baseline(page, step)
        self._observable_baseline = await self._capture_observable_baseline(page, step)
        self._pre_action_url = str(getattr(page, 'url', '') or '')
        # Controls seen while planning this action, keyed by position and text. A committed value display must
        # differ from them. Position, not selector, identifies a node: a menu option and the control that later
        # shows the chosen value can share one attribute selector while occupying different places.
        self._pre_action_control_names = set()
        self._pre_action_blocking_layer = False
        for control in self._last_actionable_controls:
            if not isinstance(control, dict):
                continue
            if control.get('blocking_layer') is True:
                self._pre_action_blocking_layer = True
            rect = control.get('rect') if isinstance(control.get('rect'), dict) else None
            if rect:
                text = ' '.join(str(control.get('name') or '').split())
                self._pre_action_control_names.add((PyUICompatAgent._rect_key(rect), text))
        if any(isinstance(a, dict) and a.get('assert_kind') == 'playback' for a in step.get('assertions') or []):
            from apps.ai_testing.execution.browser_observers import capture_visual_frames

            # Planning can take tens of seconds; measure playback from the moment the action starts.
            self._pre_action_visual_frames = await capture_visual_frames(page, step.get('assertions') or [])
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
        allowed_capabilities = step.get('allowed_capabilities') or []
        mcp_client = self._mcp_client
        if mcp_client is None:
            browser_tools = BrowserMCPToolAdapter(
                allowed_capabilities,
                lambda instruction: self._execute_step(page, instruction, timeout_error=timeout_error),
            )
            mcp_client = MCPInProcessClient(MCPInProcessTransport(MCPJsonRpcDispatcher(browser_tools)))
        for sub_index, ai_action in enumerate(ai_actions, start=1):
            if self.execution_record_id is not None:
                if not isinstance(allowed_capabilities, list) or not allowed_capabilities:
                    raise ValueError('Persisted browser step is missing allowed_capabilities.')
            await self._emit(
                step_callback,
                {'type': 'log', 'content': f"[planner_v2] Step {index}.{sub_index}: {self._describe_action(ai_action)}\n"},
            )
            try:
                if ai_action.get('action') == 'assert' and not ai_action.get('assert_kind'):
                    action_result = None
                else:
                    tool_result = await mcp_client.call_tool(
                        'browser.act',
                        {'instruction': ai_action},
                    )
                    action_result = tool_result['structuredContent']
                self._drain_runtime_events(history, index)
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
                self._drain_runtime_events(history, index)
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

    def _drain_runtime_events(self, history, step_index):
        """Move runtime decisions (e.g. fill repairs) recorded during actions into the audited artifacts."""
        if not self._runtime_events:
            return
        events, self._runtime_events = self._runtime_events, []
        if history is None:
            return
        history.artifacts.extend({**event, 'step': step_index} for event in events)

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

    def _browser_runtime_setting(self, key, default, minimum, maximum):
        settings = getattr(self.environment_configuration, 'runtime_settings', {}) or {}
        browser = settings.get('ai_testing_browser', {}) if isinstance(settings, dict) else {}
        try:
            return max(minimum, min(maximum, int(browser.get(key, default))))
        except (TypeError, ValueError):
            return default

    def _action_cache_ttl(self):
        return timedelta(days=self._browser_runtime_setting('action_cache_ttl_days', ACTION_CACHE_TTL_DAYS, 1, 365))

    def _action_cache_variant_limit(self):
        return self._browser_runtime_setting('action_cache_variants_per_step', ACTION_CACHE_VARIANTS_PER_STEP, 1, 100)

    @staticmethod
    def _planned_assertion_contract(assertions):
        """Assertions as the plan stated them, without runtime binding results.

        Binding writes ``target.locator`` (and flattens a nested intent) into the step before the cache entry
        is written, while the lookup happens before any binding. Hashing the planned contract on both sides is
        what makes a lookup key equal to the key the entry was stored under.
        """
        contract = []
        for assertion in assertions or []:
            if not isinstance(assertion, dict):
                continue
            item = dict(assertion)
            target = item.get('target')
            if isinstance(target, dict):
                cleaned = {key: value for key, value in target.items() if key not in {'locator', 'selection_basis'}}
                intent = cleaned.get('intent')
                while isinstance(intent, dict) and 'intent' in intent:
                    intent = intent['intent']
                if isinstance(intent, dict) and 'locator' in intent:
                    intent = intent['locator']
                if intent is not None:
                    cleaned['intent'] = intent
                item['target'] = cleaned
            contract.append(item)
        return contract

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
                'assertion_contract': self._planned_assertion_contract(step.get('assertions', [])),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        context_digest = hashlib.sha256(context_payload.encode('utf-8')).hexdigest()[:12]
        return f'{ACTION_CACHE_SCHEMA_VERSION}::{safe_case_name}::step{step_no}::{digest}::{context_digest}'

    def _resolved_cache_key(self, step, context):
        """The key used at lookup time for this step when known, so the entry is stored under the same key."""
        return self._cache_key_by_step.get(self._step_context_key(step)) or self._cache_key_for_step(step, context)

    def _find_cached_actions_sync(self, cache_key):
        from django.db.models import F

        from apps.ai_testing.models import AIActionCacheEntry

        now = timezone.now()
        entry = AIActionCacheEntry.objects.filter(cache_key=cache_key, expires_at__gt=now).first()
        if entry is None or not self._reusable_action_sequence(entry.actions):
            return None
        # A hit keeps the entry alive (sliding expiry); entries nobody uses age out.
        AIActionCacheEntry.objects.filter(pk=entry.pk).update(
            hit_count=F('hit_count') + 1, last_hit_at=now, expires_at=now + self._action_cache_ttl(),
        )
        return [action for action in entry.actions if isinstance(action, dict)]

    async def _load_cached_ai_actions(self, step, page_context=None):
        context = page_context or self._cache_context_by_step.get(self._step_context_key(step), {})
        if not context.get('fingerprint'):
            return None  # without a reliable page identity nothing may be reused
        try:
            return await sync_to_async(self._find_cached_actions_sync, thread_sensitive=True)(
                self._cache_key_for_step(step, context),
            )
        except DatabaseError as error:
            logger.warning('planner_v2 failed to read action cache: %s', error)
            return None

    def _upsert_cached_actions_sync(self, step, safe_actions, context):
        from apps.ai_testing.models import AIActionCacheEntry

        now = timezone.now()
        description = str(step.get('description') or '').strip()
        step_no = int(step.get('index') or 0)
        AIActionCacheEntry.objects.update_or_create(
            cache_key=self._resolved_cache_key(step, context),
            defaults={
                'schema_version': ACTION_CACHE_SCHEMA_VERSION,
                'project_id': self.ai_project_id,
                'ai_case_id': self.ai_case_id,
                'case_name': str(self.case_name or '')[:255],
                'step_index': step_no,
                'step_description': description,
                'page_url': str(context.get('url', ''))[:1000],
                'page_fingerprint': str(context.get('fingerprint', ''))[:64],
                'environment_key': self._experience_environment_key()[:200],
                'permission_fingerprint': self._permission_fingerprint(),
                'actions': safe_actions,
                'expires_at': now + self._action_cache_ttl(),
            },
        )
        # Eviction: expired entries go, and one step keeps only its newest page-state variants.
        AIActionCacheEntry.objects.filter(expires_at__lt=now).delete()
        variants = AIActionCacheEntry.objects.filter(
            case_name=str(self.case_name or '')[:255], step_index=step_no, step_description=description,
        ).order_by('-updated_at').values_list('pk', flat=True)
        stale = list(variants[self._action_cache_variant_limit():])
        if stale:
            AIActionCacheEntry.objects.filter(pk__in=stale).delete()

    async def _store_cached_ai_actions(self, step, actions, page_context=None) -> bool:
        """Persist the step's verified actions; returns whether anything was stored.

        The skip reasons used to be silent while the caller still counted a write, so a step that never made it
        into the cache looked identical to one that did. TC_006 stayed permanently cold that way: its first
        step reported a write every run yet had no entry, and there was nothing in the log to say why.
        """
        safe_actions = self._safe_experience_actions(actions)
        if not safe_actions:
            logger.info(
                'planner_v2 step %s not cached: no replayable action in %s',
                step.get('index'), [str(action.get('action') or '') for action in actions or []][:4],
            )
            return False
        context = page_context or self._cache_context_by_step.get(self._step_context_key(step), {})
        if not context.get('fingerprint'):
            logger.info(
                'planner_v2 step %s not cached: no page fingerprint (context keys=%s)',
                step.get('index'), sorted(context) if isinstance(context, dict) else type(context).__name__,
            )
            return False
        try:
            await sync_to_async(self._upsert_cached_actions_sync, thread_sensitive=True)(step, safe_actions, context)
        except DatabaseError as error:
            logger.warning('planner_v2 failed to write action cache: %s', error)
            return False
        return True

    def _delete_cached_actions_sync(self, cache_key):
        from apps.ai_testing.models import AIActionCacheEntry

        return AIActionCacheEntry.objects.filter(cache_key=cache_key).delete()[0]

    async def _delete_cached_ai_actions(self, step, page_context=None):
        context = page_context or self._cache_context_by_step.get(self._step_context_key(step), {})
        try:
            return await sync_to_async(self._delete_cached_actions_sync, thread_sensitive=True)(
                self._resolved_cache_key(step, context),
            )
        except DatabaseError as error:
            logger.warning('planner_v2 failed to delete action cache entry: %s', error)
            return 0

    async def _reused_actions_applicable(self, page, actions) -> str:
        """'' when reused actions can run on the current page, else why not (target missing or hidden, dialog open).

        Cached and experience actions skip the planner's validators, so the first action's target is checked
        against the live DOM before anything is clicked; a stale sequence falls through to a fresh plan instead
        of acting on the wrong element.
        """
        if page is None or not isinstance(actions, list):
            return ''
        # A reused sequence skips the planner observation, so refresh the pre-action baselines the binders and
        # effect detection rely on (control names/positions, accessibility snapshot) from the live page here.
        try:
            controls = await self._build_actionable_controls(page)
        except Exception:
            controls = None
        if isinstance(controls, list):
            self._last_actionable_controls = self._planner_control_baseline(controls)
            try:
                from apps.ai_testing.execution.page_observation import capture_accessibility_snapshot

                self._last_accessibility_snapshot = await capture_accessibility_snapshot(page)
            except Exception:
                pass
        first = next((action for action in actions if isinstance(action, dict) and action.get('action') != 'assert'), None)
        if first is None:
            return ''
        selector = str(first.get('selector') or '').strip()
        role = str(first.get('role') or '').strip()
        accessible_name = str(first.get('accessible_name') or '').strip()
        interactive = str(first.get('action') or '') in {'click', 'hover', 'fill', 'select', 'press', 'type', 'scroll'}
        try:
            if selector:
                locator = page.locator(selector)
                if await locator.count() == 0:
                    return f'selector not on page: {selector[:120]}'
                if interactive and not await locator.first.is_visible():
                    return f'selector hidden: {selector[:120]}'
            elif role and accessible_name:
                if await page.get_by_role(role, name=accessible_name, exact=True).count() == 0:
                    return f'role target not on page: {role} {accessible_name[:60]}'
            else:
                return ''
        except Exception as error:
            return f'target probe failed: {str(error)[:120]}'
        if not isinstance(controls, list):
            return ''
        from apps.ai_testing.execution.blocking_state import build_blocking_state

        blocking_state = build_blocking_state(controls)
        if blocking_state.get('active_layer_ids'):
            inside_layer = any(
                isinstance(control, dict)
                and control.get('blocking_layer') is True
                and str(control.get('selector') or '').strip() == selector
                for control in controls
            )
            if not inside_layer:
                return 'a blocking dialog is open and the reused target is outside it'
        return ''

    async def _invalidate_reused_actions(self, step, action_source):
        if action_source == 'cache':
            await self._delete_cached_ai_actions(step)
        elif action_source == 'experience':
            await self._invalidate_verified_experience(step)

    @staticmethod
    def _step_context_key(step):
        return f"{int(step.get('index') or 0)}::{str(step.get('description') or '').strip()}"

    def _experience_environment_key(self):
        configuration = self.environment_configuration
        return str(getattr(configuration, 'environment', '') or '').strip()

    async def _build_page_context(self, page):
        """Identity of the current page state for action reuse: URL path, masked title and the DOM skeleton.

        Body text used to be part of the fingerprint, which made every data refresh (new alert, another camera
        name, a clock) a cache miss and piled up dozens of variants per step. The skeleton ignores text, counts
        and list lengths while still separating an opened dialog or an expanded panel from the base page. When
        the skeleton cannot be captured the fingerprint is empty and nothing is reused for this step.
        """
        if page is None:
            return {}
        raw_url = str(getattr(page, 'url', '') or '').strip()
        parsed_url = urlsplit(raw_url)
        normalized_url = urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', ''))
        page_title = ''
        application_version = ''
        try:
            page_title = str(await page.title()).strip()
        except Exception:
            page_title = ''
        try:
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
        skeleton = ''
        try:
            skeleton = str(await page.evaluate(PAGE_SKELETON_JS) or '').strip()
        except Exception as error:
            logger.info('planner_v2 page skeleton unavailable: %s', error)
        context = {'url': normalized_url[:1000], 'fingerprint': '', 'application_version': application_version}
        if not skeleton:
            return context
        fingerprint_source = json.dumps(
            {'url': normalized_url, 'title': self._structural_text(page_title, limit=200), 'skeleton': skeleton},
            ensure_ascii=True,
            sort_keys=True,
        )
        context['fingerprint'] = hashlib.sha256(fingerprint_source.encode('utf-8')).hexdigest()
        context['skeleton_size'] = len(skeleton)
        return context

    @staticmethod
    def _structural_text(page_text, limit=4000):
        """Page text with volatile digit runs masked, so live counters and clocks keep the same fingerprint."""
        collapsed = re.sub(r'\s+', ' ', str(page_text or '')).strip()
        return re.sub(r'\d+', '#', collapsed)[:limit]

    @staticmethod
    def _intent_hash(step):
        description = re.sub(r'\s+', ' ', str(step.get('description') or '').strip().lower())
        return hashlib.sha256(description.encode('utf-8')).hexdigest()

    def _permission_fingerprint(self):
        return hashlib.sha256(str(self.execution_user_id or '').encode('utf-8')).hexdigest()

    @staticmethod
    def _assertion_contract_hash(step):
        contract = PyUICompatAgent._planned_assertion_contract(step.get('assertions', []) if isinstance(step, dict) else [])
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
        safe = [action for action in serialized if isinstance(action, dict)]
        # An assert-only outcome depends on the page state of that moment; replaying it would skip the step's
        # action altogether (a cached "assert" for "Click Deactivate" deactivated nobody).
        if not PyUICompatAgent._reusable_action_sequence(safe):
            return []
        return safe

    @staticmethod
    def _reusable_action_sequence(actions) -> bool:
        """A stored sequence is worth replaying only if it performs something; assert/wait alone is not an action."""
        return isinstance(actions, list) and any(
            isinstance(action, dict) and str(action.get('action') or '') not in {'assert', 'wait', ''}
            for action in actions
        )

    def _experience_lookup(self, step, page_context):
        return {
            'project_id': self.ai_project_id,
            'intent_hash': self._intent_hash(step),
            'page_fingerprint': page_context.get('fingerprint', ''),
            'environment_key': self._experience_environment_key(),
            'permission_fingerprint': self._permission_fingerprint(),
            'assertion_contract_hash': self._assertion_contract_hash(step),
        }

    def _experience_reuse_policy(self):
        """'auto_verified' (default) reuses any verified experience; 'confirmed_only' requires a human confirmation."""
        settings = getattr(self.environment_configuration, 'runtime_settings', {}) or {}
        browser = settings.get('ai_testing_browser', {}) if isinstance(settings, dict) else {}
        policy = str(browser.get('experience_reuse_policy') or '').strip().lower()
        return policy if policy in {'auto_verified', 'confirmed_only'} else 'auto_verified'

    def _find_experience_actions(self, step, page_context):
        from apps.ai_testing.models import AIExecutionExperience

        queryset = AIExecutionExperience.objects.filter(
            project_id=self.ai_project_id,
            intent_hash=self._intent_hash(step),
            permission_fingerprint=self._permission_fingerprint(),
            assertion_contract_hash=self._assertion_contract_hash(step),
            status='verified',
            confidence__gte=0.7,
        )
        if self._experience_reuse_policy() == 'confirmed_only':
            queryset = queryset.filter(review_status='confirmed')
        if page_context.get('fingerprint'):
            queryset = queryset.filter(page_fingerprint=page_context['fingerprint'])
        environment_key = self._experience_environment_key()
        if environment_key:
            queryset = queryset.filter(environment_key=environment_key)
        experience = queryset.order_by('-confidence', '-last_verified_at').first()
        if experience is None or not self._reusable_action_sequence(experience.action_sequence):
            return None
        return experience.action_sequence

    async def _load_verified_experience(self, step, page_context):
        if not self.ai_project_id:
            return None
        try:
            actions = await sync_to_async(self._find_experience_actions, thread_sensitive=True)(step, page_context)
        except DatabaseError as error:
            logger.warning('planner_v2 failed to load verified experience: %s', error)
            return None
        return actions if isinstance(actions, list) and actions else None

    def _upsert_experience(self, step, safe_actions, page_context):
        """Record a verified action sequence; repeated independent verification promotes it to reusable."""
        from apps.ai_testing.models import AIExecutionExperience

        lookup = self._experience_lookup(step, page_context)
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
            same_actions = experience.action_sequence == safe_actions
            experience.action_sequence = safe_actions
            if experience.status == 'verified':
                experience.success_count += 1
                experience.confidence = min(0.95, 0.7 + experience.success_count * 0.05)
            elif experience.status == 'pending' and same_actions:
                # The model independently re-derived the same actions and the evidence verified again.
                experience.success_count += 1
                if experience.success_count >= EXPERIENCE_AUTO_VERIFY_SUCCESSES:
                    experience.status = 'verified'
                    experience.confidence = max(experience.confidence, 0.8)
            else:
                # New or previously invalidated sequence: start counting again.
                experience.status = 'pending'
                experience.success_count = 1
                experience.confidence = 0.7
            experience.save()
            return True

    async def _store_verified_experience(self, step, actions):
        if not self.ai_project_id:
            return False
        safe_actions = self._safe_experience_actions(actions)
        if not safe_actions:
            return False
        page_context = self._cache_context_by_step.get(self._step_context_key(step), {})
        try:
            return await sync_to_async(self._upsert_experience, thread_sensitive=True)(step, safe_actions, page_context)
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

    def _invalidate_experience_sync(self, step, page_context):
        from apps.ai_testing.models import AIExecutionExperience

        experience = AIExecutionExperience.objects.select_for_update().filter(
            **self._experience_lookup(step, page_context),
            status='verified',
        ).first()
        if experience is None:
            return 0
        experience.status = 'invalid'
        experience.failure_count += 1
        experience.confidence = max(0.0, experience.confidence - 0.2)
        experience.save(update_fields=['status', 'failure_count', 'confidence', 'updated_at'])
        return 1

    async def _invalidate_verified_experience(self, step):
        if not self.ai_project_id:
            return
        page_context = self._cache_context_by_step.get(self._step_context_key(step), {})
        try:
            await sync_to_async(self._invalidate_experience_sync, thread_sensitive=True)(step, page_context)
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

    def _step_screenshot_filename(self, step_index, suffix=''):
        """Step screenshot name; replans and recoveries pass a suffix so earlier attempts' evidence is not overwritten."""
        return f'{self._case_id_token()}_step_{int(step_index):02d}{suffix}.png'

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
            {'type': 'planner_accessibility_snapshot', **self._last_accessibility_snapshot},
        ]
        artifacts.extend([
            {'type': 'network_response', **event}
            for event in self._recent_network_events[-10:]
            if isinstance(event, dict)
        ])
        if page_text is not None:
            artifacts.append({'type': 'dom_snapshot', 'text': str(page_text)})
        canvas_frames_before = self._merged_canvas_baseline(canvas_frames_before, self._observed_canvas_baseline)
        self._observed_canvas_baseline = None
        try:
            artifacts.extend(await collect_browser_observations(
                page,
                step.get('assertions') or [],
                BrowserObservationContext(
                    native_media_before=media_state_before,
                    visual_frames_before=tuple(visual_frames_before or []),
                    canvas_frames_before=tuple(canvas_frames_before or []),
                    download_events=tuple(self._current_step_download_events()),
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

        audit_action = self._audit_action_payload(executed_action, step)
        persisted_attempt = await sync_to_async(persist_step_attempt)(
            self.execution_record_id,
            step_index,
            audit_action,
            {'output': output} if output is not None else {},
            'completed' if status == 'completed' else status,
            error_message or '',
            hashlib.sha256(environment_value.encode('utf-8')).hexdigest(),
            hashlib.sha256(permission_value.encode('utf-8')).hexdigest(),
            artifacts,
        )
        return {
            **persisted_attempt,
            'action': audit_action,
            'assertion_statuses': await self._evaluate_persisted_assertions(step_index),
        }

    @staticmethod
    def _audit_action_payload(executed_action, step):
        action = executed_action if isinstance(executed_action, dict) else {}
        payload = {
            'action': str(action.get('action') or executed_action or step.get('action') or ''),
            'selector': str(action.get('selector') or ''),
            'url': str(action.get('url') or ''),
            'param': str(action.get('param') or ''),
            'assert_kind': str(action.get('assert_kind') or ''),
            'value_present': bool(action.get('value')),
            'value_digest': PyUICompatAgent._audit_value(action.get('value'), action.get('selector')),
            'source': step.get('step_mode') or 'direct',
            'executor': step.get('executor') or 'browser',
        }
        return payload

    @staticmethod
    def _audit_value(value, selector=None):
        """Privacy-safe audit form of a typed value: a short digest plus length, never the plaintext."""
        text = str(value or '')
        if not text:
            return ''
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]
        return f'sha256:{digest}/len={len(text)}'

    @staticmethod
    def _bind_step_assertions(step, bindings):
        bound_step = dict(step)
        assertions = [dict(assertion) for assertion in step.get('assertions', [])]
        for binding in bindings:
            assertion = assertions[int(binding['assertion_index']) - 1]
            original_target = assertion.get('target', {})
            semantic_intent = original_target
            while isinstance(semantic_intent, dict) and 'intent' in semantic_intent:
                semantic_intent = semantic_intent['intent']
            if isinstance(semantic_intent, dict) and 'locator' in semantic_intent:
                semantic_intent = semantic_intent['locator']
            target = dict(original_target) if isinstance(original_target, dict) else {}
            target.update({'locator': binding['locator'], 'intent': semantic_intent})
            assertion['target'] = target
        bound_step['assertions'] = assertions
        return bound_step

    async def _apply_assertion_bindings(self, step_index, step, actions):
        bindings = actions[0].get('assertion_bindings', []) if actions else []
        if not bindings:
            return
        if self.execution_record_id is not None:
            from apps.ai_testing.execution.plan_persistence import persist_bound_step

            await sync_to_async(persist_bound_step)(self.execution_record_id, step_index, bindings)
        bound_step = self._bind_step_assertions(step, bindings)
        step.clear()
        step.update(bound_step)

    async def _bind_required_assertions_after_action(
        self,
        page,
        step: dict,
        step_index: int,
        actions: list[dict],
        step_callback,
        history,
    ) -> bool:
        bindable_kinds = {'field_value', 'popup', 'element_state', 'collection', 'absence'}
        has_bound_assertion = any(
            isinstance(assertion, dict) and str((assertion.get('target') or {}).get('locator') or '').strip()
            for assertion in step.get('assertions') or []
        )
        if self.execution_record_id is not None and has_bound_assertion:
            await self._clear_vanished_assertion_bindings(page, step, step_index)
        unresolved = [
            assertion
            for assertion in step.get('assertions') or []
            if (
                isinstance(assertion, dict)
                and assertion.get('required', True) is not False
                and assertion.get('assert_kind') in bindable_kinds
                and not str((assertion.get('target') or {}).get('locator') or '').strip()
            )
        ]
        if not unresolved or not actions or actions[-1].get('action') == 'assert':
            return False
        image_unresolved = [
            assertion for assertion in unresolved
            if isinstance(assertion.get('target'), dict) and assertion['target'].get('visual_content') == 'image'
        ]
        if image_unresolved:
            # A thumbnail that has not rendered yet cannot be bound by anyone; give the lazy image (or the
            # target camera's card) its bounded chance before binders decline and the model burns attempts.
            try:
                await self._wait_for_rendered_visual_content(page, step, image_unresolved)
            except Exception as error:
                logger.info('planner_v2 pre-binding render wait skipped: %s', error)
        self._binding_verified_predecessors = self._verified_predecessor_context(history) if history is not None else []
        binders = (
            ('field_value', self._field_value_bindings_from_completed_action),
            ('selected_value', self._selected_value_binding_from_completed_click),
            ('visible_element', self._visible_element_binding_from_completed_click),
            ('intent_value', self._intent_value_binding_from_completed_action),
            ('rendered_visual', self._rendered_visual_binding_from_completed_action),
            ('vanished_media', self._vanished_media_binding_from_completed_action),
            ('fresh_content', self._fresh_content_binding_from_completed_action),
            ('collection', self._collection_binding_from_completed_action),
            ('inherited_collection', self._inherited_collection_binding_from_read_only_action),
        )
        # Every binder reasons about one assertion at a time, so a step with several unresolved assertions
        # (a result count plus a thumbnail) is bound assertion by assertion and the results are merged.
        deterministic_bindings = []
        still_unresolved = []
        for assertion in unresolved:
            declined = []
            bound = []
            for binder_name, binder in binders:
                bound = await binder(page, step, [assertion], actions[-1])
                if bound:
                    if history is not None:
                        history.artifacts.append({
                            'type': 'deterministic_binding',
                            'step': step_index,
                            'binder': binder_name,
                            'bindings': bound,
                        })
                    break
                declined.append(binder_name)
            if bound:
                deterministic_bindings.extend(bound)
            else:
                still_unresolved.append(assertion)
                if history is not None:
                    history.artifacts.append({
                        'type': 'binders_declined',
                        'step': step_index,
                        'binders': declined,
                        'unresolved': [{'assert_kind': assertion.get('assert_kind'), 'intent': (assertion.get('target') or {}).get('intent')}],
                        'had_observable_baseline': self._observable_baseline is not None,
                        'had_visual_baseline': self._rendered_visual_baseline is not None,
                        'notes': list(self._runtime_events),
                    })
                    self._runtime_events = []
        if deterministic_bindings:
            await self._apply_assertion_bindings(
                step_index,
                step,
                [{'action': 'assert', 'assertion_bindings': deterministic_bindings}],
            )
            if not still_unresolved:
                return True
        binding_step = {
            **step,
            'allowed_capabilities': ['browser.inspect'],
            '_prior_actions': [
                {**self._audit_action_payload(action, step), 'status': 'completed'}
                for action in actions[-8:]
            ],
            'description': (
                f"{step['description']}\n"
                'The state-changing action completed. Inspect the current page and return assert with complete '
                'discovered locator bindings for every required DOM assertion. Do not perform another UI action. '
                'For an assertion whose target.visual_content is image, bind the discovered element whose '
                'has_visual_content is true and that displays the rendered image, video, or canvas introduced by '
                'this step; never bind a text label, an empty container, or a loading placeholder.'
            ),
        }
        # A model binding round costs two planner_vision calls. Asking again about a page whose structure has
        # not moved since the last failure returns the same unbindable answer: one step burned twelve rounds
        # this way. The skeleton fingerprint ignores text and list lengths, so a refreshed list still counts as
        # the same state, while an opened dialog or expanded panel correctly counts as a new one worth asking about.
        binding_state = await self._binding_state_key(page, step_index, still_unresolved)
        if binding_state and binding_state in self._exhausted_binding_states:
            logger.info(
                'planner_v2 skipped a repeat binding round for step %s: page state unchanged since the last failure',
                step_index,
            )
            return False
        try:
            binding_actions = await self._plan_ai_step_with_retries(
                page,
                binding_step,
                history,
                step_callback=step_callback,
                step_index=step_index,
                max_attempts=2,
            )
        except PlannerRetryExhaustedError:
            if binding_state:
                self._exhausted_binding_states.add(binding_state)
            logger.info(
                'planner_v2 could not bind required assertions after step %s action; continue with strict evidence capture',
                step_index,
            )
            return False
        await self._apply_assertion_bindings(step_index, step, binding_actions)
        return True

    async def _binding_state_key(self, page, step_index: int, unresolved: list[dict]) -> str:
        """Identify "this step, these assertions, this page structure" so a hopeless round is asked only once."""
        try:
            context = await self._build_page_context(page)
        except Exception as error:
            logger.info('planner_v2 binding state fingerprint unavailable: %s', error)
            return ''
        fingerprint = str((context or {}).get('fingerprint') or '')
        if not fingerprint:
            return ''
        wanted = sorted(
            f"{assertion.get('assert_kind')}|{(assertion.get('target') or {}).get('intent') or ''}"
            for assertion in unresolved
        )
        return f'{step_index}|{fingerprint}|' + '|'.join(wanted)

    async def _field_value_bindings_from_completed_action(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        if len(unresolved) != 1 or unresolved[0].get('assert_kind') != 'field_value':
            return []
        if action.get('action') not in {'fill', 'input', 'type'}:
            return []
        assertion = unresolved[0]
        expected = str((assertion.get('expected') or {}).get('value') or '')
        action_value = str(action.get('value') or action.get('param') or '')
        if assertion.get('operator') != 'equals' or not expected or action_value != expected:
            return []
        candidates = {
            str(element.get('selector') or '').strip()
            for element in await self._build_observable_elements(page)
            if (
                isinstance(element, dict)
                and element.get('tag') in {'input', 'textarea', 'select'}
                and str(element.get('text') or '') == expected
                and str(element.get('selector') or '').strip()
            )
        }
        if len(candidates) != 1:
            return []
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        return [{'assertion_index': assertion_index, 'locator': candidates.pop()}]

    async def _selected_value_binding_from_completed_click(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        """After choosing an option, bind the value assertion to the control that now displays the choice."""
        if len(unresolved) != 1 or action.get('action') not in {'click', 'select'}:
            return []
        assertion = unresolved[0]
        if assertion.get('assert_kind') != 'field_value' or assertion.get('operator') not in {'starts_with', 'equals', 'contains'}:
            return []
        expected = str((assertion.get('expected') or {}).get('value') or '').strip().casefold()
        if not expected:
            return []
        choice_roles = {'option', 'menuitem', 'menuitemcheckbox', 'menuitemradio'}
        candidates: list[tuple[int, str]] = []
        dialog_closed = False
        for _ in range(6):  # the display may refresh a moment after the option is chosen
            controls = await self._build_actionable_controls(page)
            elements = [*controls, *await self._build_observable_elements(page)]
            candidates = self._selected_value_candidates(assertion, expected, choice_roles, self._changed_since_planning(elements))
            if candidates:
                break
            # A confirm click that closed the dialog commits a value the control already displayed while the
            # dialog was open; the closed dialog is the change, so the unchanged display is the evidence.
            dialog_closed = self._pre_action_blocking_layer and not any(
                isinstance(control, dict) and control.get('blocking_layer') is True for control in controls
            )
            if dialog_closed:
                candidates = self._selected_value_candidates(assertion, expected, choice_roles, elements)
                if candidates:
                    logger.info('planner_v2 selected-value binder accepted the display committed by closing the dialog')
                    break
            await page.wait_for_timeout(500)
        if not candidates:
            return []
        best_priority = max(priority for priority, _selector, _rect in candidates)
        best = [(selector, rect) for priority, selector, rect in candidates if priority == best_priority]
        if len(best) != 1:
            innermost = self._innermost_of_nested(best)
            if not innermost:
                logger.info(
                    'planner_v2 selected-value binder declined: %s equally ranked candidates that do not nest (%s)',
                    len(best), [selector for selector, _rect in best][:8],
                )
                return []
            logger.info(
                'planner_v2 selected-value binder resolved %s nested candidates to the innermost %s',
                len(best), innermost,
            )
            best = [(innermost, ())]
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        logger.info('planner_v2 selected-value binder chose %s', best[0][0])
        return [{'assertion_index': assertion_index, 'locator': best[0][0]}]

    @staticmethod
    def _selected_value_candidates(assertion: dict, expected: str, choice_roles: set, discovered: list) -> list[tuple[int, str, tuple]]:
        candidates: list[tuple[int, str, tuple]] = []
        seen: set[str] = set()
        seen_rects: set[tuple] = set()
        for element in discovered:
            if not isinstance(element, dict):
                continue
            selector = str(element.get('selector') or '').strip()
            shown = str(element.get('name') or element.get('text') or '').strip().casefold()
            if not selector or selector in seen or not shown:
                continue
            rect = element.get('rect') if isinstance(element.get('rect'), dict) else None
            rect_key = tuple(int(rect.get(key) or 0) for key in ('x', 'y', 'width', 'height')) if rect else None
            if rect_key is not None and rect_key in seen_rects:
                # The same DOM node discovered twice (attribute selector vs structural selector).
                continue
            matched = shown == expected if assertion.get('operator') == 'equals' else shown.startswith(expected)
            if not matched:
                continue
            role = str(element.get('role') or '').strip().casefold()
            tag = str(element.get('tag') or '').strip().casefold()
            if role in choice_roles or tag == 'option' or (element.get('top_layer') and int(element.get('group_size') or 0) > 1):
                continue
            seen.add(selector)
            if rect_key is not None:
                seen_rects.add(rect_key)
            priority = 2 if tag in {'select', 'input'} or role in {'combobox', 'textbox'} else 1 if not element.get('top_layer') else 0
            candidates.append((priority, selector, rect_key or ()))
        return candidates

    def _is_fresh_content(self, element: dict, baseline: set) -> bool:
        """Whether this element is content the action introduced.

        A new structural selector is the obvious signal, but it misses the common case: a single-page app
        swapping the contents of a container keeps the nth-of-type path, so content that is new to the reader
        is old to the selector set. One measured step showed 12 elements carrying text that was nowhere on the
        page before, while only 1 had a selector the baseline had not already seen. Text that was not on the
        page before the action therefore counts as fresh too.
        """
        if element.get('selector') not in baseline:
            return True
        text = str(element.get('text') or '').strip()
        return bool(text) and text not in self._observable_baseline_texts

    @staticmethod
    def _innermost_of_nested(candidates: list[tuple[str, tuple]]) -> str:
        """Return the innermost selector when the tied candidates are one control seen at several DOM depths.

        A status control's text is reported by the control and by every ancestor that wraps it, so a single
        control on screen arrives here as a chain of boxes that each contain the next. Picking the innermost
        is then correct by construction. Candidates that do not nest are genuinely different controls and the
        caller must keep declining rather than guess between them.
        """
        boxed = [(selector, rect) for selector, rect in candidates if rect and len(rect) == 4 and rect[2] > 0 and rect[3] > 0]
        if len(boxed) != len(candidates) or not boxed:
            return ''

        def contains(outer, inner):
            ox, oy, ow, oh = outer
            ix, iy, iw, ih = inner
            return ox <= ix and oy <= iy and ox + ow >= ix + iw and oy + oh >= iy + ih

        ordered = sorted(boxed, key=lambda item: item[1][2] * item[1][3])
        for (_outer_selector, outer), (_inner_selector, inner) in zip(ordered[1:], ordered):
            if not contains(outer, inner):
                return ''
        return ordered[0][0]

    async def _visible_element_binding_from_completed_click(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        if len(unresolved) != 1 or action.get('action') not in {'click', 'select', 'press', 'hover', 'scroll', 'wait'}:
            return []
        assertion = unresolved[0]
        if (
            assertion.get('assert_kind') != 'element_state'
            or assertion.get('operator') != 'exists'
            or not expects_true((assertion.get('expected') or {}).get('value'))
        ):
            return []

        target = assertion.get('target') or {}
        target_text = str(target.get('text') or '').strip().casefold()
        intent = str(target.get('intent') or '')
        ignored_tokens = {'a', 'an', 'the', 'in', 'on', 'of', 'open', 'role', 'option', 'dropdown', 'menu'}
        intent_tokens = {
            token for token in re.findall(r'\w+', intent.casefold())
            if token not in ignored_tokens
        }
        if not target_text and not intent_tokens:
            return []

        controls = [control for control in await self._build_actionable_controls(page) if isinstance(control, dict)]
        # Dialog content first: while a layer is open it owns the screen, and a background control with a
        # matching name would be the wrong evidence. With no blocking layer on the page that risk is gone, and
        # restricting to the top layer left ordinary content unbindable — a camera list entry named in the plan
        # matched no binder at all, because assertions carrying target.text are excluded from the media binders.
        scoped = [control for control in controls if control.get('top_layer') is True]
        if not scoped and not any(control.get('blocking_layer') is True for control in controls):
            scoped = controls

        candidates_by_name: dict[str, dict[str, Any]] = {}
        for control in scoped:
            name = str(control.get('name') or '').strip()
            selector = str(control.get('selector') or '').strip()
            normalized_name = name.casefold()
            name_tokens = set(re.findall(r'\w+', normalized_name))
            target_matches = (
                normalized_name == target_text
                or normalized_name.startswith(f'{target_text} ')
                or normalized_name.startswith(f'{target_text}(')
                or normalized_name.startswith(f'{target_text}（')
            ) if target_text else intent_tokens.issubset(name_tokens)
            if not name or not selector or not target_matches:
                continue
            candidate = candidates_by_name.setdefault(
                normalized_name,
                {'extra_token_count': len(name_tokens - intent_tokens) if not target_text else len(normalized_name) - len(target_text), 'selectors': []},
            )
            candidate['selectors'].append(selector)
        if not candidates_by_name:
            return []

        minimum_extra_tokens = min(candidate['extra_token_count'] for candidate in candidates_by_name.values())
        best_candidates = [
            candidate
            for candidate in candidates_by_name.values()
            if candidate['extra_token_count'] == minimum_extra_tokens
        ]
        if len(best_candidates) != 1:
            return []
        selectors = best_candidates[0]['selectors']
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        return [{'assertion_index': assertion_index, 'locator': min(selectors, key=len)}]

    async def _intent_value_binding_from_completed_action(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        """Bind an element_state exists assertion whose intent names the text the element shows.

        "status control showing To Do" is satisfied by the one discovered element whose visible text is
        exactly "To Do". Repeated list labels share structural selectors and are skipped in favour of the
        attribute-anchored control; an ambiguous match declines so the planner keeps ownership.
        """
        # Binders read the current page, so read-only recovery actions (scroll, hover, wait) count as completed too.
        if len(unresolved) != 1 or action.get('action') not in {'click', 'select', 'fill', 'press', 'navigate', 'goto', 'scroll', 'hover', 'wait'}:
            return []
        assertion = unresolved[0]
        target = assertion.get('target') or {}
        operator = assertion.get('operator')
        expected_value = (assertion.get('expected') or {}).get('value')
        if assertion.get('assert_kind') != 'element_state' or target.get('visual_content') == 'image':
            return []
        if operator == 'exists':
            if not expects_true(expected_value):
                return []
            value = display_value_from_target(target)
        elif operator in {'equals', 'contains'} and isinstance(expected_value, str):
            # "status control displaying the selected value" contains "Close": the committed value is the text
            # to find, and an option still listed in an open menu is not the control that displays it.
            value = expected_value.strip()
        else:
            return []
        if not value:
            return []
        if operator == 'exists':
            elements = [*await self._build_actionable_controls(page), *await self._build_observable_elements(page)]
            locator = exact_text_locator(value, elements)
        else:
            locator = ''
            for _ in range(6):  # the display may refresh a moment after the option is chosen
                elements = [*await self._build_actionable_controls(page), *await self._build_observable_elements(page)]
                locator = exact_text_locator(
                    value,
                    self._changed_since_planning(elements),
                    allow_containing=operator == 'contains',
                    skip_choices=True,
                    case_sensitive=True,
                )
                if locator:
                    break
                await page.wait_for_timeout(500)
        if not locator:
            return []
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        self._runtime_events.append({'type': 'intent_value_binding', 'value': value, 'locator': locator})
        return [{'assertion_index': assertion_index, 'locator': locator}]

    @staticmethod
    def _rect_key(rect: dict) -> tuple:
        return tuple(int(rect.get(key) or 0) for key in ('x', 'y', 'width', 'height'))

    def _changed_since_planning(self, elements: list[dict]) -> list[dict]:
        """Drop elements that already showed the same text when the action was planned.

        A "close" icon button or a heading that existed before the action cannot be the display of the value
        the action just committed. The same node may be rediscovered under another selector, so position is
        compared as well.
        """
        unchanged = self._pre_action_control_names
        if not unchanged:
            return list(elements)
        kept = []
        for element in elements:
            if not isinstance(element, dict):
                continue
            text = ' '.join(str(element.get('name') or element.get('text') or '').split())
            rect = element.get('rect') if isinstance(element.get('rect'), dict) else None
            if rect and (self._rect_key(rect), text) in unchanged:
                continue
            kept.append(element)
        return kept

    @staticmethod
    def _image_assertions(step: dict) -> list[dict]:
        return [
            assertion
            for assertion in step.get('assertions') or []
            if (
                isinstance(assertion, dict)
                and assertion.get('assert_kind') in {'element_state', 'popup'}
                and assertion.get('operator') == 'exists'
                and assertion.get('required', True) is not False
                and isinstance(assertion.get('target'), dict)
                and assertion['target'].get('visual_content') == 'image'
            )
        ]

    @staticmethod
    def _media_bindable_assertions(step: dict) -> list[dict]:
        """Assertions that a rendered media surface introduced by the step can objectively satisfy."""
        result = []
        for assertion in step.get('assertions') or []:
            if not (
                isinstance(assertion, dict)
                and assertion.get('assert_kind') in {'element_state', 'popup'}
                and assertion.get('operator') == 'exists'
                and assertion.get('required', True) is not False
                and isinstance(assertion.get('target'), dict)
            ):
                continue
            target = assertion['target']
            if target.get('visual_content') == 'image':
                result.append(assertion)
            elif not str(target.get('text') or '').strip() and not str(target.get('locator') or '').strip():
                result.append(assertion)
        return result

    async def _rendered_visual_elements(self, page) -> list[dict]:
        try:
            elements = await page.evaluate(RENDERED_VISUAL_ELEMENTS_JS)
        except Exception as error:
            logger.info('planner_v2 rendered visual inventory failed: %s', error)
            return []
        return [element for element in elements if isinstance(element, dict) and element.get('selector')]

    @staticmethod
    def _vanishing_media_assertions(step: dict) -> list[dict]:
        """not_exists assertions about a media surface the step is expected to remove (close a player, dismiss a preview)."""
        result = []
        for assertion in step.get('assertions') or []:
            if not (
                isinstance(assertion, dict)
                # 'absence' states the same thing as element_state/not_exists and planners use both for a
                # closed player. Recognising only one of them left the other with no deterministic binder:
                # the model guessed a locator instead, and a guess that landed on a surviving container made
                # the step fail even though the player had closed.
                and assertion.get('assert_kind') in {'element_state', 'absence'}
                and assertion.get('operator') == 'not_exists'
                and assertion.get('required', True) is not False
                and isinstance(assertion.get('target'), dict)
            ):
                continue
            target = assertion['target']
            if str(target.get('locator') or '').strip():
                continue
            described = f"{target.get('intent') or ''} {target.get('text') or ''}"
            if target.get('visual_content') == 'image' or MEDIA_INTENT_PATTERN.search(described):
                result.append(assertion)
        return result

    async def _capture_rendered_visual_baseline(self, page, step):
        """Remember which rendered media existed before the step acts, so media that appears or vanishes can be attributed to it."""
        self._rendered_visual_baseline_elements = None
        if not self._media_bindable_assertions(step) and not self._vanishing_media_assertions(step):
            return None
        elements = await self._rendered_visual_elements(page)
        self._rendered_visual_baseline_elements = {str(element['selector']): element for element in elements}
        return set(self._rendered_visual_baseline_elements)

    async def _media_inventory_census(self, page) -> str:
        """Why the rendered-media inventory came back empty on a page that visibly shows pictures.

        The inventory only queries img/canvas/video, while the observable-element inventory also counts a
        sized CSS background image. If a page paints its thumbnails as background images the two disagree,
        and this census says so instead of leaving a bare "observed=0".
        """
        try:
            counts = await page.evaluate(
                """() => {
                    const tagged = Array.from(document.querySelectorAll('img, canvas, video'));
                    const sized = (element) => {
                        const rect = element.getBoundingClientRect();
                        return rect.width >= 24 && rect.height >= 24;
                    };
                    const backgrounds = Array.from(document.querySelectorAll('div, span, a, button, li'))
                        .filter(element => sized(element) && getComputedStyle(element).backgroundImage !== 'none');
                    return {
                        tagged: tagged.length,
                        tagged_sized: tagged.filter(sized).length,
                        backgrounds: backgrounds.length,
                    };
                }"""
            )
        except Exception as error:
            return f'census unavailable: {error}'
        return (
            f"census tagged={counts.get('tagged')} tagged_sized={counts.get('tagged_sized')} "
            f"background_images={counts.get('backgrounds')}"
        )

    def _is_fresh_media(self, element: dict, baseline: set) -> bool:
        """Whether this rendered surface is showing something the action brought in.

        Selector novelty alone misses the case that blocks thumbnail assertions: filtering a camera list
        reuses the row containers, so the thumbnail keeps its structural selector while the picture behind
        it changes. Comparing what the surface is showing catches that.
        """
        selector = element.get('selector')
        if selector not in baseline:
            return True
        previous = (self._rendered_visual_baseline_elements or {}).get(str(selector))
        if not isinstance(previous, dict):
            return False
        key = str(element.get('content_key') or '')
        return bool(key) and key != str(previous.get('content_key') or '')

    async def _vanished_media_binding_from_completed_action(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        """Bind a not_exists media assertion to the rendered surface the action removed.

        A closed player cannot be discovered afterwards, so the planner has no current locator to bind; the
        pre-action inventory is the only objective source for it. The dominant vanished surface is chosen.
        """
        if len(unresolved) != 1 or action.get('action') not in {'click', 'press', 'select'}:
            return []
        assertion = unresolved[0]
        if assertion not in self._vanishing_media_assertions(step):
            return []
        baseline = self._rendered_visual_baseline_elements or {}
        if not baseline:
            return []

        def area(element):
            return int(element.get('area') or 0)

        vanished: list[dict] = []
        for _ in range(8):  # a closing surface may fade out; allow up to ~4 seconds
            current = {str(element.get('selector') or '') for element in await self._rendered_visual_elements(page)}
            vanished = [element for selector, element in baseline.items() if selector not in current]
            if vanished:
                break
            await page.wait_for_timeout(500)
        sizable = [element for element in vanished if area(element) >= 10000]
        pool = sizable or (vanished if len(vanished) == 1 else [])
        if not pool:
            self._runtime_events.append({'type': 'binder_note', 'binder': 'vanished_media', 'vanished': len(vanished)})
            return []
        chosen = max(pool, key=area)
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        logger.info('planner_v2 vanished-media binder chose %s (vanished=%s)', chosen.get('selector'), len(vanished))
        return [{'assertion_index': assertion_index, 'locator': str(chosen['selector'])}]

    @staticmethod
    def _unbound_collection_assertions(step: dict) -> list[dict]:
        return [
            assertion
            for assertion in step.get('assertions') or []
            if (
                isinstance(assertion, dict)
                and assertion.get('assert_kind') == 'collection'
                and assertion.get('required', True) is not False
                and not str((assertion.get('target') or {}).get('locator') or '').strip()
            )
        ]

    async def _capture_observable_baseline(self, page, step):
        """Remember which observable elements existed before the step acts, so new content can be attributed to it."""
        needs_baseline = any(
            (assertion.get('target') or {}).get('visual_content') != 'image'
            for assertion in self._media_bindable_assertions(step)
        ) or bool(self._unbound_collection_assertions(step))
        if not needs_baseline:
            self._observable_baseline_texts = set()
            return None
        elements = [
            element for element in await self._build_observable_elements(page)
            if isinstance(element, dict) and element.get('selector')
        ]
        # Texts are kept alongside selectors because a structural nth-of-type selector survives a SPA
        # swapping the content inside a stable container: the node is new to the user, old to the set.
        self._observable_baseline_texts = {
            text for text in (str(element.get('text') or '').strip() for element in elements) if text
        }
        return {str(element.get('selector') or '') for element in elements}

    async def _collection_binding_from_completed_action(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        """Bind a collection assertion to the repeated-item group the action introduced."""
        if len(unresolved) != 1 or action.get('action') not in {'click', 'select', 'press', 'navigate', 'fill', 'scroll', 'wait'}:
            return []
        assertion = unresolved[0]
        if assertion not in self._unbound_collection_assertions(step):
            return []
        baseline = self._observable_baseline
        if baseline is None:
            return []
        groups: dict[str, dict] = {}
        for element in [*await self._build_observable_elements(page), *await self._build_actionable_controls(page)]:
            if not isinstance(element, dict):
                continue
            group_selector = str(element.get('group_selector') or '').strip()
            if not group_selector or element.get('selector') in baseline:
                continue
            role = str(element.get('role') or '').strip().casefold()
            if role in {'option', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'link'} or element.get('top_layer'):
                continue
            rect = element.get('rect') if isinstance(element.get('rect'), dict) else {}
            area = int(rect.get('width') or 0) * int(rect.get('height') or 0)
            entry = groups.setdefault(group_selector, {'size': int(element.get('group_size') or 1), 'area': 0, 'text': False})
            entry['area'] = max(entry['area'], area)
            entry['text'] = entry['text'] or bool(str(element.get('text') or element.get('name') or '').strip())
        candidates = [(selector, info) for selector, info in groups.items() if info['size'] >= 1 and info['area'] >= 2000 and info['text']]
        if not candidates:
            self._runtime_events.append({'type': 'binder_note', 'binder': 'collection', 'fresh_groups': len(groups)})
            return []
        selector, info = max(candidates, key=lambda item: (item[1]['size'], item[1]['area']))
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        logger.info('planner_v2 collection binder chose %s (size=%s)', selector, info['size'])
        return [{'assertion_index': assertion_index, 'locator': selector}]

    async def _inherited_collection_binding_from_read_only_action(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        """Bind a verify-only step's collection assertion to the verified predecessor group it continues.

        After a wait, scroll or hover nothing new was introduced, so the fresh-group binder declines; the
        repeated items a predecessor step already proved are still the evidence for "the list finished loading".
        """
        if len(unresolved) != 1 or action.get('action') not in {'wait', 'scroll', 'hover'}:
            return []
        assertion = unresolved[0]
        if assertion not in self._unbound_collection_assertions(step):
            return []
        group_selectors = {
            str(element.get('group_selector') or '').strip()
            for element in [*await self._build_observable_elements(page), *await self._build_actionable_controls(page)]
            if isinstance(element, dict) and str(element.get('group_selector') or '').strip()
        }
        intent = str((assertion.get('target') or {}).get('intent') or '')
        locator = continuing_collection_locator(intent, self._binding_verified_predecessors, group_selectors)
        if not locator:
            return []
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        logger.info('planner_v2 inherited collection binder chose %s', locator)
        return [{'assertion_index': assertion_index, 'locator': locator}]

    async def _fresh_content_binding_from_completed_action(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        """Bind an intent-only existence assertion to the largest content block the action introduced."""
        # Each gate says why it refused. A binder that returns an empty list in silence is the reason a
        # single unbindable assertion has cost several diagnostic runs: the log showed the chain failing
        # without showing where.
        def refuse(reason: str) -> list:
            logger.info('planner_v2 fresh-content binder skipped: %s', reason)
            self._runtime_events.append({'type': 'binder_note', 'binder': 'fresh_content', 'skipped': reason})
            return []

        if len(unresolved) != 1:
            return refuse(f'{len(unresolved)} assertions in one call')
        if action.get('action') not in {'click', 'select', 'press', 'navigate', 'scroll', 'wait'}:
            return refuse(f"last action was {action.get('action')}")
        assertion = unresolved[0]
        if assertion not in self._media_bindable_assertions(step):
            return refuse('assertion is not media-bindable')
        if (assertion.get('target') or {}).get('visual_content') == 'image':
            return refuse('image target belongs to the rendered-visual binder')
        named_control = NAMED_CONTROL_INTENT_PATTERN.search(str((assertion.get('target') or {}).get('intent') or ''))
        if named_control:
            # This binder answers "the action introduced this block of content" by taking the largest fresh
            # element. That is the wrong shape of answer for "the Deactivate button exists": the largest
            # fresh block is a layout container, it is present whether or not the button is, and binding it
            # turned a broken flow into a passing step. A named control belongs to a name-matching binder.
            return refuse(f'intent names a control ({named_control.group(0)}); leave it to a name-matching binder')
        baseline = self._observable_baseline
        if baseline is None:
            return refuse('no observable baseline was captured before the action')

        def area(element):
            rect = element.get('rect') if isinstance(element.get('rect'), dict) else {}
            return int(rect.get('width') or 0) * int(rect.get('height') or 0)

        observed = [
            element for element in await self._build_observable_elements(page)
            if isinstance(element, dict) and element.get('selector')
        ]
        fresh = [element for element in observed if self._is_fresh_content(element, baseline)]
        by_selector = sum(1 for element in observed if element.get('selector') not in baseline)
        if len(fresh) < 3:
            logger.info(
                'planner_v2 fresh-content binder declined: only %s new observable element(s) '
                '(baseline=%s observed=%s new_by_selector=%s)',
                len(fresh), len(baseline), len(observed), by_selector,
            )
            self._runtime_events.append({
                'type': 'binder_note', 'binder': 'fresh_content', 'fresh': len(fresh),
                'baseline': len(baseline), 'observed': len(observed), 'new_by_selector': by_selector,
            })
            return []
        sizable = [element for element in fresh if area(element) >= 10000]
        with_text = [element for element in sizable if str(element.get('text') or '').strip()]
        pool = with_text or sizable
        if not pool:
            return refuse(
                f'{len(fresh)} new element(s) but none reaches 10000px2 '
                f'(largest={max((area(element) for element in fresh), default=0)})'
            )
        chosen = max(pool, key=area)
        if assertion.get('assert_kind') == 'popup':
            # Diagnostic only: dialog text is too weak a signal to refuse the evidence (see planner note).
            mismatch = popup_intent_mismatch(
                str((assertion.get('target') or {}).get('intent') or ''),
                str(chosen.get('text') or ''),
            )
            if mismatch:
                self._runtime_events.append({'type': 'popup_intent_warning', 'binder': 'fresh_content', 'detail': mismatch[:200]})
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        logger.info('planner_v2 fresh-content binder chose %s (fresh=%s)', chosen.get('selector'), len(fresh))
        return [{'assertion_index': assertion_index, 'locator': str(chosen['selector'])}]

    async def _rendered_visual_binding_from_completed_action(
        self,
        page,
        step: dict,
        unresolved: list[dict],
        action: dict,
    ) -> list[dict]:
        if len(unresolved) != 1 or action.get('action') not in {'click', 'select', 'press', 'fill', 'navigate', 'scroll', 'wait'}:
            return []
        assertion = unresolved[0]
        if assertion not in self._media_bindable_assertions(step):
            return []
        baseline = self._rendered_visual_baseline
        if baseline is None:
            return []
        observed = await self._rendered_visual_elements(page)
        fresh = [element for element in observed if self._is_fresh_media(element, baseline)]
        if not fresh:
            logger.info(
                'planner_v2 media binder declined: no new rendered media (baseline=%s observed=%s%s)',
                len(baseline), len(observed),
                f' {await self._media_inventory_census(page)}' if not observed else '',
            )
            self._runtime_events.append({
                'type': 'binder_note', 'binder': 'rendered_visual',
                'fresh': 0, 'baseline': len(baseline), 'observed': len(observed),
            })
            return []
        is_image = (assertion.get('target') or {}).get('visual_content') == 'image'

        def area(element):
            return int(element.get('area') or 0)

        target_rects = await self._target_camera_card_rects(page, step)
        if target_rects:
            in_target = [
                element for element in fresh
                if any(self._rect_inside(element.get('rect'), target) for target in target_rects)
            ]
            if in_target:
                chosen = max(in_target, key=area)
                logger.info('planner_v2 media binder chose the target camera thumbnail %s', chosen.get('selector'))
                assertion_index = next(
                    index
                    for index, candidate in enumerate(step.get('assertions') or [], start=1)
                    if candidate is assertion
                )
                return [{'assertion_index': assertion_index, 'locator': str(chosen['selector'])}]
            # The target card is visible but its thumbnail has not rendered: do not bind a neighbour.
            self._runtime_events.append({'type': 'binder_note', 'binder': 'rendered_visual', 'target_camera_pending': len(fresh)})
            return []

        def ratio(element):
            return float(element.get('viewport_ratio') or 0)

        # A layer introduced by the action (dialog, popover, detail pane) is the strongest signal;
        # for intent-only assertions a tiny layered thumbnail (e.g. a toast) is not enough.
        top_layer = [element for element in fresh if element.get('top_layer') and (is_image or area(element) >= 40000)]
        dominant = [element for element in fresh if ratio(element) >= 0.2]
        if top_layer:
            chosen = max(top_layer, key=area)
        elif dominant:
            chosen = max(dominant, key=area)
        elif is_image and len(fresh) == 1:
            chosen = fresh[0]
        else:
            # Several small in-page media surfaces and no layer introduced by the action: ambiguous.
            logger.info(
                'planner_v2 media binder declined: fresh=%s top_layer=%s dominant=%s image=%s',
                len(fresh), len(top_layer), len(dominant), is_image,
            )
            self._runtime_events.append({'type': 'binder_note', 'binder': 'rendered_visual', 'fresh': len(fresh), 'top_layer': len(top_layer), 'dominant': len(dominant)})
            return []
        logger.info(
            'planner_v2 media binder chose %s (fresh=%s top_layer=%s dominant=%s image=%s)',
            chosen.get('selector'), len(fresh), len(top_layer), len(dominant), is_image,
        )
        assertion_index = next(
            index
            for index, candidate in enumerate(step.get('assertions') or [], start=1)
            if candidate is assertion
        )
        return [{'assertion_index': assertion_index, 'locator': str(chosen['selector'])}]

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
    def _should_retry_assertions(step, action_completed, assertions_verified, action_source, assertion_statuses=()):
        return (
            step.get('verification_required', True) is not False
            and action_completed
            and not assertions_verified
            and action_source in {'model', 'cache', 'experience'}
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

    def _latest_assertion_actuals(self, step_index):
        """Observed values from the most recent evaluation of this step, aligned to its assertions."""
        from apps.ai_testing.models import AIExecutionAssertionResult, AIExecutionStep

        if self.execution_record_id is None:
            return []
        try:
            step = (
                AIExecutionStep.objects.filter(
                    plan_revision__execution_record_id=self.execution_record_id,
                    display_order=step_index,
                )
                .order_by('-plan_revision__revision_number')
                .first()
            )
            if step is None or not isinstance(step.assertions, list) or not step.assertions:
                return []
            rows = list(
                AIExecutionAssertionResult.objects.filter(
                    step__plan_revision__execution_record_id=self.execution_record_id,
                    step__display_order=step_index,
                ).order_by('-id')[:len(step.assertions)]
            )[::-1]
        except Exception as error:  # diagnostic enrichment only; never block the retry loop
            logger.debug('planner_v2 could not load observed assertion values: %s', error)
            return []
        return [row.actual if isinstance(row.actual, dict) else {} for row in rows]

    @staticmethod
    def _describe_assertion_shortfall(step, statuses, max_length=500, actuals=None):
        """Summarize which assertion contracts remained unverified, for planner feedback."""
        assertions = step.get('assertions', []) if isinstance(step, dict) else []
        lines = []
        for index, (assertion, status) in enumerate(zip(assertions, statuses), start=1):
            if not isinstance(assertion, dict) or status == 'passed':
                continue
            observed = actuals[index - 1] if isinstance(actuals, list) and len(actuals) >= index else None
            kind = str(assertion.get('assert_kind') or '').strip() or 'assertion'
            operator = str(assertion.get('operator') or '').strip()
            expected_value = assertion.get('expected')
            expected = expected_value.get('value') if isinstance(expected_value, dict) else expected_value
            target = assertion.get('target')
            label = ''
            if isinstance(target, dict):
                label = str(target.get('text') or '').strip() or str(target.get('intent') or '').strip()
                if isinstance(label, dict):
                    label = str(label.get('intent') or '').strip()
            if len(label) > 60:
                label = f'{label[:57]}...'
            expected_text = 'None' if expected is None else str(expected)
            line = f'#{index} {kind}({operator}) expected={expected_text} -> {status}'
            if isinstance(observed, dict):
                facts = {key: value for key, value in observed.items() if key != 'reason' and value is not None}
                summary = json.dumps(facts, ensure_ascii=False, default=str) if facts else str(observed.get('reason') or '')
                if summary:
                    line = f'{line} observed={summary[:160]}'
            if label:
                line = f'{line} target={label!r}'
            lines.append(line)
        detail = ' | '.join(lines)
        if len(detail) > max_length:
            detail = f'{detail[:max_length - 3]}...'
        return detail

    async def _wait_for_assertion_observation(self, page, step):
        assertions = step.get('assertions') or []
        image_assertions = [
            assertion
            for assertion in assertions
            if (
                isinstance(assertion, dict)
                and assertion.get('assert_kind') in {'element_state', 'popup'}
                and assertion.get('operator') == 'exists'
                and assertion.get('required', True) is not False
                and isinstance(assertion.get('target'), dict)
                and assertion['target'].get('visual_content') == 'image'
            )
        ]
        media_assertions = self._media_bindable_assertions(step)
        if image_assertions or (media_assertions and self._rendered_visual_baseline is not None):
            await self._wait_for_rendered_visual_content(page, step, image_assertions or media_assertions)
        download_assertions = [
            assertion
            for assertion in assertions
            if isinstance(assertion, dict) and assertion.get('assert_kind') == 'download_task'
        ]
        playback_assertions = [
            assertion
            for assertion in assertions
            if (
                isinstance(assertion, dict)
                and assertion.get('assert_kind') in {'playback', 'stream_state'}
                and assertion.get('required', True) is not False
            )
        ]
        collection_assertions = [
            assertion
            for assertion in assertions
            if (
                isinstance(assertion, dict)
                and assertion.get('assert_kind') == 'collection'
                and assertion.get('required', True) is not False
            )
        ]
        if collection_assertions:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError

            timeout_ms = min(10000, max(
                int(assertion.get('timeout_ms') or step.get('timeout_ms') or 10000)
                for assertion in collection_assertions
            ))
            try:
                await page.wait_for_load_state('networkidle', timeout=timeout_ms)
            except (PlaywrightTimeoutError, TimeoutError):
                logger.info(
                    'planner_v2 collection observation networkidle timeout after %sms; '
                    'continue with strict evidence capture',
                    timeout_ms,
                )
            return
        if playback_assertions:
            from apps.ai_testing.execution.browser_observers import capture_canvas_frames

            stream_assertions = [assertion for assertion in playback_assertions if assertion.get('assert_kind') == 'stream_state']
            timeout_ms = max(
                int(assertion.get('timeout_ms') or step.get('timeout_ms') or 10000)
                for assertion in playback_assertions
            )
            if stream_assertions:
                # A live stream negotiates and decodes before its first picture; give it a bounded head start
                # instead of judging a canvas that has not drawn yet and replanning (which opens another stream).
                timeout_ms = max(timeout_ms, STREAM_START_WAIT_MS)
            minimum_advanced_seconds = max(
                float((assertion.get('expected') or {}).get('minimum_advanced_seconds') or 0)
                for assertion in playback_assertions
            )
            deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
            playback_baselines = {}
            self._observed_canvas_baseline = None
            iteration = 0
            while True:
                iteration += 1
                if stream_assertions and iteration % 2 == 1:
                    frames = await capture_canvas_frames(page, stream_assertions)
                    if self._observed_canvas_baseline is None:
                        self._observed_canvas_baseline = list(frames)
                    else:
                        if self._canvas_frames_changed(self._observed_canvas_baseline, frames):
                            return
                        self._observed_canvas_baseline = self._first_picture_canvas_frames(self._observed_canvas_baseline, frames)
                media_state = await self._capture_media_state(page)
                if isinstance(media_state, list):
                    for media_index, media in enumerate(media_state):
                        if not isinstance(media, dict):
                            continue
                        try:
                            ready_state = int(media.get('readyState') or 0)
                            current_time = float(media.get('currentTime') or 0)
                        except (TypeError, ValueError):
                            continue
                        if ready_state < 2 or media.get('paused', True) or media.get('ended', False):
                            continue
                        baseline = playback_baselines.setdefault(media_index, current_time)
                        if current_time - baseline >= minimum_advanced_seconds:
                            return
                remaining_ms = round((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    return
                await page.wait_for_timeout(min(500, remaining_ms))
        if not download_assertions:
            await page.wait_for_timeout(300)
            return
        timeout_ms = max(
            int(assertion.get('timeout_ms') or step.get('timeout_ms') or 10000)
            for assertion in download_assertions
        )
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        while not self._current_step_download_events() and time.monotonic() < deadline:
            await page.wait_for_timeout(min(500, max(1, round((deadline - time.monotonic()) * 1000))))

    @staticmethod
    def _first_picture_canvas_frames(baseline: list, frames: list) -> list:
        """Keep, per canvas, the earliest frame that shows a picture; a blank connecting canvas is not a baseline."""
        by_index = {frame.get('index'): dict(frame) for frame in baseline if isinstance(frame, dict)}
        for frame in frames or []:
            if not isinstance(frame, dict):
                continue
            current = by_index.get(frame.get('index'))
            if current is None or (not current.get('visual_signal') and frame.get('visual_signal')):
                by_index[frame.get('index')] = dict(frame)
        return list(by_index.values())

    @staticmethod
    def _canvas_frames_changed(baseline: list, frames: list) -> bool:
        """True when a canvas that already showed a picture now shows a different one (a live stream is drawing)."""
        before = {frame.get('index'): frame for frame in baseline if isinstance(frame, dict)}
        for frame in frames or []:
            if not isinstance(frame, dict):
                continue
            earlier = before.get(frame.get('index'))
            if (
                earlier is not None
                and earlier.get('visual_signal') and frame.get('visual_signal')
                and earlier.get('content_hash') and frame.get('content_hash')
                and earlier.get('content_hash') != frame.get('content_hash')
            ):
                return True
        return False

    @staticmethod
    def _merged_canvas_baseline(pre_action_frames, observed_frames) -> list:
        """Evidence baseline for canvas change: the pre-action frame, or for a canvas the action introduced (or one
        that was still blank before the action) the first picture observed while waiting for the stream."""
        merged = {frame.get('index'): dict(frame) for frame in pre_action_frames or [] if isinstance(frame, dict)}
        for frame in observed_frames or []:
            if not isinstance(frame, dict):
                continue
            current = merged.get(frame.get('index'))
            if current is None or (not current.get('visual_signal') and frame.get('visual_signal')):
                merged[frame.get('index')] = dict(frame)
        return list(merged.values())

    def _current_step_download_events(self):
        return self._recent_download_events[self._download_event_baseline:]

    async def _wait_for_rendered_visual_content(self, page, step, image_assertions):
        """Give lazily loaded images and media a bounded chance to render before evidence capture.

        Camera thumbnails are fetched one by one after a list opens and commonly take 20-30 seconds, so an
        image assertion waits noticeably longer than other media. When the step names the environment's
        target camera, the wait ends only once a thumbnail renders inside that camera's card.

        The budget is spent in two phases and is amortised across the whole step. Waiting the full image
        budget while the target camera's card is not even on screen buys nothing: the card usually appears
        only after the model expands its site group, so that phase is capped short and control returns to the
        model. And because a step can re-enter this wait on every assertion replan, the time already spent is
        subtracted from a per-step ceiling; TC_006 previously paid the full 45s eighteen times and exhausted
        its 600s step budget inside step 1, which left the case permanently uncached and failing.
        """
        timeout_ms = min(15000, max(
            int(assertion.get('timeout_ms') or step.get('timeout_ms') or 10000)
            for assertion in image_assertions
        ))
        locators = [
            locator
            for assertion in image_assertions
            for locator in [str((assertion.get('target') or {}).get('locator') or '').strip()]
            if locator
        ]
        is_image_wait = bool(self._image_assertions(step))
        baseline = self._rendered_visual_baseline if not locators else None
        if not locators and not is_image_wait:
            timeout_ms = min(timeout_ms, 5000)
        if is_image_wait and not locators:
            timeout_ms = min(60000, max(timeout_ms, IMAGE_RENDER_WAIT_MS))
        wants_target = bool(is_image_wait and not locators and self._step_targets_configured_camera(step))
        target_rects = await self._target_camera_card_rects(page, step) if wants_target else []

        step_key = str(step.get('index') or step.get('description') or '')
        spent_ms = self._render_wait_spent_ms.get(step_key, 0)
        budget_left_ms = max(0, RENDER_WAIT_BUDGET_PER_STEP_MS - spent_ms)
        if budget_left_ms <= 0:
            logger.info(
                'planner_v2 step %s already spent its %sms render-wait budget; capture evidence now',
                step.get('index'), spent_ms,
            )
            return
        timeout_ms = min(timeout_ms, budget_left_ms)
        started_at = time.monotonic()
        card_deadline = (
            started_at + min(CARD_APPEAR_WAIT_MS, timeout_ms) / 1000.0
            if wants_target and not target_rects
            else None
        )
        deadline = started_at + max(0, timeout_ms) / 1000.0
        probes = 0
        try:
            while True:
                probes += 1
                try:
                    if wants_target and not target_rects and probes % 4 == 0:
                        # The card may only appear once the site group expands; keep looking for it.
                        target_rects = await self._target_camera_card_rects(page, step)
                        if target_rects:
                            card_deadline = None  # the card is here: the thumbnail may use the full budget
                    if wants_target and not target_rects:
                        settled = False  # another camera's thumbnail is not the target's
                    elif target_rects:
                        # The step is about the configured target camera: it is settled once any rendered media
                        # sits inside that camera's card, whether or not the media existed before the action.
                        settled = any(
                            self._rect_inside(element.get('rect'), target)
                            for element in await self._rendered_visual_elements(page)
                            for target in target_rects
                        )
                    elif locators or baseline is None:
                        settled = await page.evaluate(VISUAL_CONTENT_SETTLED_JS, locators)
                    else:
                        # Unbound media assertion with a pre-action baseline: wait for the surface the
                        # action introduces, not merely for already-present media to finish loading.
                        settled = any(
                            element.get('selector') not in baseline
                            for element in await self._rendered_visual_elements(page)
                        )
                except Exception as error:
                    logger.info('planner_v2 visual content settle probe failed: %s', error)
                    return
                if settled:
                    return
                now = time.monotonic()
                if card_deadline is not None and now >= card_deadline:
                    logger.info(
                        'planner_v2 target camera card still absent after %sms; stop waiting so the step can act',
                        round(CARD_APPEAR_WAIT_MS),
                    )
                    return
                remaining_ms = round((deadline - now) * 1000)
                if remaining_ms <= 0:
                    logger.info(
                        'planner_v2 visual content did not settle within %sms; continue with strict evidence capture',
                        timeout_ms,
                    )
                    return
                await page.wait_for_timeout(min(500, remaining_ms))
        finally:
            self._render_wait_spent_ms[step_key] = spent_ms + round((time.monotonic() - started_at) * 1000)

    async def _retry_assertion_failure(self, page, step, step_index, actions, assertion_statuses, step_callback, timeout_error, history, artifact_dir):
        if self.execution_record_id is None:
            return None
        await self._clear_vanished_assertion_bindings(page, step, step_index)
        if actions and isinstance(actions[-1], dict) and actions[-1].get('action') != 'assert':
            # Before any rebinding, deal with a click that did nothing. This must not be gated on the step's
            # assertion kinds: steps asserting page text need it as much as steps asserting an element.
            await self._retry_swallowed_action(page, step, step_index, actions[-1], step_callback, history)
        if not self._step_budget_exhausted():
            recovered = await self._recover_by_rebinding(page, step, step_index, actions, step_callback, history, artifact_dir)
            if recovered is not None:
                return recovered
        shortfall = PyUICompatAgent._describe_assertion_shortfall(
            step, assertion_statuses, actuals=await sync_to_async(self._latest_assertion_actuals)(step_index),
        )
        failure = (
            f'Required assertions were not verified: {", ".join(assertion_statuses)}.'
            + (f' {shortfall}' if shortfall else '')
            + (f' {self._last_action_effect_note}' if self._last_action_effect_note else '')
        )
        replan_limit = self._assertion_replan_limit()
        persisted_actions = await sync_to_async(self._persisted_step_action_history)(step_index)
        prior_actions = persisted_actions or [self._audit_action_payload(action, step) for action in actions[-8:]]
        persisted_attempt = None
        screenshot_path = None
        previous_outcome = None
        for attempt in range(1, replan_limit + 1):
            if self._step_budget_exhausted():
                budget_message = f'Step time budget exhausted after {attempt - 1} assertion replan(s).'
                await self._emit(step_callback, {'type': 'log', 'content': f'[planner_v2] Step {step_index}: {budget_message}\n'})
                return 'inconclusive', budget_message, actions[-1].get('action') if actions else '', actions, persisted_attempt, screenshot_path
            replanning_step = {
                **step,
                '_planner_failure': failure,
                '_prior_actions': prior_actions[-16:],
                '_verified_predecessors': self._verified_predecessor_context(history),
                'description': (
                    f"{step['description']}\n"
                    f'{failure} Inspect the current page evidence and choose a different action sequence.'
                ),
            }
            try:
                replan_actions = await self._plan_ai_step_with_retries(
                    page, replanning_step, history, step_callback=step_callback, step_index=step_index,
                )
            except PlannerRetryExhaustedError as error:
                error_message = f'{type(error).__name__}: {error}'
                return 'inconclusive', error_message, actions[-1].get('action') if actions else '', actions, persisted_attempt, screenshot_path
            from apps.ai_testing.execution.plan_persistence import persist_replanned_step

            await sync_to_async(persist_replanned_step)(
                self.execution_record_id, step_index, actions[-1] if actions else {}, failure, replan_actions,
            )
            await self._emit(
                step_callback,
                {'type': 'log', 'content': f'[planner_v2] Step {step_index}: replanning after assertion failure ({attempt}/{replan_limit}).\n'},
            )
            media_state_before = await self._capture_media_state(page)
            from apps.ai_testing.execution.browser_observers import capture_canvas_frames, capture_visual_frames
            visual_frames_before = await capture_visual_frames(page, step.get('assertions') or [])
            canvas_frames_before = await capture_canvas_frames(page, step.get('assertions') or [])
            self._observed_canvas_baseline = None
            self._download_event_baseline = len(self._recent_download_events)
            self._pre_action_visual_frames = None
            try:
                await self._execute_ai_actions(
                    page, step, replan_actions, step_index, step_callback, timeout_error, history=history,
                )
                action_status = 'completed'
                error_message = ''
            except Exception as error:
                action_status = 'failed'
                error_message = f'{type(error).__name__}: {error}'
            await self._wait_for_assertion_observation(page, step)
            if action_status == 'completed':
                await self._bind_required_assertions_after_action(
                    page, step, step_index, replan_actions, step_callback, history,
                )
            screenshot_path = await self._capture_screenshot(
                page, artifact_dir, self._step_screenshot_filename(step_index, suffix=f'_r{attempt}'),
            )
            persisted_attempt = await self._persist_step_attempt(
                step_index, step, replan_actions[-1] if replan_actions else {}, action_status,
                error_message, None, screenshot_path, page, media_state_before,
                self._pre_action_visual_frames or visual_frames_before,
                canvas_frames_before,
            )
            statuses = persisted_attempt.get('assertion_statuses', []) if persisted_attempt else []
            required_statuses = self._required_assertion_statuses(step, statuses)
            status = self._status_after_assertions(action_status, required_statuses)
            if self._step_assertions_are_verified(step, required_statuses) or action_status != 'completed':
                return status, error_message, replan_actions[-1].get('action') if replan_actions else '', replan_actions, persisted_attempt, screenshot_path
            outcome = (self._action_signature(replan_actions), tuple(required_statuses))
            if outcome == previous_outcome:
                stall_message = 'Replanning repeated the same actions with the same unverified outcome; stopping early.'
                await self._emit(step_callback, {'type': 'log', 'content': f'[planner_v2] Step {step_index}: {stall_message}\n'})
                return status, stall_message, replan_actions[-1].get('action') if replan_actions else '', replan_actions, persisted_attempt, screenshot_path
            previous_outcome = outcome
            shortfall = PyUICompatAgent._describe_assertion_shortfall(
                step, required_statuses, actuals=await sync_to_async(self._latest_assertion_actuals)(step_index),
            )
            failure = (
                f'Required assertions were not verified: {", ".join(required_statuses)}.'
                + (f' {shortfall}' if shortfall else '')
            )
            actions = replan_actions
            persisted_actions = await sync_to_async(self._persisted_step_action_history)(step_index)
            if persisted_actions:
                prior_actions = persisted_actions[-16:]
            else:
                persisted_action = persisted_attempt.get('action') if isinstance(persisted_attempt, dict) else None
                prior_actions.append(
                    persisted_action
                    if isinstance(persisted_action, dict)
                    else self._audit_action_payload(replan_actions[-1], step)
                )
        return status, failure, actions[-1].get('action') if actions else '', actions, persisted_attempt, screenshot_path

    async def _action_had_visible_effect(self, page):
        """None without a pre-action baseline; otherwise whether the URL, content or media changed since it."""
        current_url = str(getattr(page, 'url', '') or '')
        if self._pre_action_url and current_url and current_url != self._pre_action_url:
            return True
        if self._pre_action_control_names:
            # A control whose text changed in place (a status now reading "Close") is a visible effect too.
            texts_by_position: dict[tuple, set] = {}
            for rect_key, text in self._pre_action_control_names:
                texts_by_position.setdefault(rect_key, set()).add(text)
            # Novelty is judged by text, never by pixel position: rect keys are exact coordinates, so a
            # one-pixel scroll or a reflow would otherwise mark every control as revealed and make this
            # method report an effect for any click at all, silently disabling swallowed-click recovery.
            previous_texts = {text for _rect_key, text in self._pre_action_control_names if text}
            revealed_controls = 0
            for control in await self._build_actionable_controls(page):
                if not isinstance(control, dict) or not isinstance(control.get('rect'), dict):
                    continue
                rect_key = self._rect_key(control['rect'])
                text = ' '.join(str(control.get('name') or '').split())
                if rect_key in texts_by_position and text not in texts_by_position[rect_key]:
                    return True
                if text and text not in previous_texts:
                    revealed_controls += 1
            # A panel that expanded brings a row of genuinely new labels (filters, tabs); a single stray
            # control could be a tooltip, so require a group.
            if revealed_controls >= 2:
                return True
        if self._observable_baseline is None and self._rendered_visual_baseline is None:
            return None
        if self._observable_baseline is not None:
            current = {
                str(element.get('selector') or '')
                for element in await self._build_observable_elements(page)
                if isinstance(element, dict) and element.get('selector')
            }
            if current - self._observable_baseline:
                return True
        if self._rendered_visual_baseline is not None:
            rendered = {str(element.get('selector') or '') for element in await self._rendered_visual_elements(page)}
            if rendered - self._rendered_visual_baseline:
                return True
        return False

    @staticmethod
    def _control_toggles_state(action: dict, controls: list | None) -> bool:
        """True for a control that undoes itself when clicked twice (toggle, collapse/expand, switch, checkbox).

        Repeating such a click after a slow first response would close the panel it had just opened, so the
        swallowed-action retry must leave it alone and let the normal replan look at the page instead.
        """
        selector = str(action.get('selector') or '').strip()
        names = [str(action.get('accessible_name') or '')]
        for control in controls or []:
            if not isinstance(control, dict) or not selector or str(control.get('selector') or '').strip() != selector:
                continue
            if str(control.get('role') or '').strip().casefold() in {'switch', 'checkbox', 'menuitemcheckbox', 'menuitemradio'}:
                return True
            names.append(str(control.get('name') or ''))
        haystack = ' '.join([selector, *names]).casefold()
        return bool(re.search(r'toggle|collapse|expand|aria-expanded|aria-pressed|\bswitch\b', haystack))

    async def _click_inner_activator(self, page, selector: str) -> bool:
        """Click the thumbnail/link inside a container whose own click had no effect."""
        if not selector or selector.startswith('text='):
            return False
        try:
            inner = page.locator(f'{selector} img, {selector} a, {selector} [role="button"], {selector} button').first
            if await inner.count() == 0 or not await inner.is_visible():
                return False
            await inner.click(timeout=5000)
            return True
        except Exception as error:
            logger.info('planner_v2 inner activator click failed: %s', error)
            return False

    async def _retry_swallowed_action(self, page, step, step_index, last_action, step_callback, history) -> None:
        """Repeat a click that changed nothing, then try the activator inside it.

        Live lists and portals routinely swallow the first click on a row, and some rows are containers whose
        real activator is an inner thumbnail or link. This runs before any rebinding and independently of the
        step's assertion kinds: a step asserting page text (\"results contain 5003_D13\") needs the retry just
        as much as one asserting an element, and gating it on DOM-kind assertions left TC_006 without it.
        """
        self._last_action_effect_note = ''
        if (
            last_action.get('action') not in {'click', 'select'}
            or step_index in self._swallowed_action_retries
            or self._control_toggles_state(last_action, self._last_actionable_controls)
        ):
            return
        if await self._action_had_visible_effect(page) is not False or await self._click_target_moved(page, last_action):
            return
        self._swallowed_action_retries.add(step_index)
        await self._emit(step_callback, {'type': 'log', 'content': f'[planner_v2] Step {step_index}: action produced no visible change; repeating it once.\n'})
        methods = ['same_target']
        try:
            await self._execute_step(page, last_action, timeout_error=TimeoutError)
        except Exception as error:
            logger.info('planner_v2 swallowed-action retry failed: %s', error)
        await page.wait_for_timeout(1500)
        if await self._action_had_visible_effect(page) is False:
            if await self._click_inner_activator(page, str(last_action.get('selector') or '')):
                methods.append('inner_activator')
                await page.wait_for_timeout(1500)
        if await self._action_had_visible_effect(page) is False:
            self._last_action_effect_note = (
                'The completed action produced no visible change on the page, so the intended transition did not happen; '
                'choose a different target (for example the item thumbnail or link) instead of asserting.'
            )
        logger.info('planner_v2 step %s swallowed-action retry methods=%s recovered=%s',
                    step_index, methods, not self._last_action_effect_note)
        if history is not None:
            history.artifacts.append({
                'type': 'swallowed_action_retry',
                'step': step_index,
                'action': self._audit_action_payload(last_action, step),
                'methods': methods,
                'effect_after_retry': not self._last_action_effect_note,
            })

    async def _recover_by_rebinding(self, page, step, step_index, actions, step_callback, history, artifact_dir):
        """Before asking the model to act again, give the completed action's state a chance to settle and rebind.

        Many unverified outcomes are not wrong actions but evidence captured too early (a form still
        rendering, a thumbnail not yet loaded) or bindings the model failed to produce. Re-running the
        settle wait, the deterministic binders and the evaluation is cheap and avoids a needless replan.
        """
        if not actions or not isinstance(actions[-1], dict) or actions[-1].get('action') == 'assert':
            return None
        dom_kinds = {'element_state', 'popup', 'field_value', 'collection', 'absence'}
        required = [
            assertion
            for assertion in step.get('assertions') or []
            if isinstance(assertion, dict) and assertion.get('required', True) is not False
        ]
        if not required or any(assertion.get('assert_kind') not in dom_kinds for assertion in required):
            return None
        last_action = actions[-1]
        await self._wait_for_assertion_observation(page, step)
        await self._bind_required_assertions_after_action(page, step, step_index, actions, step_callback, history)
        # Applying bindings replaces the step's assertion dicts, so re-read them instead of the pre-binding list.
        required = [
            assertion
            for assertion in step.get('assertions') or []
            if isinstance(assertion, dict) and assertion.get('required', True) is not False
        ]
        if not required or any(not str((assertion.get('target') or {}).get('locator') or '').strip() for assertion in required):
            return None
        await self._emit(step_callback, {'type': 'log', 'content': f'[planner_v2] Step {step_index}: re-evaluating evidence after settle/rebind.\n'})
        screenshot_path = await self._capture_screenshot(page, artifact_dir, self._step_screenshot_filename(step_index, suffix='_rebind'))
        persisted_attempt = await self._persist_step_attempt(
            step_index, step, actions[-1], 'completed', '', None, screenshot_path, page, None, [], [],
        )
        statuses = persisted_attempt.get('assertion_statuses', []) if persisted_attempt else []
        required_statuses = self._required_assertion_statuses(step, statuses)
        if not self._step_assertions_are_verified(step, required_statuses):
            return None
        if history is not None:
            history.artifacts.append({'type': 'rebind_recovery', 'step': step_index, 'statuses': required_statuses})
        return 'completed', '', actions[-1].get('action') if actions else '', actions, persisted_attempt, screenshot_path

    async def _clear_vanished_assertion_bindings(self, page, step, step_index):
        """Drop bound locators that no longer point at usable evidence so the step can rebind."""
        stale_indexes = []
        for assertion_index, assertion in enumerate(step.get('assertions') or [], start=1):
            if not isinstance(assertion, dict) or assertion.get('assert_kind') not in {'field_value', 'popup', 'element_state', 'collection'}:
                continue
            operator = assertion.get('operator')
            if operator in {'not_exists', 'not_contains'}:
                continue
            target = assertion.get('target') or {}
            locator = str(target.get('locator') or '').strip()
            if not locator:
                continue
            expected_value = (assertion.get('expected') or {}).get('value') if isinstance(assertion.get('expected'), dict) else None
            try:
                handle = page.locator(locator)
                if await handle.count() == 0:
                    if assertion.get('assert_kind') == 'collection' and operator == 'equals' and str(expected_value) == '0':
                        continue  # an empty collection is exactly what this contract expects
                    stale_indexes.append(assertion_index)
                elif (
                    operator == 'exists'
                    and assertion.get('assert_kind') in {'popup', 'element_state'}
                    and not await handle.first.is_visible()
                ):
                    # Portal-level structural selectors drift when sibling layers appear or close;
                    # an invisible target is no longer evidence for an existence assertion.
                    stale_indexes.append(assertion_index)
            except Exception:
                continue
        if not stale_indexes:
            return
        from apps.ai_testing.execution.plan_persistence import _semantic_target_intent

        for assertion_index in stale_indexes:
            assertion = step['assertions'][assertion_index - 1]
            target = assertion.get('target')
            unbound_target = dict(target) if isinstance(target, dict) else {}
            unbound_target.pop('locator', None)
            unbound_target['intent'] = _semantic_target_intent(unbound_target)
            assertion['target'] = unbound_target
        from apps.ai_testing.execution.plan_persistence import persist_unbound_step

        await sync_to_async(persist_unbound_step)(self.execution_record_id, step_index, stale_indexes)

    def _persisted_step_action_history(self, step_index):
        from apps.ai_testing.models import AIExecutionStepAttempt

        if self.execution_record_id is None:
            return []
        attempts = AIExecutionStepAttempt.objects.filter(
            step__plan_revision__execution_record_id=self.execution_record_id,
            step__display_order=step_index,
        ).order_by(
            'step__plan_revision__revision_number',
            'attempt_number',
            'id',
        )
        history = []
        for attempt in attempts:
            if not isinstance(attempt.action, dict):
                continue
            history.append({**attempt.action, 'status': attempt.status, 'error': str(attempt.error_message or '')[:200]})
        return history

    def _step_time_budget_seconds(self):
        settings = getattr(self.environment_configuration, 'runtime_settings', {}) or {}
        browser = settings.get('ai_testing_browser', {}) if isinstance(settings, dict) else {}
        try:
            return max(60, min(3600, int(browser.get('step_time_budget_seconds', 600))))
        except (TypeError, ValueError):
            return 600

    def _step_budget_exhausted(self):
        return self._step_deadline is not None and time.monotonic() >= self._step_deadline

    @staticmethod
    def _action_signature(actions):
        return json.dumps(
            [
                {key: action.get(key) for key in ('action', 'selector', 'value', 'param', 'url', 'role', 'accessible_name')}
                for action in actions or []
                if isinstance(action, dict)
            ],
            ensure_ascii=True,
            sort_keys=True,
            default=str,
        )

    def _assertion_replan_limit(self):
        settings = getattr(self.environment_configuration, 'runtime_settings', {}) or {}
        browser = settings.get('ai_testing_browser', {}) if isinstance(settings, dict) else {}
        try:
            return max(1, min(12, int(browser.get('assertion_replan_limit', 8))))
        except (TypeError, ValueError):
            return 8

    async def _capture_media_state(self, page):
        try:
            from apps.ai_testing.execution.browser_observers import NATIVE_MEDIA_OBSERVER

            return await NATIVE_MEDIA_OBSERVER.capture_state(page)
        except Exception as error:
            logger.warning('planner_v2 failed to capture media evidence: %s', error)
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

    @staticmethod
    def _normalize_existence_expectations(assertions):
        """Give every existence assertion the same expected value before binders look at it.

        parse_assertion normalises this when a plan is generated and again when it is evaluated, but binders
        read the plan as it was stored. A plan written before that normalisation can still carry
        ``expected.value: ""``, which expects_true() reads as False, so the binders that gate on it decline
        and the step can only end inconclusive. Healing on load keeps those stored plans usable.
        """
        healed = []
        for assertion in assertions or []:
            if (
                isinstance(assertion, dict)
                and assertion.get('assert_kind') in {'element_state', 'popup'}
                and assertion.get('operator') in {'exists', 'not_exists'}
                and isinstance(assertion.get('expected'), dict)
                and assertion['expected'].get('value') is not True
            ):
                assertion = {**assertion, 'expected': {**assertion['expected'], 'value': True}}
            healed.append(assertion)
        return healed

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
            'assertions': self._normalize_existence_expectations(raw_step.get('assertions') or []),
            'transition': raw_step.get('transition'),
            'verification_required': raw_step.get('verification_required', True) is not False,
            'selector': selector,
            'role': raw_step.get('role'),
            'accessible_name': raw_step.get('accessible_name'),
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
            'correlates_resource': raw_step.get('correlates_resource'),
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
        image_assertions = self._image_assertions(step)
        if image_assertions and not any(
            isinstance(action, dict) and action.get('status') == 'completed' for action in step.get('_prior_actions') or []
        ):
            # A verify-only step ("locate camera X and check its thumbnail") plans straight from the current page;
            # give lazily loaded thumbnails the same chance to render that post-action binding gets.
            await self._wait_for_rendered_visual_content(page, step, image_assertions)
        from apps.ai_testing.execution.mcp_tools import (
            BrowserMCPToolAdapter,
            MCPInProcessClient,
            MCPInProcessTransport,
            MCPJsonRpcDispatcher,
        )
        from apps.ai_testing.global_planner import VisualStepReplanner

        mcp_client = self._mcp_client
        if mcp_client is None:
            browser_tools = BrowserMCPToolAdapter(
                step.get('allowed_capabilities') or [],
                observation_handler=lambda: self._collect_planner_observation(page, step),
            )
            mcp_client = MCPInProcessClient(MCPInProcessTransport(MCPJsonRpcDispatcher(browser_tools)))
        self._active_planning_step = step
        try:
            tool_result = await mcp_client.call_tool('browser.observe', {})
            actions = await VisualStepReplanner().create_actions(
                step['description'],
                tool_result['structuredContent'],
            )
        finally:
            self._active_planning_step = None
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

    @staticmethod
    def _planner_control_baseline(actionable_controls):
        """The trimmed control list kept as the pre-action baseline for binders and effect detection."""
        return [
            {key: control.get(key) for key in PLANNER_CONTROL_KEYS}
            for control in (actionable_controls or [])[:300]
            if isinstance(control, dict)
        ]

    async def _collect_planner_observation(self, page, step):
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

        from apps.ai_testing.execution.blocking_state import build_blocking_state
        from apps.ai_testing.execution.page_observation import capture_accessibility_snapshot

        actionable_controls = await self._build_actionable_controls(page)
        prior_actions = step.get('_prior_actions') or []
        hover_state = bool(prior_actions) and str((prior_actions[-1] or {}).get('action') or '') == 'hover'
        if not hover_state:  # probing would move the mouse and close a hover-revealed menu
            await self._enrich_icon_control_names(page, actionable_controls)
        self._last_actionable_controls = self._planner_control_baseline(actionable_controls)
        observable_elements = self._dedupe_observable_elements(
            actionable_controls,
            await self._build_observable_elements(page),
        )
        accessibility_snapshot = await capture_accessibility_snapshot(page)
        self._last_accessibility_snapshot = accessibility_snapshot
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
                    })).filter(item => item.selector && item.remaining > 1 && item.client_height * 0.8 >= 2).sort((left, right) => right.remaining - left.remaining).slice(0, 20);
                    return { scroll_y: window.scrollY, scroll_height: document.documentElement.scrollHeight, viewport_height: window.innerHeight, scroll_containers: scrollContainers };
                }"""
            )
        except Exception:
            page_metrics = {}
        return {
            'url': current_url,
            'title': page_title,
            'visible_text': normalized_text,
            'actionable_controls': actionable_controls,
            'blocking_state': build_blocking_state(actionable_controls),
            'observable_elements': observable_elements,
            'accessibility_snapshot': accessibility_snapshot,
            'page_metrics': page_metrics,
            'allowed_capabilities': step.get('allowed_capabilities') or [],
            'assertions': step.get('assertions') or [],
            'transition': step.get('transition'),
            'correlates_resource': step.get('correlates_resource') or '',
            'execution_resources': self._execution_resources,
            'prior_actions': step.get('_prior_actions') or [],
            'verified_predecessors': step.get('_verified_predecessors') or [],
            'error': step.get('_planner_failure', ''),
            'screenshot': await self._capture_inline_screenshot_data(page),
        }

    @staticmethod
    def _rect_inside(inner, outer, tolerance: int = 2) -> bool:
        if not isinstance(inner, dict) or not isinstance(outer, dict):
            return False
        try:
            ix, iy, iw, ih = (float(inner.get(key) or 0) for key in ('x', 'y', 'width', 'height'))
            ox, oy, ow, oh = (float(outer.get(key) or 0) for key in ('x', 'y', 'width', 'height'))
        except (TypeError, ValueError):
            return False
        return iw > 0 and ih > 0 and ix >= ox - tolerance and iy >= oy - tolerance and ix + iw <= ox + ow + tolerance and iy + ih <= oy + oh + tolerance

    def _step_targets_configured_camera(self, step) -> bool:
        camera_names = default_device_camera_names(self._execution_resources)
        description = f"{step.get('description') or ''} {step.get('intent') or ''}"
        return bool(camera_names) and refers_to_target_device(description, camera_names)

    async def _target_camera_card_rects(self, page, step) -> list[dict]:
        """Rects of visible controls named after the environment's target camera, for steps about that camera."""
        camera_names = default_device_camera_names(self._execution_resources)
        names = [name.casefold() for name in camera_names]
        description = f"{step.get('description') or ''} {step.get('intent') or ''}"
        if not names or not refers_to_target_device(description, camera_names):
            if not names:
                logger.info('planner_v2 target camera rects: no environment device cameras among %s resources', len(self._execution_resources))
            return []
        rects = []
        controls = await self._build_actionable_controls(page)
        for control in controls:
            if not isinstance(control, dict) or not isinstance(control.get('rect'), dict) or is_text_input(control):
                continue
            shown = ' '.join(str(control.get('name') or '').split()).casefold()
            if any(name in shown for name in names) and int(control['rect'].get('width') or 0) >= 60:
                rects.append(control['rect'])
        logger.info('planner_v2 target camera rects: cameras=%s controls=%s matched=%s', camera_names, len(controls), len(rects))
        return rects

    def _seed_environment_resources(self) -> None:
        """Publish the environment's configured test devices as execution-scoped resources for the planner."""
        existing = {
            str(resource.get('resource_id') or '')
            for resource in self._execution_resources
            if isinstance(resource, dict) and resource.get('resource_type') == 'environment_device'
        }
        for resource in environment_device_resources(self.environment_configuration):
            if str(resource.get('resource_id') or '') not in existing:
                self._execution_resources.append(resource)

    async def _click_target_moved(self, page, action: dict) -> bool:
        """True when the clicked selector now resolves elsewhere (or nowhere) than the element that was clicked.

        Value-based selectors such as ``[title="Close"]`` match a menu option first and the control that
        displays the chosen value afterwards; repeating such a click would toggle the menu again.
        """
        selector = str(action.get('selector') or '').strip()
        if not selector or not isinstance(self._last_click_box, dict):
            return False
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                return True
            box = await locator.bounding_box()
        except Exception as error:
            logger.info('planner_v2 click target probe failed for %s: %s', selector, error)
            return False
        if not isinstance(box, dict):
            return True
        return any(round(float(box.get(key) or 0)) != round(float(self._last_click_box.get(key) or 0)) for key in ('x', 'y', 'width', 'height'))

    async def _enrich_icon_control_names(self, page, controls):
        """Name icon-only toolbar buttons from their hover tooltips.

        A player toolbar is a row of unnamed svg buttons; without names the planner picks one by DOM index
        and regularly lands on the neighbour ("Create Case" instead of "Download"). Hovering reveals the
        tooltip, which is the very word the step description uses. Probing is bounded, skipped while a
        blocking layer is open, and cached per page path and button position.
        """
        if not isinstance(controls, list):
            return
        if any(isinstance(control, dict) and control.get('blocking_layer') is True for control in controls):
            return
        unnamed = []
        for control in controls:
            if not isinstance(control, dict) or control.get('tag') != 'button' or str(control.get('name') or '').strip():
                continue
            rect = control.get('rect') if isinstance(control.get('rect'), dict) else {}
            selector = str(control.get('selector') or '').strip()
            width, height = int(rect.get('width') or 0), int(rect.get('height') or 0)
            if selector and ' > ' in selector and 16 <= width <= 96 and 16 <= height <= 96:
                unnamed.append(control)
        groups: dict[str, list[dict]] = {}
        for control in unnamed:
            groups.setdefault(control['selector'].rsplit(' > ', 1)[0], []).append(control)
        candidates = [control for group in groups.values() if len(group) >= 3 for control in group][:ICON_TOOLTIP_PROBE_LIMIT]
        if not candidates:
            return
        cache = self._tooltip_name_cache.setdefault(urlsplit(str(page.url or '')).path, {})

        def key_for(control):
            rect = control['rect']
            return (control['selector'], int(rect.get('x') or 0) // 8, int(rect.get('y') or 0) // 8)

        pending = [control for control in candidates if key_for(control) not in cache]
        if pending:
            try:
                previous = set((await page.evaluate(TOOLTIP_PROBE_JS, ''))['texts'])
            except Exception as error:
                logger.info('planner_v2 tooltip probe unavailable: %s', error)
                return
            for control in pending:
                rect = control['rect']
                name = ''
                try:
                    await page.mouse.move(rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2)
                    await page.wait_for_timeout(ICON_TOOLTIP_HOVER_MS)
                    probe = await page.evaluate(TOOLTIP_PROBE_JS, control['selector'])
                    texts = [str(text) for text in (probe.get('texts') or [])]
                    fresh = [text for text in texts if text not in previous]
                    name = str(probe.get('described') or '').strip() or (fresh[0] if len(fresh) == 1 else '')
                    previous = set(texts)
                except Exception as error:
                    logger.info('planner_v2 tooltip probe failed for %s: %s', control['selector'], error)
                cache[key_for(control)] = name
            try:
                await page.mouse.move(1, 1)  # leave the toolbar so the last tooltip closes before the screenshot
                await page.wait_for_timeout(150)
            except Exception:
                pass
        named = 0
        for control in candidates:
            name = cache.get(key_for(control), '')
            if name:
                control['name'] = name
                control['name_source'] = 'tooltip'
                named += 1
        if named:
            logger.info('planner_v2 named %s icon button(s) from tooltips on %s', named, urlsplit(str(page.url or '')).path)

    @staticmethod
    def _dedupe_observable_elements(actionable_controls, observable_elements):
        """Remove observables that are the same node as an actionable control (rect and text match)."""
        control_keys = set()
        for control in actionable_controls or []:
            if not isinstance(control, dict) or not isinstance(control.get('rect'), dict):
                continue
            rect = control['rect']
            control_keys.add((
                tuple(int(rect.get(key) or 0) for key in ('x', 'y', 'width', 'height')),
                str(control.get('name') or '').strip(),
            ))
        deduped = []
        for element in observable_elements or []:
            if isinstance(element, dict) and isinstance(element.get('rect'), dict):
                rect = element['rect']
                key = (
                    tuple(int(rect.get(key) or 0) for key in ('x', 'y', 'width', 'height')),
                    str(element.get('text') or '').strip(),
                )
                if key in control_keys and not element.get('group_selector'):
                    continue
            deduped.append(element)
        return deduped

    async def _build_actionable_controls(self, page):
        try:
            controls = await page.locator('body *').evaluate_all(
                """
                elements => elements.filter(element => {
                    const style = getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    const disabledAncestor = element.closest('[aria-disabled="true"], [disabled], [inert]');
                    const nativeControl = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName);
                    const interactiveRole = ['button', 'link', 'option', 'menuitem', 'row'].includes(element.getAttribute('role'));
                    const frameworkListener = Object.getOwnPropertySymbols(element).some(symbol => {
                        const value = element[symbol];
                        return String(symbol.description || '').includes('_vei') && value && typeof value === 'object' && Object.keys(value).length > 0;
                    }) || (element._vei && typeof element._vei === 'object' && Object.keys(element._vei).length > 0) || Object.getOwnPropertyNames(element).some(property => {
                        const value = element[property];
                        return property.startsWith('__reactProps') && value && typeof value === 'object' && Object.keys(value).some(key => /^on[A-Z]/.test(key));
                    });
                    const directSvg = Array.from(element.children).some(child => child.tagName === 'svg');
                    const compactIconControl = directSvg && rect.width >= 16 && rect.height >= 16 && rect.width <= 80 && rect.height <= 80;
                    const interactive = nativeControl || interactiveRole || element.hasAttribute('tabindex') || element.hasAttribute('onclick') || frameworkListener || style.cursor === 'pointer' || compactIconControl;
                    const hitTarget = document.elementFromPoint(
                        rect.left + rect.width / 2,
                        rect.top + rect.height / 2,
                    );
                    return interactive && !disabledAncestor && style.pointerEvents !== 'none' && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0 && (hitTarget === element || element.contains(hitTarget));
                }).filter(element => {
                    const rect = element.getBoundingClientRect();
                    const containsInteractive = Array.from(element.querySelectorAll('*')).some(child => {
                        const childStyle = getComputedStyle(child);
                        const childFrameworkListener = Object.getOwnPropertySymbols(child).some(symbol => String(symbol.description || '').includes('_vei')) || (child._vei && typeof child._vei === 'object' && Object.keys(child._vei).length > 0) || Object.getOwnPropertyNames(child).some(property => property.startsWith('__reactProps'));
                        return ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(child.tagName) || ['button', 'link', 'option', 'menuitem', 'row'].includes(child.getAttribute('role')) || child.hasAttribute('onclick') || childFrameworkListener || childStyle.cursor === 'pointer';
                    });
                    const nativeControl = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName);
                    const viewportRatio = (rect.width * rect.height) / Math.max(1, window.innerWidth * window.innerHeight);
                    return nativeControl || !containsInteractive || viewportRatio < 0.25;
                }).map((element, index) => {
                    const title = element.getAttribute('title');
                    const href = element.getAttribute('href');
                    const semanticChild = element.querySelector('[aria-label], [title], [alt], [data-icon], [data-lucide], svg title, svg, use');
                    const semanticUse = element.querySelector('svg use, use');
                    const semanticReference = semanticUse ? (
                        semanticUse.getAttribute('href')
                        || semanticUse.getAttribute('xlink:href')
                        || ''
                    ) : '';
                    const semanticClass = semanticChild && typeof semanticChild.getAttribute('class') === 'string'
                        ? semanticChild.getAttribute('class').split(/\\s+/).find(token => /icon$/i.test(token)) || ''
                        : '';
                    const semanticName = semanticChild ? (
                        semanticChild.getAttribute('aria-label')
                        || semanticChild.getAttribute('title')
                        || semanticChild.getAttribute('alt')
                        || semanticChild.getAttribute('data-icon')
                        || semanticChild.getAttribute('data-lucide')
                        || semanticReference
                        || semanticChild.textContent
                        || semanticChild.getAttribute('href')
                        || semanticChild.getAttribute('xlink:href')
                        || semanticClass
                        || ''
                    ) : '';
                    const name = (element.getAttribute('aria-label') || title || element.innerText || element.value || href || semanticName || '').trim().slice(0, 120);
                    const uniqueId = element.id && document.querySelectorAll(`#${CSS.escape(element.id)}`).length === 1;
                    const attributeSelector = (attribute, value) => `[${attribute}=${JSON.stringify(value)}]`;
                    const structuralSelector = (target = element) => {
                        const uniqueAnchor = (node) => {
                            if (node.id && document.querySelectorAll(`#${CSS.escape(node.id)}`).length === 1) return `#${CSS.escape(node.id)}`;
                            const testId = node.getAttribute('data-testid');
                            if (testId && document.querySelectorAll(`[data-testid=${JSON.stringify(testId)}]`).length === 1) return `[data-testid=${JSON.stringify(testId)}]`;
                            if (node.parentElement === document.body) {
                                const classes = typeof node.className === 'string' ? node.className.split(/\\s+/).filter(Boolean) : [];
                                if (classes.length) {
                                    const candidate = `body > ${node.tagName.toLowerCase()}${classes.map(token => `.${CSS.escape(token)}`).join('')}`;
                                    if (document.querySelectorAll(candidate).length === 1) return candidate;
                                }
                            }
                            return '';
                        };
                        const parts = [];
                        let current = target;
                        while (current && current !== document.body) {
                            const anchor = uniqueAnchor(current);
                            if (anchor) {
                                const anchored = parts.length ? `${anchor} > ${parts.join(' > ')}` : anchor;
                                if (document.querySelectorAll(anchored).length === 1) return anchored;
                            }
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
                    let url = '';
                    if (href) {
                        try { url = new URL(href, document.baseURI).href; } catch (error) { url = href; }
                    }
                    const rect = element.getBoundingClientRect();
                    const depth = (() => { let value = 0; let current = element; while (current && current !== document.body) { value += 1; current = current.parentElement; } return value; })();
                    const nativeControl = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName);
                    const containerText = (element.parentElement?.innerText || '').trim().slice(0, 240);
                    const className = typeof element.className === 'string' ? element.className.trim() : '';
                    const sameTagSiblings = element.parentElement ? Array.from(element.parentElement.children).filter(sibling => sibling.tagName === element.tagName) : [];
                    const classSiblings = className ? sameTagSiblings.filter(sibling => sibling.className === element.className) : [];
                    const grouped = classSiblings.length >= 1 ? classSiblings : (sameTagSiblings.length > 1 ? sameTagSiblings : []);
                    const parentSelector = element.parentElement ? structuralSelector(element.parentElement) : '';
                    const groupClass = classSiblings.length >= 1 && className ? className.split(/\\s+/).filter(Boolean).map(token => `.${CSS.escape(token)}`).join('') : '';
                    const groupSelector = grouped.length >= 1 && parentSelector
                        ? `${parentSelector} > ${element.tagName.toLowerCase()}${groupClass}`
                        : '';
                    const hasRenderedVisual = element.tagName === 'IMG'
                        ? (element.naturalWidth > 1 && element.naturalHeight > 1)
                        : (getComputedStyle(element).backgroundImage !== 'none' || Array.from(element.querySelectorAll('img, canvas, video')).some(candidate => (
                            candidate instanceof HTMLImageElement ? (candidate.naturalWidth > 1 && candidate.naturalHeight > 1)
                                : candidate instanceof HTMLCanvasElement ? (candidate.width > 1 && candidate.height > 1)
                                : (candidate.readyState >= 2 && candidate.videoWidth > 1)
                        )));
                    const dialog = element.closest('[role="dialog"], dialog, [aria-modal="true"]');
                    const positioned = (() => { let current = element; while (current && current !== document.body) { const style = getComputedStyle(current); const zIndex = Number.parseInt(style.zIndex, 10) || 0; if (['fixed', 'sticky'].includes(style.position) || zIndex > 0) return current; current = current.parentElement; } return null; })();
                    const positionedRect = positioned?.getBoundingClientRect();
                    const positionedRatio = positionedRect ? (positionedRect.width * positionedRect.height) / Math.max(1, window.innerWidth * window.innerHeight) : 0;
                    const zIndex = Number.parseInt(getComputedStyle(dialog || positioned || element).zIndex, 10) || 0;
                    const topLayer = Boolean(dialog || positioned || zIndex > 0);
                    const blockingLayer = Boolean(dialog || (positioned && getComputedStyle(positioned).position === 'fixed' && positionedRatio >= 0.3));
                    const blockingLayerId = blockingLayer ? structuralSelector(dialog || positioned) : '';
                    const inputType = String(element.getAttribute('type') || '').toLowerCase();
                    const implicitRole = element.tagName === 'BUTTON' ? 'button'
                        : element.tagName === 'A' && href ? 'link'
                        : element.tagName === 'SELECT' ? 'combobox'
                        : element.tagName === 'TEXTAREA' ? 'textbox'
                        : element.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes(inputType) ? 'button'
                        : element.tagName === 'INPUT' && inputType === 'checkbox' ? 'checkbox'
                        : element.tagName === 'INPUT' && inputType === 'radio' ? 'radio'
                        : element.tagName === 'INPUT' ? 'textbox' : '';
                    return { index, tag: element.tagName.toLowerCase(), role: element.getAttribute('role') || implicitRole, name, selector, group_selector: groupSelector, url, described_by: element.getAttribute('aria-describedby') || '', native_control: nativeControl, editable: !element.hasAttribute('readonly') && !element.hasAttribute('disabled'), depth, container_text: containerText, group_size: grouped.length, group_ordinal: grouped.indexOf(element), has_visual_content: hasRenderedVisual, top_layer: topLayer, blocking_layer: blockingLayer, blocking_layer_id: blockingLayerId, dialog_layer: Boolean(dialog), z_index: zIndex, rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) } };
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
            for control in controls:
                described_by = str(control.pop('described_by', '') or '').strip()
                if control.get('name') or not described_by or not control.get('selector'):
                    continue
                try:
                    tooltip_name = await page.evaluate(
                        "tooltipId => document.getElementById(tooltipId)?.innerText?.trim() || ''",
                        described_by,
                    )
                except Exception:
                    tooltip_name = ''
                if tooltip_name:
                    control['name'] = str(tooltip_name)[:120]
            return controls
        except Exception:
            return []

    async def _build_observable_elements(self, page):
        try:
            elements = await page.locator('body *').evaluate_all(
                """
                elements => elements.filter(element => {
                    const style = getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    const text = (element.getAttribute('aria-label') || element.getAttribute('title') || element.getAttribute('alt') || element.innerText || element.value || '').trim();
                    const ratio = (rect.width * rect.height) / Math.max(1, window.innerWidth * window.innerHeight);
                    const ownVisual = (element instanceof HTMLImageElement && element.naturalWidth > 1 && element.naturalHeight > 1)
                        || (element instanceof HTMLCanvasElement && element.width > 1 && element.height > 1)
                        || (element instanceof HTMLVideoElement && element.readyState >= 2 && element.videoWidth > 1)
                        || (style.backgroundImage !== 'none' && rect.width >= 24 && rect.height >= 24);
                    return element.parentElement !== document.body && (text || ownVisual) && text.length <= 240 && ratio < 0.25 && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                }).map((element, order) => {
                    const rect = element.getBoundingClientRect();
                    const offscreen = (rect.y + rect.height <= 0 || rect.y >= window.innerHeight || rect.x + rect.width <= 0 || rect.x >= window.innerWidth) ? 1 : 0;
                    return { element, order, offscreen };
                }).sort((left, right) => left.offscreen - right.offscreen || left.order - right.order).slice(0, 200).map(({ element }, index) => {
                    const structuralSelector = (target = element) => {
                        const uniqueAnchor = (node) => {
                            if (node.id && document.querySelectorAll(`#${CSS.escape(node.id)}`).length === 1) return `#${CSS.escape(node.id)}`;
                            const testId = node.getAttribute('data-testid');
                            if (testId && document.querySelectorAll(`[data-testid=${JSON.stringify(testId)}]`).length === 1) return `[data-testid=${JSON.stringify(testId)}]`;
                            if (node.parentElement === document.body) {
                                const classes = typeof node.className === 'string' ? node.className.split(/\\s+/).filter(Boolean) : [];
                                if (classes.length) {
                                    const candidate = `body > ${node.tagName.toLowerCase()}${classes.map(token => `.${CSS.escape(token)}`).join('')}`;
                                    if (document.querySelectorAll(candidate).length === 1) return candidate;
                                }
                            }
                            return '';
                        };
                        const parts = [];
                        let current = target;
                        while (current && current !== document.body) {
                            const anchor = uniqueAnchor(current);
                            if (anchor) {
                                const anchored = parts.length ? `${anchor} > ${parts.join(' > ')}` : anchor;
                                if (document.querySelectorAll(anchored).length === 1) return anchored;
                            }
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
                    const text = (element.getAttribute('aria-label') || element.getAttribute('title') || element.getAttribute('alt') || element.innerText || element.value || '').trim().slice(0, 240);
                    const rect = element.getBoundingClientRect();
                    const className = typeof element.className === 'string' ? element.className.trim() : '';
                    const sameTagSiblings = element.parentElement ? Array.from(element.parentElement.children).filter(sibling => sibling.tagName === element.tagName) : [];
                    const classSiblings = className ? sameTagSiblings.filter(sibling => sibling.className === element.className) : [];
                    const grouped = classSiblings.length >= 1 ? classSiblings : (sameTagSiblings.length > 1 ? sameTagSiblings : []);
                    const parentSelector = structuralSelector(element.parentElement);
                    const groupClass = classSiblings.length >= 1 && className ? className.split(/\\s+/).filter(Boolean).map(token => `.${CSS.escape(token)}`).join('') : '';
                    const groupSelector = grouped.length >= 1 && parentSelector
                        ? `${parentSelector} > ${element.tagName.toLowerCase()}${groupClass}`
                        : '';
                    const visualElements = [element, ...element.querySelectorAll('img, canvas, video, [style]')];
                    const hasVisualContent = visualElements.some(candidate => {
                        if (candidate instanceof HTMLImageElement) return candidate.naturalWidth > 1 && candidate.naturalHeight > 1;
                        if (candidate instanceof HTMLCanvasElement) return candidate.width > 1 && candidate.height > 1;
                        if (candidate instanceof HTMLVideoElement) return candidate.readyState >= 2 && candidate.videoWidth > 1 && candidate.videoHeight > 1;
                        return getComputedStyle(candidate).backgroundImage !== 'none';
                    });
                    return { index, tag: element.tagName.toLowerCase(), text, selector: structuralSelector(), group_selector: groupSelector, group_size: grouped.length, group_ordinal: grouped.indexOf(element), has_visual_content: hasVisualContent, rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) } };
                }).filter(element => element.selector);
                """
            )
            # Discovery reports whether an element has rendered image content but never screenshots
            # elements: per-element screenshots cost seconds each (and scroll the page), which turned
            # observation of media-heavy pages into a multi-minute stall. The pixel-level signal is
            # measured only at evidence time for the one element an assertion is bound to.
            for element in elements:
                if element.get('has_visual_content'):
                    element['visual_signal'] = None
            return elements
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
            has_accessible_locator = bool(
                str(action.get('role') or '').strip()
                and str(action.get('accessible_name') or '').strip()
            )
            if name in {'click', 'double_click', 'right_click', 'hover', 'fill', 'press', 'select'} and not (
                str(action.get('selector') or '').strip() or has_accessible_locator
            ):
                raise ValueError(f'Planner action {index} {name} requires selector or role and accessible_name')
            if name == 'navigate' and not action.get('url'):
                raise ValueError(f'Planner action {index} navigate requires url')
            if name in {'fill', 'press', 'select'} and not action.get('value'):
                raise ValueError(f'Planner action {index} {name} requires value')
            if allowed_capabilities is not None:
                validate_browser_action(name, allowed_capabilities)

    def _attach_runtime_observers(self, page):
        self._recent_network_events = []
        self._recent_download_events = []
        self._download_event_baseline = 0

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
            except Exception:
                logger.debug('planner_v2 failed to record runtime response', exc_info=True)

        page.on('response', on_response)

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

    async def _recover_control_by_observed_geometry(self, page, selector):
        """Re-find a control whose structural selector drifted (auto-hiding toolbars, re-indexed siblings).

        The planner chose the selector from an observation that also recorded the control's geometry.
        Hovering that spot re-reveals auto-hidden controls; if the selector still fails, the element now
        occupying the same spot is used when it is a genuine control.
        """
        observed = next(
            (
                control
                for control in self._last_actionable_controls
                if isinstance(control, dict) and str(control.get('selector') or '').strip() == selector
            ),
            None,
        )
        rect = observed.get('rect') if isinstance(observed, dict) and isinstance(observed.get('rect'), dict) else None
        if not rect or int(rect.get('width') or 0) <= 0 or int(rect.get('height') or 0) <= 0:
            return None
        center_x = int(rect['x']) + int(rect['width']) / 2
        center_y = int(rect['y']) + int(rect['height']) / 2
        try:
            await page.mouse.move(center_x, center_y)
            await page.wait_for_timeout(400)
            revealed = await self._resolve_locator(page, selector)
            if revealed is not None:
                self._runtime_events.append({'type': 'selector_recovery', 'selector': selector, 'method': 'hover_reveal'})
                return revealed
        except Exception as error:
            logger.info('planner_v2 geometry recovery hover failed: %s', error)
            return None
        try:
            probe = await page.evaluate(
                """([x, y]) => {
                    const element = document.elementFromPoint(x, y);
                    if (!element) return null;
                    const control = element.closest('button, a, [role="button"], [role="menuitem"], [role="tab"], [role="option"], input, select, [onclick], [tabindex]');
                    if (!control) return null;
                    const rect = control.getBoundingClientRect();
                    return { tag: control.tagName.toLowerCase(), x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, name: (control.getAttribute('aria-label') || control.getAttribute('title') || control.innerText || '').trim().slice(0, 80) };
                }""",
                [center_x, center_y],
            )
        except Exception as error:
            logger.info('planner_v2 geometry recovery probe failed: %s', error)
            return None
        if not probe:
            return None
        self._runtime_events.append({
            'type': 'selector_recovery',
            'selector': selector,
            'method': 'element_at_observed_position',
            'resolved_tag': probe.get('tag'),
            'resolved_name': probe.get('name'),
        })
        return _PointClickTarget(page, float(probe['x']), float(probe['y']))

    async def _resolve_step_locator(self, page, step):
        role = str(step.get('role') or '').strip()
        accessible_name = str(step.get('accessible_name') or '').strip()
        if role or accessible_name:
            if not role or not accessible_name:
                raise ValueError('Accessibility locator requires both role and accessible_name.')
            locator = page.get_by_role(role, name=accessible_name, exact=True)
            visible_matches = []
            for index in range(await locator.count()):
                candidate = locator.nth(index) if hasattr(locator, 'nth') else locator.first
                if await candidate.is_visible():
                    visible_matches.append(candidate)
            if len(visible_matches) != 1:
                raise ValueError(
                    f'Accessibility locator role={role!r}, name={accessible_name!r} matched '
                    f'{len(visible_matches)} visible elements.'
                )
            return visible_matches[0]
        return await self._resolve_locator(page, step.get('selector'))

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
            locator = await self._resolve_step_locator(page, step)
            point = self._parse_point(loc) or self._parse_point(param)
            if locator is None and point is None and selector:
                locator = await self._recover_control_by_observed_geometry(page, selector)
            if locator is not None:
                self._last_click_box = None
                bounding_box = getattr(locator, 'bounding_box', None)
                if callable(bounding_box):
                    try:
                        box = await bounding_box()
                        self._last_click_box = box if isinstance(box, dict) else None
                    except Exception:
                        self._last_click_box = None
                await locator.click(timeout=timeout_ms)
            elif point is not None:
                await page.mouse.click(point[0], point[1])
            elif selector:
                raise ValueError(f'click selector did not resolve on the current page: {selector}')
            else:
                raise ValueError('click step requires selector or loc')
            return

        if action in {'double_click'}:
            locator = await self._resolve_step_locator(page, step)
            point = self._parse_point(loc) or self._parse_point(param)
            if locator is not None:
                await locator.dblclick(timeout=timeout_ms)
            elif point is not None:
                await page.mouse.dblclick(point[0], point[1])
            else:
                raise ValueError('double_click step requires selector or loc')
            return

        if action in {'right_click'}:
            locator = await self._resolve_step_locator(page, step)
            point = self._parse_point(loc) or self._parse_point(param)
            if locator is not None:
                await locator.click(timeout=timeout_ms, button='right')
            elif point is not None:
                await page.mouse.click(point[0], point[1], button='right')
            else:
                raise ValueError('right_click step requires selector or loc')
            return

        if action in {'hover'}:
            locator = await self._resolve_step_locator(page, step)
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
            locator = await self._resolve_step_locator(page, step)
            point = self._parse_point(loc)
            if locator is not None:
                await locator.fill(value, timeout=timeout_ms)
                await self._repair_fill_if_mismatched(locator, value, timeout_ms)
            elif point is not None:
                await page.mouse.click(point[0], point[1])
                await page.keyboard.type(value)
            else:
                raise ValueError('type/fill step requires selector or loc')
            return

        if action in {'press', 'keyboard_press', 'key', 'hotkey'}:
            value = str(step.get('value') or param or '').strip()
            locator = await self._resolve_step_locator(page, step)
            if not value:
                raise ValueError('press step requires value')
            if locator is not None:
                await locator.press(value, timeout=timeout_ms)
            else:
                await page.keyboard.press(value)
            return

        if action in {'select', 'select_option'}:
            value = str(step.get('value') or '').strip()
            if not value:
                raise ValueError('select step requires value')
            locator = await self._resolve_step_locator(page, step)
            if locator is None:
                raise ValueError('select step requires a resolvable element locator')
            await locator.select_option(value, timeout=timeout_ms)
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
                                    const match = String(raw).match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
                                    if (!match) return null;
                                    return [Number(match[1]), Number(match[2]), Number(match[3])];
                                };

                                const pickColor = (el) => {
                                    if (!el) return null;
                                    const c = window.getComputedStyle(el).backgroundColor;
                                    const rgb = parseRgb(c);
                                    if (!rgb) return null;
                                    const [r, g, b] = rgb;
                                    const isTransparent = r === 0 && g === 0 && b === 0 && /rgba\\(0,\\s*0,\\s*0,\\s*0\\)/i.test(String(c));
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

    @staticmethod
    def _fill_matches(expected: str, observed: object) -> bool:
        """Compare a typed value with what the input actually holds, tolerating display masks."""
        expected_text = str(expected or '').strip()
        observed_text = str(observed or '')
        if not expected_text:
            return True
        expected_digits = ''.join(ch for ch in expected_text if ch.isdigit())
        phone_like = len(expected_digits) >= 7 and all(ch.isdigit() or ch in '+ -()' for ch in expected_text)
        if phone_like:
            return ''.join(ch for ch in observed_text if ch.isdigit()) == expected_digits

        def normalize(text: str) -> str:
            return ' '.join(text.split()).casefold()

        return normalize(expected_text) in normalize(observed_text)

    async def _repair_fill_if_mismatched(self, locator, value: str, timeout_ms: int) -> None:
        """Masked or controlled inputs may re-format a programmatic fill; re-type through the keyboard when it did not land."""
        if not value:
            return
        try:
            observed = await locator.input_value(timeout=2000)
        except Exception:
            return
        if self._fill_matches(value, observed):
            return
        logger.info('planner_v2 fill mismatch expected=%r observed=%r; retyping through keyboard', value, observed)
        event = {
            'type': 'fill_repair',
            'expected': self._audit_value(value, None),
            'observed_before': self._audit_value(observed, None),
        }
        try:
            await locator.click(timeout=timeout_ms)
            await locator.press('Control+A')
            await locator.press('Backspace')
            residual = str(await locator.input_value(timeout=2000) or '').strip()
            to_type = value
            if residual and value.startswith(residual):
                # The field keeps a fixed prefix (e.g. a country code); do not type it twice.
                to_type = value[len(residual):].strip()
            await locator.press_sequentially(to_type, delay=25, timeout=timeout_ms)
            observed = await locator.input_value(timeout=2000)
        except Exception as error:
            logger.info('planner_v2 fill repair failed: %s', error)
            self._runtime_events.append({**event, 'result': 'error', 'error': f'{type(error).__name__}: {error}'})
            return
        matched = self._fill_matches(value, observed)
        self._runtime_events.append({**event, 'observed_after': self._audit_value(observed, None), 'result': 'repaired' if matched else 'mismatch'})
        if not matched:
            logger.info('planner_v2 fill still mismatched after keyboard retype: expected=%r observed=%r', value, observed)

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
            raise EnvironmentBootstrapError('planner_v2 bootstrap could not find login form')

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
                    await self._capture_bootstrap_debug(
                        page,
                        step_callback,
                        f'login_attempt_{login_attempt}_failed',
                    )
                    if login_attempt < 3:
                        logger.warning('planner_v2 bootstrap login attempt %s/3 did not reach dashboard', login_attempt)
                        await page.goto(login.login_url, wait_until='commit', timeout=60000)
                        await self._wait_login_page_ready(page, timeout_ms=30000)
            if last_login_error is not None:
                raise EnvironmentBootstrapError(f'planner_v2 bootstrap login did not reach dashboard: {last_login_error}') from last_login_error

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
