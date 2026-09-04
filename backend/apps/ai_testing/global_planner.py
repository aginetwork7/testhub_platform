from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import re
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections


PLAN_SUBMISSION_TOOL = {
    'type': 'function',
    'function': {
        'name': 'submit_execution_plan',
        'description': 'Submit the complete execution plan for server validation.',
        'parameters': {
            'type': 'object',
            'properties': {'steps': {'type': 'array', 'minItems': 1, 'items': {'type': 'object', 'properties': {
                'executor': {'type': 'string', 'description': 'browser, data_factory, or device_cli'},
                'description': {'type': 'string'},
                'step_mode': {'type': 'string'},
                'verification_required': {'type': 'boolean'},
                'allowed_capabilities': {'type': 'array', 'items': {'type': 'string'}},
                'assertions': {'type': 'array', 'items': {'type': 'object'}},
                'action': {'type': 'string', 'description': 'For data_factory this must be exactly create.'}, 'resource_type': {'type': 'string'},
                'arguments': {'type': 'object'}, 'device_id': {'type': 'string'}, 'command': {'type': 'string'},
            }, 'required': ['executor', 'description']}}},
            'required': ['steps'],
        },
    },
}
ACTION_SUBMISSION_TOOL = {
    'type': 'function',
    'function': {
        'name': 'submit_browser_actions',
        'description': 'Submit browser actions for server validation and execution.',
        'parameters': {
            'type': 'object',
            'properties': {
                'actions': {'type': 'array', 'minItems': 1, 'maxItems': 1, 'items': {'type': 'object', 'properties': {
                    'action': {'type': 'string'}, 'description': {'type': 'string'},
                    'selector': {'type': 'string'}, 'url': {'type': 'string'},
                    'value': {'type': 'string'}, 'param': {'type': 'string'},
                    'assert_kind': {'type': 'string'}, 'target': {'type': 'object'},
                    'operator': {'type': 'string'}, 'expected': {'type': 'object'},
                }, 'required': ['action']}},
                'assertion_bindings': {'type': 'array', 'minItems': 1, 'items': {'type': 'object', 'properties': {
                    'assertion_index': {'type': 'integer'}, 'locator': {'type': 'string'},
                    'selection_basis': {'type': 'string'},
                }, 'required': ['assertion_index', 'locator']}},
            },
            'required': ['actions'],
        },
    },
}


class GlobalPlanError(ValueError):
    """Raised when a global test plan cannot be generated or validated."""


class VisualStepReplanner:
    """Planner-side visual replanning from executor evidence."""

    async def create_actions(self, step_description: str, evidence: dict[str, Any]) -> list[dict[str, Any]]:
        config = await self._get_active_model_config()
        if config is None:
            raise GlobalPlanError('未配置可用的 Planner Vision 模型。')

        from apps.requirement_analysis.models import AIModelService

        visible_text = str(evidence.get('visible_text') or '')[:600]
        actionable_controls = evidence.get('actionable_controls') or []
        observable_elements = (evidence.get('observable_elements') or [])[:80]
        allowed_capabilities = evidence.get('allowed_capabilities') or []
        assertions = evidence.get('assertions') or []
        execution_resources = evidence.get('execution_resources') or []
        require_assertion_bindings = evidence.get('require_assertion_bindings') is True
        from apps.ai_testing.execution.capabilities import allowed_browser_actions

        permitted_actions = allowed_browser_actions(allowed_capabilities)
        messages: list[dict[str, Any]] = [
            {
                'role': 'system',
                'content': (
                    'Call submit_browser_actions exactly once with exactly one action. No prose. '
                    f'Actions allowed for this step: {", ".join(permitted_actions)}. '
                    'Use only locators discovered from the current page evidence. '
                    'For click-like actions, choose only a selector from the actionable controls list. '
                    'For a navigation step, prefer clicking a named current actionable link. Never invent a route or scroll an unrelated content container to search for navigation. Use action="navigate" only with the exact resolved url supplied by a current actionable control. '
                    'When a step description identifies a control by its currently displayed value, do not choose a query or filter control whose name contains only the field label. Choose a detail-context control whose own name or container_text contains that current value; if it is not present, reveal more of the detail panel first. '
                    'For assertion bindings, choose a locator from actionable controls or observable elements. '
                    'Generate only actions permitted by the allowed capabilities supplied in the page evidence. '
                    'Choose actions that can produce the supplied assertion evidence; do not treat an action as proof. '
                    'When prior_actions shows a completed state-changing action but the required assertion remains unverified, do not repeat the same action and selector. Choose a distinct next control from the current evidence; when the current layer exposes an explicit commit or confirm control, use it to commit the pending selection before asserting the final state. '
                    'If a current actionable control or observable element objectively contains the assertion expected value and represents its semantic target, return action="assert" with that locator binding immediately; do not continue unrelated interactions after the required state is already visible. '
                    'For collection assertions, expected numeric values are count thresholds rather than visible text. When a visible option group or container semantically matches the assertion target intent, return action="assert" and bind that group or container locator immediately. '
                    'Use page_metrics to detect off-screen content. When the required field or control is absent from current evidence and scroll_y + viewport_height is less than scroll_height, scroll to reveal more content before operating any unrelated control. '
                    'When page_metrics.scroll_containers contains a container with remaining scroll range, return action="scroll" with that discovered selector and value="down" to reveal controls inside the panel. '
                    'When prior_actions already contains a scroll for a container that still has remaining scroll range, continue scrolling that container instead of guessing an unnamed icon control. Stop scrolling only when a blocking layer must be handled or a named current control or observable element directly represents the required target or expected value. '
                    'After each state-changing action the page will be observed again. Return action="assert" with complete assertion_bindings only when the current page already shows the required final state; otherwise omit assertion_bindings. '
                    'If actionable controls include blocking_layer=true, operate one of those blocking controls before interacting with background controls. '
                    'When an execution-scoped resource provides result_correlation, use it only for the transition that selects the visible result record; otherwise do not infer record ordering. '
                    'During record selection, score repeated record controls by how many non-empty result_correlation.match_values occur in each control container_text and select the unique highest-scoring record. When match_values are present, never fall back to first_visible. Only when match_values are absent and correlation explicitly permits first_visible may you select group_ordinal=0. After a detail view is visible, operate controls in that detail context and never reselect the result record for a later step. '
                    'During record selection, do not assert or click a partial match when no current control contains every result_correlation.match_values entry. Continue searching by scrolling a discovered record-list container with remaining range; assert only after the selected-record state is visible. '
                    'Every click, double_click, right_click, hover, fill, press, and select action must include a non-empty selector string. '
                    'Every fill, press, and select action must include a non-empty value. '
                    'Use fill only when the selected actionable control has editable=true; use click, press, or select for readonly controls. '
                    'Never use coordinates, fixed application selectors, page names, business keywords, or preset workflows. '
                    'Every assertion uses action="assert" with a registered assert_kind and is supported by current-run evidence.'
                    'Bind only field_value, popup, element_state, and collection assertions. Each assertion_bindings locator must be discovered from current page evidence and reference its 1-based assertion_index. URL, text, media, resource, and network assertions use their own evidence and must not receive locator bindings. '
                ),
            },
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': (
                            f'Step: {step_description}\n'
                            f'URL: {evidence.get("url", "")}\n'
                            f'Failure: {str(evidence.get("error", ""))[:300]}\n'
                            f'Prior actions: {json.dumps(evidence.get("prior_actions", []), ensure_ascii=True)}\n'
                            f'Page metrics: {json.dumps(evidence.get("page_metrics", {}), ensure_ascii=True)}\n'
                            f'Visible text:\n{visible_text}'
                            f'\nActionable controls:\n{json.dumps(actionable_controls, ensure_ascii=True)}'
                            f'\nObservable elements:\n{json.dumps(observable_elements, ensure_ascii=True)}'
                            f'\nAllowed capabilities:\n{json.dumps(allowed_capabilities, ensure_ascii=True)}'
                            f'\nAllowed actions:\n{json.dumps(permitted_actions, ensure_ascii=True)}'
                            f'\nAssertions to verify:\n{json.dumps(assertions, ensure_ascii=True)}'
                            f'\nExecution-scoped resources:\n{json.dumps(execution_resources, ensure_ascii=True)}'
                            f'\nRequire complete assertion bindings: {json.dumps(require_assertion_bindings)}'
                        ),
                    },
                ],
            },
        ]
        screenshot = evidence.get('screenshot')
        if screenshot:
            messages[1]['content'].append({'type': 'image_url', 'image_url': {'url': screenshot}})

        response = await asyncio.wait_for(
            AIModelService.call_openai_compatible_api(
                config,
                messages,
                max_tokens=max(config.max_tokens, 8192),
                enable_thinking=True,
                tools=[_action_submission_tool(len(assertions), require_assertion_bindings)],
                tool_choice={'type': 'function', 'function': {'name': 'submit_browser_actions'}},
            ),
            timeout=settings.TIMEOUTS_AI_REQUEST,
        )
        try:
            payload = _response_payload(response, 'submit_browser_actions')
            actions = payload.get('actions') if isinstance(payload, dict) else None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise GlobalPlanError('Planner Vision 未返回有效 JSON 动作计划。') from error
        if not isinstance(actions, list) or not actions or not all(isinstance(item, dict) for item in actions):
            raise GlobalPlanError(
                f'Planner Vision 动作计划为空或格式无效：{json.dumps(payload, ensure_ascii=True)[:1200]}。'
            )
        bindings = payload.get('assertion_bindings', [])
        if not isinstance(bindings, list) or not all(isinstance(item, dict) for item in bindings):
            raise GlobalPlanError('Planner Vision assertion_bindings 格式无效。')
        bindings = [
            {
                **binding,
                'assertion_index': int(binding['assertion_index'])
                if isinstance(binding.get('assertion_index'), str) and binding['assertion_index'].isdigit()
                else binding.get('assertion_index'),
            }
            for binding in bindings
        ]
        assertion_check = len(actions) == 1 and str(actions[0].get('action') or '') == 'assert'
        if not assertion_check:
            bindings = []
            for action in actions:
                action.pop('assertion_bindings', None)
        bindable_indexes = {
            index
            for index, assertion in enumerate(assertions, start=1)
            if assertion.get('assert_kind') in {'field_value', 'popup', 'element_state', 'collection'}
        }
        raw_indexes = [binding.get('assertion_index') for binding in bindings]
        if bindable_indexes and set(raw_indexes) == {index - 1 for index in bindable_indexes}:
            bindings = [{**binding, 'assertion_index': binding['assertion_index'] + 1} for binding in bindings]
        for binding in bindings:
            assertion_index = binding.get('assertion_index')
            locator = str(binding.get('locator') or '').strip()
            if not isinstance(assertion_index, int) or assertion_index < 1 or assertion_index > len(assertions) or not locator:
                raise GlobalPlanError(
                    f'Planner Vision assertion binding 无效：{json.dumps(binding, ensure_ascii=True)}。'
                )
            discovered_locators = {
                str(control.get('selector') or '')
                for control in [*actionable_controls, *observable_elements]
                if isinstance(control, dict)
            }
            if locator not in discovered_locators:
                raise GlobalPlanError('Planner Vision assertion binding locator was not discovered on the current page.')
        self._validate_offscreen_search_action(
            actions,
            evidence.get('page_metrics') or {},
            actionable_controls,
            evidence.get('prior_actions') or [],
            step_description,
        )
        self._validate_discovered_navigation(actions, actionable_controls)
        self._validate_visible_record_correlation(
            actions,
            actionable_controls,
            evidence.get('execution_resources') or [],
            step_description,
            evidence.get('page_metrics') or {},
        )
        self._validate_non_repeating_action(
            actions,
            evidence.get('prior_actions') or [],
            actionable_controls,
        )
        self._validate_blocking_layer_action(actions, actionable_controls, bindings)
        if assertion_check and {binding['assertion_index'] for binding in bindings} != bindable_indexes:
            raise GlobalPlanError(
                'Planner Vision returned assert without complete locator bindings. If the required state is not currently visible, return one state-changing action using a current actionable selector instead of assert. If it is visible, return assert with every required DOM binding. '
                f'Bindings: {json.dumps(bindings, ensure_ascii=True)}.'
            )
        if bindings:
            actions[0]['assertion_bindings'] = bindings
        return actions

    @staticmethod
    def _validate_offscreen_search_action(
        actions: list[dict[str, Any]],
        page_metrics: dict[str, Any],
        actionable_controls: list[dict[str, Any]],
        prior_actions: list[dict[str, Any]],
        step_description: str = '',
    ) -> None:
        scroll_containers = page_metrics.get('scroll_containers')
        if not isinstance(scroll_containers, list) or not any(
            isinstance(container, dict) and float(container.get('remaining') or 0) > 1
            for container in scroll_containers
        ):
            return
        if any(
            isinstance(control, dict) and control.get('blocking_layer') is True
            for control in actionable_controls
        ):
            return
        action = actions[0] if len(actions) == 1 else {}
        action_name = str(action.get('action') or '').strip()
        if action_name == 'scroll' and re.search(r'\bnavigat(?:e|ion)\b', step_description, flags=re.IGNORECASE):
            if any(
                isinstance(control, dict) and str(control.get('url') or '').strip()
                for control in actionable_controls
            ):
                raise GlobalPlanError(
                    'Planner Vision navigation step must use a discovered actionable link instead of scrolling an unrelated content container.'
                )
        if action_name == 'wait':
            raise GlobalPlanError('Planner Vision must scroll a discovered container instead of waiting while off-screen content remains.')
        prior_scrolled = any(
            isinstance(prior_action, dict) and str(prior_action.get('action') or '').strip() == 'scroll'
            for prior_action in prior_actions
        )
        if prior_scrolled or action_name not in {'click', 'double_click', 'right_click'}:
            return
        selector = str(action.get('selector') or '').strip()
        selected_control = next(
            (
                control
                for control in actionable_controls
                if isinstance(control, dict) and str(control.get('selector') or '').strip() == selector
            ),
            None,
        )
        if selected_control is not None and not str(selected_control.get('name') or '').strip():
            raise GlobalPlanError('Planner Vision must scroll a discovered container before guessing an unnamed control while off-screen content remains.')

    @staticmethod
    def _validate_non_repeating_action(
        actions: list[dict[str, Any]],
        prior_actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]] | None = None,
    ) -> None:
        action = actions[0] if len(actions) == 1 else {}
        action_name = str(action.get('action') or '').strip()
        selector = str(action.get('selector') or '').strip()
        if action_name not in {'click', 'double_click', 'right_click', 'hover', 'fill', 'press', 'select'} or not selector:
            return
        previous_action = prior_actions[-1] if prior_actions and isinstance(prior_actions[-1], dict) else {}
        immediate_repeat = (
            str(previous_action.get('action') or '').strip() == action_name
            and str(previous_action.get('selector') or '').strip() == selector
        )
        repeated_earlier = any(
            isinstance(prior_action, dict)
            and str(prior_action.get('action') or '').strip() == action_name
            and str(prior_action.get('selector') or '').strip() == selector
            for prior_action in prior_actions
        )
        selected_control = next(
            (
                control
                for control in actionable_controls or []
                if isinstance(control, dict) and str(control.get('selector') or '').strip() == selector
            ),
            None,
        )
        reusable_transaction_control = bool(
            selected_control is not None and selected_control.get('blocking_layer') is True
        )
        if immediate_repeat or (repeated_earlier and not reusable_transaction_control):
            raise GlobalPlanError(
                'Planner Vision must not repeat a failed non-blocking state-changing selector; choose a distinct control. A blocking transaction control may be reused only after an intervening state change.'
            )

    @staticmethod
    def _validate_discovered_navigation(
        actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
    ) -> None:
        action = actions[0] if len(actions) == 1 else {}
        if str(action.get('action') or '').strip() != 'navigate':
            return
        target_url = str(action.get('url') or '').strip()
        discovered_urls = {
            str(control.get('url') or '').strip()
            for control in actionable_controls
            if isinstance(control, dict) and str(control.get('url') or '').strip()
        }
        if not target_url or target_url not in discovered_urls:
            raise GlobalPlanError(
                'Planner Vision navigate URL was not discovered from a current actionable link. Click a discovered link or use its exact resolved URL.'
            )

    @staticmethod
    def _validate_visible_record_correlation(
        actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
        execution_resources: list[dict[str, Any]],
        step_description: str,
        page_metrics: dict[str, Any] | None = None,
    ) -> None:
        original_intent = str(step_description or '').splitlines()[0].strip()
        if re.search(r'\bnavigat(?:e|ion)\b', original_intent, flags=re.IGNORECASE):
            return
        if not re.search(r'\b(?:open|select)\b', original_intent, flags=re.IGNORECASE):
            return
        match_values: list[str] = []
        for resource in execution_resources:
            if not isinstance(resource, dict):
                continue
            payload = resource.get('resource') if isinstance(resource.get('resource'), dict) else resource
            correlation = payload.get('result_correlation') if isinstance(payload, dict) else None
            values = correlation.get('match_values') if isinstance(correlation, dict) else None
            if isinstance(values, list):
                match_values.extend(str(value).strip().casefold() for value in values if str(value).strip())
        if not match_values:
            return
        scored_controls: list[tuple[int, str]] = []
        for control in actionable_controls:
            if not isinstance(control, dict):
                continue
            if str(control.get('tag') or '').casefold() in {'input', 'textarea', 'select'} or control.get('editable') is True:
                continue
            selector = str(control.get('selector') or '').strip()
            text = f"{control.get('name', '')} {control.get('container_text', '')}".casefold()
            score = sum(value in text for value in match_values)
            if selector and score > 0:
                scored_controls.append((score, selector))
        max_score = max((score for score, _ in scored_controls), default=0)
        required_score = len(set(match_values))
        if max_score < required_score:
            scroll_containers = (page_metrics or {}).get('scroll_containers') or []
            searchable_containers = [
                container
                for container in scroll_containers
                if isinstance(container, dict)
                and str(container.get('selector') or '').strip()
                and float(container.get('remaining') or 0) > 1
            ]
            if searchable_containers:
                target = max(searchable_containers, key=lambda container: float(container.get('remaining') or 0))
                actions[0] = {'action': 'scroll', 'selector': str(target['selector']), 'value': 'down'}
                return
            raise GlobalPlanError(
                'Planner Vision cannot select or assert an uncorrelated or partially correlated record; no current control contains every result correlation value.'
            )
        best_selectors = {selector for score, selector in scored_controls if score == max_score}
        if len(best_selectors) != 1:
            return
        best_selector = next(iter(best_selectors))
        action = actions[0] if len(actions) == 1 else {}
        action_name = str(action.get('action') or '').strip()
        if action_name not in {'click', 'double_click', 'right_click'} or str(action.get('selector') or '').strip() != best_selector:
            actions[0] = {
                'action': 'click',
                'selector': best_selector,
            }

    @staticmethod
    def _validate_blocking_layer_action(
        actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
        bindings: list[dict[str, Any]] | None = None,
    ) -> None:
        blocking_locators = {
            str(control.get('selector') or '')
            for control in actionable_controls
            if isinstance(control, dict) and control.get('blocking_layer') is True
        }
        if not blocking_locators:
            return
        if (
            len(actions) == 1
            and str(actions[0].get('action') or '').strip() == 'assert'
            and bindings
            and all(str(binding.get('locator') or '').strip() in blocking_locators for binding in bindings)
        ):
            return
        for action in actions:
            action_name = str(action.get('action') or '').strip()
            locator = str(action.get('selector') or '').strip()
            if action_name not in {'click', 'double_click', 'right_click', 'hover', 'fill', 'press', 'select'} or locator not in blocking_locators:
                raise GlobalPlanError('Planner Vision must resolve the current blocking dialog before operating background controls.')

    async def assess_playback_advance(self, before_screenshot: str, after_screenshot: str) -> dict[str, Any]:
        config = await self._get_active_model_config()
        if config is None:
            raise GlobalPlanError('未配置可用的 Planner Vision 模型。')

        from apps.requirement_analysis.models import AIModelService

        messages = [
            {
                'role': 'system',
                'content': (
                    'Compare two playback screenshots. Read the burned-in HH:MM:SS timestamps. '
                    'Return only JSON: {"before_time":"HH:MM:SS","after_time":"HH:MM:SS",'
                    '"advanced_seconds":number,"confidence":number}. No prose.'
                ),
            },
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'First image is before clicking 10s Forward; second image is after.'},
                    {'type': 'image_url', 'image_url': {'url': before_screenshot}},
                    {'type': 'image_url', 'image_url': {'url': after_screenshot}},
                ],
            },
        ]
        response = await AIModelService.call_openai_compatible_api(
            config,
            messages,
            max_tokens=config.max_tokens,
            response_format={'type': 'json_object'},
        )
        try:
            payload = json.loads(str(response['choices'][0]['message']['content'] or ''))
            seconds = float(payload['advanced_seconds'])
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise GlobalPlanError('Planner Vision 未返回有效的 Playback 时间证据。') from error
        return {**payload, 'advanced_seconds': seconds}

    @staticmethod
    def _load_active_model_config():
        close_old_connections()
        from apps.ai_testing.models import AITestModelConfig

        return AITestModelConfig.objects.filter(role='planner_vision', is_active=True).first()

    async def _get_active_model_config(self):
        return await sync_to_async(self._load_active_model_config)()


class GlobalTestPlanner:
    """Builds a typed cross-executor plan from one natural-language test goal."""

    async def create_plan(
        self,
        task_description: str,
        environment_configuration_id: int | None,
        use_cache: bool = False,
    ) -> list[dict[str, Any]]:
        if use_cache:
            cached_steps = await sync_to_async(self._load_cached_plan_steps)(
                task_description,
                environment_configuration_id,
            )
            if cached_steps:
                cached_response = {
                    'choices': [{'message': {'tool_calls': [{'function': {
                        'name': 'submit_execution_plan',
                        'arguments': json.dumps({'steps': cached_steps}, ensure_ascii=True),
                    }}]}}],
                }
                try:
                    return self.normalize_response(
                        cached_response,
                        environment_configuration_id,
                        task_description,
                    )
                except GlobalPlanError:
                    pass

        configs = await self._get_active_model_configs()
        if not configs:
            raise GlobalPlanError('未配置可用的 Planner 模型。')

        from apps.requirement_analysis.models import AIModelService

        prompt_content = await sync_to_async(self._load_active_prompt_content)('planner_text')
        if not prompt_content:
            raise GlobalPlanError('未配置可用的 Planner 文本提示词。')
        resources = await sync_to_async(self._load_data_factory_resources)(environment_configuration_id)
        messages = self._build_messages(task_description, environment_configuration_id, prompt_content, resources)
        last_error: GlobalPlanError | None = None
        for config in configs:
            retry_messages = list(messages)
            for attempt in range(5):
                try:
                    response = await asyncio.wait_for(
                        AIModelService.call_openai_compatible_api(
                            config,
                            retry_messages,
                            max_tokens=4096,
                            enable_thinking=True,
                            tools=[PLAN_SUBMISSION_TOOL],
                            tool_choice={'type': 'function', 'function': {'name': 'submit_execution_plan'}},
                        ),
                        timeout=settings.TIMEOUTS_AI_REQUEST,
                    )
                except TimeoutError as error:
                    last_error = GlobalPlanError(
                        f'Planner 模型 {config.name} 在第 {attempt + 1} 次请求时超时。'
                    )
                    continue
                except Exception as error:
                    raise GlobalPlanError(
                        f'Planner 模型 {config.name} 请求失败：{type(error).__name__}。'
                    ) from error
                try:
                    return self.normalize_response(response, environment_configuration_id, task_description)
                except GlobalPlanError as error:
                    last_error = error
                    retry_messages.append({
                        'role': 'user',
                        'content': (
                            f'Your previous plan violated this contract: {error}. '
                            'Correct that specific violation and call submit_execution_plan again with the complete non-empty steps array. '
                            'Rebuild the full ordered plan rather than appending a repair step. Move every required field-edit transaction, including its commit and verification, before any irreversible final-status transaction, and remove any duplicate or post-status field steps.'
                        ),
                    })
        raise GlobalPlanError(f'Planner 未生成有效计划：{last_error or "未知原因"}') from last_error

    @staticmethod
    def _build_messages(
        task_description: str,
        configuration_id: int | None,
        prompt_content: str,
        data_factory_resources: list[dict[str, object]] | None = None,
    ) -> list[dict[str, Any]]:
        device_context = (
            '设备 CLI 环境已配置，可以输出 device_cli 步骤。'
            if configuration_id is not None
            else '没有设备 CLI 环境配置；不要输出 device_cli 步骤。'
        )
        return [
            {
                'role': 'system',
                'content': (
                    f'{prompt_content}\n\n'
                    'You are a test planner. Call submit_execution_plan exactly once with an ordered steps array. '
                    'Each step must have executor and description. '
                    'executor can only be browser, data_factory, or device_cli. '
                    'For browser, output step_mode="ai", a concrete description, and a non-empty allowed_capabilities array. Final-state steps require non-empty assertions. Intermediate menu/dialog steps may use verification_required=false and an empty assertions array; they pass only when their action succeeds and must be followed by a verifying step. '
                    'Each browser step must perform exactly one user-visible state transition and assert only its immediate resulting state. Split navigation, record selection, status changes, modal choices, confirmations, and subsequent page verification into separate ordered steps. '
                    'For a state change that opens menus or dialogs and requires additional choices or confirmation, plan every intermediate transition: open the control and assert its options, select the requested option and assert the next dialog, make required dialog selections and assert them, then confirm and only then assert the committed final state. Never assert the final state before the commit action. '
                    'When the goal requires both updating a field and reaching a final status, plan and verify the field update before the irreversible status transition. Do not assume a status transition will expose a field dialog; only handle such a dialog during visual replanning when current page evidence proves it exists. '
                    'Never create conditional steps such as "if a dialog appears" because execution plans do not have conditional branches. Plan only states required by the goal; assertion-driven replanning will handle a blocking dialog when current page evidence proves it exists. '
                    'Browser allowed_capabilities may contain only browser.navigate, browser.inspect, browser.act, and browser.capture. '
                    'Configured environment authentication is completed by the runtime before the plan begins; do not output login steps or login assertions. '
                    'Every fill, press, and select action must include a non-empty value. '
                    'Use fill only when the selected actionable control has editable=true; use click, press, or select for readonly controls. '
                    'Every assertion must use action="assert" and include assert_kind, target, operator, '
                    'expected, and evidence_requirements. Use only registered generic kinds: text, field_value, '
                    'popup, media, video, visual_change, stream_state, playback, element_state, url, network, '
                    'api_resource, command_result, collection, absence. '
                    'Use element_state or collection for static UI elements such as images, thumbnails, cards, and controls. element_state supports objective visibility through exists/not_exists and visible text through equals/contains/matches; never assert inferred CSS states such as selected, active, highlighted, or focused. After selecting a record, assert an objectively observable detail element, dialog, text, or URL introduced by that transition. '
                    'Collection assertions compare the observed element count: use exists/not_exists or a numeric expected.value with equals/greater_than/less_than; never use contains or descriptive count text. '
                    'For page-bound element_state, collection, and popup assertions, use target.intent for the semantic target; the Visual Planner will bind a runtime locator after observing the page. '
                    'Use media or video only for native audio/video elements with objective media_state evidence. '
                    'For stream_state and playback, expected must include numeric minimum_advanced_seconds; do not use descriptive expected.value strings. '
                    'For visual_change, expected must use boolean value and visual_frame_before plus visual_frame_after evidence. '
                    'For device_cli, output device_id and optionally command. '
                    'For data_factory, use only resource_type and arguments declared in the environment-authorized resources. '
                    'Every data_factory step must use executor="data_factory" and action="create" exactly; never emit adapter or business-tool names as actions. '
                    'Every data_factory create step must declare allowed_capabilities exactly as ["data_factory.create"]. '
                    'Copy device_id exactly from the user goal. Never use an internal environment ID, '
                    'never infer a device ID, and never substitute a short numeric value. '
                    'Device commands must be non-interactive and report a nonzero exit code when the '
                    'expected condition is absent. '
                    'Do not output credentials, connection commands, shell commands that alter users, '
                    'firewalls, disks, SSH keys, or device power state. '
                    'Keep the plan minimal and preserve dependencies between device and browser work. '
                    f'{device_context}'
                ),
            },
            {
                'role': 'user',
                'content': (
                    f'{str(task_description or "").strip()}\n\n'
                    f'Environment-authorized data_factory resources:\n{json.dumps(data_factory_resources or [], ensure_ascii=True)}'
                ),
            },
        ]

    @staticmethod
    def normalize_response(
        response: dict[str, Any],
        configuration_id: int | None,
        task_description: str = '',
    ) -> list[dict[str, Any]]:
        try:
            payload = GlobalTestPlanner._parse_plan_payload(
                json.dumps(_response_payload(response, 'submit_execution_plan'))
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise GlobalPlanError('Planner 未返回有效 JSON 计划。') from error

        steps = payload.get('steps') if isinstance(payload, dict) else None
        if not isinstance(steps, list) or not steps or len(steps) > 50:
            raise GlobalPlanError('Planner 计划必须包含 1 到 50 个步骤。')

        normalized_steps: list[dict[str, Any]] = []
        for index, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, dict):
                raise GlobalPlanError(f'Planner 步骤 {index} 不是对象。')
            executor = str(raw_step.get('executor', '')).strip()
            description = str(raw_step.get('description', '')).strip()
            if executor == 'browser':
                if not description:
                    raise GlobalPlanError(f'Planner 浏览器步骤 {index} 缺少 description。')
                if re.search(r'\bif\b', description, flags=re.IGNORECASE):
                    raise GlobalPlanError(
                        f'Browser step {index} contains a conditional branch. Remove the word "if" and the optional step; plan only an unconditional state required by the goal.'
                    )
                allowed_capabilities = GlobalTestPlanner._normalize_capabilities(
                    raw_step.get('allowed_capabilities'),
                    index,
                )
                verification_required = raw_step.get('verification_required', True) is not False
                assertions = GlobalTestPlanner._normalize_assertions(raw_step.get('assertions'), index) if verification_required else []
                if GlobalTestPlanner._asserts_field_dialog_after_status_selection(description, assertions):
                    raise GlobalPlanError(
                        f'Planner 浏览器步骤 {index} 假设状态选择后才出现字段对话框；必须先设置并验证字段，再执行最终状态转换。'
                    )
                normalized_steps.append({
                    'executor': 'browser',
                    'step_mode': 'ai',
                    'description': description,
                    'allowed_capabilities': allowed_capabilities,
                    'assertions': assertions,
                    'verification_required': verification_required,
                })
                continue
            if executor == 'data_factory':
                if configuration_id is None:
                    raise GlobalPlanError('计划包含 data_factory 步骤，但用例未选择设备 CLI 环境。')
                action = str(raw_step.get('action', '')).strip()
                if action == 'create':
                    resource_type = str(raw_step.get('resource_type', '')).strip()
                    arguments = raw_step.get('arguments')
                    capabilities = raw_step.get('allowed_capabilities')
                    if not resource_type or not isinstance(arguments, dict):
                        raise GlobalPlanError(f'Planner 数据工厂步骤 {index} 缺少 resource_type 或 arguments。')
                    if capabilities != ['data_factory.create']:
                        raise GlobalPlanError(f'Planner 数据工厂步骤 {index} 必须声明 data_factory.create。')
                    normalized_steps.append({
                        'executor': 'data_factory',
                        'action': 'create',
                        'resource_type': resource_type,
                        'arguments': arguments,
                        'allowed_capabilities': capabilities,
                        'description': description or f'创建资源 {resource_type}',
                        'assertions': [{
                            'action': 'assert',
                            'assert_kind': 'api_resource',
                            'target': {'resource_type': resource_type},
                            'operator': 'exists',
                            'expected': {'value': True},
                            'evidence_requirements': ['api_response'],
                            'required': True,
                        }],
                    })
                    continue
                raise GlobalPlanError(f'Planner 数据工厂步骤 {index} 只支持 action="create"。')
            if executor != 'device_cli':
                raise GlobalPlanError(f'Planner 步骤 {index} 使用了不支持的执行器：{executor}')
            if configuration_id is None:
                raise GlobalPlanError('计划包含 device_cli 步骤，但用例未选择设备 CLI 环境。')
            device_id = str(raw_step.get('device_id', '')).strip()
            if not device_id:
                raise GlobalPlanError(f'Planner 设备步骤 {index} 缺少 device_id。')
            if not GlobalTestPlanner._device_id_is_from_goal(device_id, task_description):
                raise GlobalPlanError(f'Planner 设备步骤 {index} 的 device_id 未在原始需求中明确出现。')
            step = {
                'executor': 'device_cli',
                'description': description or f'连接设备 {device_id} 并执行设备命令',
                'device_id': device_id,
            }
            command = raw_step.get('command')
            if command is not None and str(command).strip():
                step['command'] = str(command).strip()
            normalized_steps.append(step)
        if normalized_steps and normalized_steps[-1].get('verification_required') is False:
            raise GlobalPlanError('Planner 最后一个步骤必须验证最终状态。')
        GlobalTestPlanner._validate_status_control_preconditions(normalized_steps)
        GlobalTestPlanner._validate_field_updates_before_status_selection(normalized_steps)
        GlobalTestPlanner._demote_superseded_precondition_assertions(normalized_steps)
        return normalized_steps

    @staticmethod
    def _demote_superseded_precondition_assertions(steps: list[dict[str, Any]]) -> None:
        ignored_tokens = {
            'control', 'current', 'dialog', 'field', 'indicator', 'list', 'options',
            'page', 'record', 'showing', 'value',
        }

        def semantic_tokens(assertion: dict[str, Any]) -> set[str]:
            target = assertion.get('target') or {}
            if not isinstance(target, dict):
                return set()
            semantic_text = ' '.join(str(target.get(key) or '') for key in ('intent', 'field'))
            return {
                token
                for token in re.findall(r'[a-z0-9]+', semantic_text.casefold())
                if len(token) >= 3 and token not in ignored_tokens
            }

        final_targets = [
            (index, semantic_tokens(assertion))
            for index, step in enumerate(steps)
            for assertion in step.get('assertions', [])
            if assertion.get('assert_kind') == 'field_value' and assertion.get('required', True) is not False
        ]
        for index, step in enumerate(steps):
            for assertion in step.get('assertions', []):
                if assertion.get('assert_kind') not in {'popup', 'element_state'} or assertion.get('operator') != 'exists':
                    continue
                tokens = semantic_tokens(assertion)
                if any(future_index > index and len(tokens.intersection(future_tokens)) >= 2 for future_index, future_tokens in final_targets):
                    assertion['required'] = False
            assertions = step.get('assertions', [])
            if assertions and not any(assertion.get('required', True) is not False for assertion in assertions):
                step['verification_required'] = False

    @staticmethod
    def _validate_status_control_preconditions(steps: list[dict[str, Any]]) -> None:
        for index, step in enumerate(steps):
            description = str(step.get('description') or '').lower()
            if 'status control' not in description or index == 0:
                continue
            current_context: list[str] = []
            for prior_step in reversed(steps[:index]):
                prior_description = str(prior_step.get('description') or '').lower()
                if any(term in prior_description for term in ('navigate', 'go to')):
                    break
                current_context.append(prior_description)
            opens_context = any(
                any(verb in prior for verb in ('open', 'select'))
                and any(target in prior for target in ('record', 'detail', 'case', 'alert'))
                for prior in current_context
            )
            if not opens_context:
                raise GlobalPlanError(
                    f'Planner 浏览器步骤 {index + 1} 操作状态控件前缺少独立的记录或详情打开步骤。'
                )

    @staticmethod
    def _validate_field_updates_before_status_selection(steps: list[dict[str, Any]]) -> None:
        status_selected = False
        for index, step in enumerate(steps):
            description = str(step.get('description') or '').lower()
            if any(term in description for term in ('navigate', 'go to')) or (
                any(verb in description for verb in ('open', 'select'))
                and any(target in description for target in ('record', 'detail'))
            ):
                status_selected = False
            selects_status = 'status' in description and any(
                verb in description for verb in ('select', 'set', 'change', 'choose')
            )
            updates_field = any(term in description for term in ('field', 'category')) and any(
                verb in description for verb in ('select', 'set', 'change', 'choose', 'update')
            )
            if updates_field and status_selected:
                raise GlobalPlanError(
                    f'Browser step {index + 1} updates a field after selecting a status in the same detail context. Move and verify the field update before the status selection.'
                )
            if selects_status:
                status_selected = True

    @staticmethod
    def _asserts_field_dialog_after_status_selection(
        description: str,
        assertions: list[dict[str, Any]],
    ) -> bool:
        normalized_description = description.lower()
        selects_status = 'status' in normalized_description and any(
            verb in normalized_description for verb in ('select', 'set', 'change', 'choose')
        )
        if not selects_status:
            return False
        for assertion in assertions:
            target = assertion.get('target') or {}
            intent = str(target.get('intent') if isinstance(target, dict) else target).lower()
            if any(term in intent for term in ('field', 'category', 'dialog', 'chooser')):
                return True
        return False

    @staticmethod
    def _parse_plan_payload(content: str) -> dict[str, Any]:
        normalized = content.strip()
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            for match in re.finditer(r'\{', normalized):
                try:
                    payload, _ = decoder.raw_decode(normalized[match.start():])
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    return payload
            raise
        if not isinstance(payload, dict):
            raise json.JSONDecodeError('Planner response is not an object.', normalized, 0)
        return payload

    @staticmethod
    def _normalize_capabilities(raw_capabilities: object, step_index: int) -> list[str]:
        from apps.ai_testing.execution.capabilities import get_capability

        capability_aliases = {
            'navigate': 'browser.navigate',
            'inspect': 'browser.inspect',
            'read': 'browser.inspect',
            'read_page': 'browser.inspect',
            'browser.read': 'browser.inspect',
            'browser.read_page': 'browser.inspect',
            'act': 'browser.act',
            'write': 'browser.act',
            'capture': 'browser.capture',
        }
        if not isinstance(raw_capabilities, list) or not raw_capabilities:
            raise GlobalPlanError(f'Planner 浏览器步骤 {step_index} 必须包含非空 allowed_capabilities。')
        normalized_capabilities: list[str] = []
        for raw_capability in raw_capabilities:
            if not isinstance(raw_capability, str) or not raw_capability.strip():
                raise GlobalPlanError(f'Planner 浏览器步骤 {step_index} 包含无效 capability。')
            capability_name = capability_aliases.get(raw_capability.strip(), raw_capability.strip())
            try:
                get_capability(capability_name)
            except ValueError as error:
                raise GlobalPlanError(f'Planner 浏览器步骤 {step_index} 的 capability 无效：{error}') from error
            normalized_capabilities.append(capability_name)
        if 'browser.navigate' in normalized_capabilities and 'browser.act' not in normalized_capabilities:
            normalized_capabilities.append('browser.act')
        return normalized_capabilities

    @staticmethod
    def _normalize_assertions(raw_assertions: object, step_index: int) -> list[dict[str, Any]]:
        from apps.ai_testing.execution.assertion_registry import AssertionContractError, parse_assertion

        if not isinstance(raw_assertions, list) or not raw_assertions:
            raise GlobalPlanError(f'Planner 浏览器步骤 {step_index} 必须包含非空 assertions。')
        normalized_assertions: list[dict[str, Any]] = []
        for assertion_index, raw_assertion in enumerate(raw_assertions, start=1):
            if not isinstance(raw_assertion, dict):
                raise GlobalPlanError(f'Planner 浏览器步骤 {step_index} 的断言 {assertion_index} 不是对象。')
            assertion_payload = dict(raw_assertion)
            target = assertion_payload.get('target')
            if isinstance(target, str) and target.strip():
                assertion_payload['target'] = {'locator': target.strip()}
            expected = assertion_payload.get('expected')
            if isinstance(expected, str) and expected.strip():
                assertion_payload['expected'] = {'value': expected.strip()}
            elif isinstance(expected, (int, float, bool)):
                assertion_payload['expected'] = {'value': expected.strip() if isinstance(expected, str) else expected}
            operator_aliases = {
                'displays_normally': 'exists',
                'is_displayed': 'exists',
                'visible': 'exists',
                'not_visible': 'not_exists',
                'gte': 'greater_than',
                'gt': 'greater_than',
                'lte': 'less_than',
                'lt': 'less_than',
            }
            operator = assertion_payload.get('operator')
            if isinstance(operator, str):
                assertion_payload['operator'] = operator_aliases.get(operator.strip(), operator.strip())
            assert_kind = assertion_payload.get('assert_kind')
            if isinstance(assert_kind, str):
                from apps.ai_testing.execution.assertion_registry import ASSERTION_KINDS

                definition = ASSERTION_KINDS.get(assert_kind.strip())
                if definition is not None:
                    assertion_payload['evidence_requirements'] = list(definition.required_evidence)
            try:
                assertion = parse_assertion(assertion_payload)
            except AssertionContractError as error:
                raise GlobalPlanError(
                    f'Planner 浏览器步骤 {step_index} 的断言 {assertion_index} 无效：{error}'
                ) from error
            normalized_assertions.append({
                'action': 'assert',
                'assert_kind': assertion.assert_kind,
                'target': assertion.target,
                'operator': assertion.operator,
                'expected': assertion.expected,
                'evidence_requirements': list(assertion.evidence_requirements),
                'required': assertion.required,
                'timeout_ms': assertion.timeout_ms,
            })
        return normalized_assertions

    @staticmethod
    def _device_id_is_from_goal(device_id: str, task_description: str) -> bool:
        if not device_id or not task_description:
            return False
        pattern = rf'(?<![A-Za-z0-9_-]){re.escape(device_id)}(?![A-Za-z0-9_-])'
        return re.search(pattern, task_description) is not None

    @staticmethod
    def _load_active_model_configs():
        close_old_connections()
        from apps.ai_testing.models import AITestModelConfig

        configs = list(
            AITestModelConfig.objects.filter(
                role='planner_text',
                is_active=True,
            ).order_by('id')
        )
        seen = set()
        unique_configs = []
        for config in configs:
            fingerprint = (config.model_type, config.base_url, config.model_name)
            if fingerprint not in seen:
                seen.add(fingerprint)
                unique_configs.append(config)
        return unique_configs

    @staticmethod
    def _load_cached_plan_steps(
        task_description: str,
        environment_configuration_id: int | None,
    ) -> list[dict[str, Any]]:
        close_old_connections()
        from apps.ai_testing.models import AIExecutionPlanRevision

        revision = (
            AIExecutionPlanRevision.objects.filter(
                source_goal=task_description,
                reason='initial',
                execution_record__environment_configuration_id=environment_configuration_id,
            )
            .order_by('-created_at', '-id')
            .first()
        )
        if revision is None or not isinstance(revision.plan, dict):
            return []
        steps = revision.plan.get('steps')
        if not isinstance(steps, list):
            return []
        return [
            dict(step.get('source') or step)
            for step in steps
            if isinstance(step, dict)
        ]

    @staticmethod
    def _load_active_prompt_content(prompt_type: str) -> str:
        close_old_connections()
        from apps.ai_testing.models import AITestPromptConfig

        config = AITestPromptConfig.get_active_config(prompt_type)
        return config.content.strip() if config and config.content else ''

    @staticmethod
    def _load_data_factory_resources(configuration_id: int | None) -> list[dict[str, object]]:
        close_old_connections()
        if configuration_id is None:
            return []
        from apps.ai_testing.execution.data_factory_resources import configured_resource_summaries
        from apps.core.models import EnvironmentConfiguration

        configuration = EnvironmentConfiguration.objects.filter(id=configuration_id).first()
        return configured_resource_summaries(configuration) if configuration is not None else []

    async def _get_active_model_configs(self):
        return await sync_to_async(self._load_active_model_configs)()


def _response_payload(response: dict[str, Any], tool_name: str) -> dict[str, Any]:
    message = response['choices'][0]['message']
    for tool_call in message.get('tool_calls') or []:
        function = tool_call.get('function') or {}
        if function.get('name') == tool_name:
            payload = json.loads(str(function.get('arguments') or ''))
            if isinstance(payload, dict):
                return payload
            raise json.JSONDecodeError('Tool arguments must be an object.', '', 0)
    content = message.get('content')
    normalized = str(content or '').strip()
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for match in re.finditer(r'\{', normalized):
            try:
                payload, _ = decoder.raw_decode(normalized[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        raise
    if not isinstance(payload, dict):
        raise json.JSONDecodeError('Response must be an object.', normalized, 0)
    return payload


def _action_submission_tool(assertion_count: int, require_bindings: bool = False) -> dict[str, Any]:
    tool = deepcopy(ACTION_SUBMISSION_TOOL)
    binding = tool['function']['parameters']['properties']['assertion_bindings']['items']['properties']['assertion_index']
    binding['minimum'] = 1
    binding['maximum'] = max(1, assertion_count)
    if require_bindings:
        tool['function']['parameters']['required'].append('assertion_bindings')
    return tool