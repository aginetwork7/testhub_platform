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
                'correlates_resource': {'type': 'string'},
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
                    'role': {'type': 'string'}, 'accessible_name': {'type': 'string'},
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
        prompt_content = await self._get_active_prompt_content()
        if not prompt_content:
            raise GlobalPlanError('未配置可用的 Planner Vision 提示词。')

        from apps.requirement_analysis.models import AIModelService

        visible_text = str(evidence.get('visible_text') or '')[:600]
        actionable_controls = evidence.get('actionable_controls') or []
        observable_elements = (evidence.get('observable_elements') or [])[:80]
        accessibility_snapshot = evidence.get('accessibility_snapshot') or {}
        blocking_state = evidence.get('blocking_state') or {}
        allowed_capabilities = evidence.get('allowed_capabilities') or []
        assertions = evidence.get('assertions') or []
        execution_resources = evidence.get('execution_resources') or []
        from apps.ai_testing.execution.capabilities import allowed_browser_actions

        permitted_actions = allowed_browser_actions(allowed_capabilities)
        messages: list[dict[str, Any]] = [
            {
                'role': 'system',
                'content': (
                    f'{prompt_content}\n\nRuntime contract:\n'
                    'Call submit_browser_actions exactly once with exactly one action. No prose. '
                    'Replan only the supplied step from current evidence; verified predecessors and the global plan are immutable. '
                    f'Actions allowed for this step: {", ".join(permitted_actions)}. '
                    'Use only current discovered evidence. Prefer a unique exact role and accessible_name; otherwise use a selector from actionable_controls. '
                    'Accessibility node IDs are observation identities, never selectors. Never invent routes, selectors, coordinates, values, or evidence. '
                    'A state-changing action is not proof. Assert only an already-observed state, and bind only assertions that require a discovered locator. '
                    'Never bind a collection assertion to a collection container, summary, loading element, or empty-state placeholder; its locator must select the actual repeated items. If no actual item is currently observed, do not substitute another element as evidence. '
                    'If current evidence already satisfies the step after a prior action, return assert with complete discovered bindings; do not repeat the transition. '
                    'When current evidence shows loading after a prior state-changing action, use one bounded wait action; never resubmit the triggering action while loading. '
                    'If a blocking layer exists, resolve it before background actions. If prior actions failed verification, choose a distinct supported action. '
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
                            f'Verified predecessor steps: {json.dumps(evidence.get("verified_predecessors", []), ensure_ascii=True)}\n'
                            f'Prior actions: {json.dumps(evidence.get("prior_actions", []), ensure_ascii=True)}\n'
                            f'Page metrics: {json.dumps(evidence.get("page_metrics", {}), ensure_ascii=True)}\n'
                            f'Visible text:\n{visible_text}'
                            f'\nActionable controls:\n{json.dumps(actionable_controls, ensure_ascii=True)}'
                            f'\nObservable elements:\n{json.dumps(observable_elements, ensure_ascii=True)}'
                            f'\nAccessibility snapshot:\n{json.dumps(accessibility_snapshot, ensure_ascii=True)}'
                            f'\nBlocking state:\n{json.dumps(blocking_state, ensure_ascii=True)}'
                            f'\nAllowed capabilities:\n{json.dumps(allowed_capabilities, ensure_ascii=True)}'
                            f'\nAllowed actions:\n{json.dumps(permitted_actions, ensure_ascii=True)}'
                            f'\nAssertions to verify:\n{json.dumps(assertions, ensure_ascii=True)}'
                            f'\nExecution-scoped resources:\n{json.dumps(execution_resources, ensure_ascii=True)}'
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
                tools=[_action_submission_tool(len(assertions))],
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
        self._validate_accessible_action(actions, accessibility_snapshot, actionable_controls)
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
            invalid_indexes = {
                binding.get('assertion_index')
                for binding in bindings
                if not isinstance(binding.get('assertion_index'), int)
                or binding['assertion_index'] < 1
                or binding['assertion_index'] > len(assertions)
                or assertions[binding['assertion_index'] - 1].get('assert_kind') != 'absence'
            }
            if invalid_indexes:
                raise GlobalPlanError('Only absence assertions may be bound before a state-changing action.')
        bindable_indexes = {
            index
            for index, assertion in enumerate(assertions, start=1)
            if assertion.get('assert_kind') in {'field_value', 'popup', 'element_state', 'collection', 'absence'}
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
        self._validate_collection_bindings(bindings, assertions, [*actionable_controls, *observable_elements])
        self._validate_offscreen_search_action(
            actions,
            evidence.get('page_metrics') or {},
            actionable_controls,
            evidence.get('prior_actions') or [],
            step_description,
            assertions,
        )
        self._validate_discovered_navigation(actions, actionable_controls)
        self._validate_absence_recovery(actions, actionable_controls, assertions)
        actions = self._resolve_visible_record_action(
            actions,
            actionable_controls,
            evidence.get('execution_resources') or [],
            evidence.get('page_metrics') or {},
            evidence.get('verified_predecessors') or [],
            correlates_resource=str(evidence.get('correlates_resource') or ''),
        )
        self._validate_non_repeating_action(
            actions,
            evidence.get('prior_actions') or [],
            actionable_controls,
        )
        self._validate_blocking_layer_action(actions, actionable_controls, bindings, blocking_state)
        if assertion_check and {binding['assertion_index'] for binding in bindings} != bindable_indexes:
            raise GlobalPlanError(
                'Planner Vision returned assert without complete locator bindings. If the required state is not currently visible, return one state-changing action using a current actionable selector instead of assert. If it is visible, return assert with every required DOM binding. '
                f'Bindings: {json.dumps(bindings, ensure_ascii=True)}.'
            )
        if bindings:
            actions[0]['assertion_bindings'] = bindings
        return actions

    @staticmethod
    def _validate_accessible_action(
        actions: list[dict[str, Any]],
        accessibility_snapshot: dict[str, Any],
        actionable_controls: list[dict[str, Any]] | None = None,
    ) -> None:
        action = actions[0] if len(actions) == 1 else {}
        role = str(action.get('role') or '').strip()
        accessible_name = str(action.get('accessible_name') or '').strip()
        if not role and not accessible_name:
            return
        if not role or not accessible_name:
            raise GlobalPlanError('Accessibility actions require both role and accessible_name.')
        matches = [
            node
            for node in accessibility_snapshot.get('nodes', [])
            if isinstance(node, dict)
            and str(node.get('role') or '').strip().casefold() == role.casefold()
            and str(node.get('name') or '').strip() == accessible_name
        ]
        if len(matches) == 1:
            return
        actionable_matches = [
            control
            for control in actionable_controls or []
            if isinstance(control, dict)
            and str(control.get('role') or '').strip().casefold() == role.casefold()
            and str(control.get('name') or '').strip() == accessible_name
            and str(control.get('selector') or '').strip()
        ]
        if len(actionable_matches) == 1:
            action['selector'] = str(actionable_matches[0]['selector']).strip()
            action['role'] = None
            action['accessible_name'] = None
            return
        raise GlobalPlanError(
            'Accessibility action role and accessible_name must identify exactly one current AX node or actionable control.'
        )

    @staticmethod
    def _validate_collection_bindings(
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        discovered_elements: list[dict[str, Any]],
    ) -> None:
        choice_roles = {'option', 'menuitem', 'menuitemcheckbox', 'menuitemradio'}
        elements_by_locator = {
            str(element.get('selector') or '').strip(): element
            for element in discovered_elements
            if isinstance(element, dict)
        }
        for binding in bindings:
            assertion_index = binding.get('assertion_index')
            if (
                not isinstance(assertion_index, int)
                or assertion_index < 1
                or assertion_index > len(assertions)
                or assertions[assertion_index - 1].get('assert_kind') != 'collection'
            ):
                continue
            locator = str(binding.get('locator') or '').strip()
            element = elements_by_locator.get(locator, {})
            if (
                str(element.get('role') or '').strip().casefold() in choice_roles
                or str(element.get('tag') or '').strip().casefold() == 'option'
            ):
                raise GlobalPlanError(
                    'Planner Vision collection binding must identify repeated content items, not a menu or listbox choice control.'
                )

    @staticmethod
    def _validate_absence_recovery(
        actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
    ) -> None:
        if not any(
            isinstance(assertion, dict)
            and assertion.get('assert_kind') == 'absence'
            and assertion.get('required', True) is not False
            for assertion in assertions
        ):
            return
        action = actions[0] if len(actions) == 1 else {}
        if str(action.get('action') or '').strip() == 'navigate':
            raise GlobalPlanError('Planner Vision must not prove absence by navigating away from the target context.')
        selector = str(action.get('selector') or '').strip()
        selected_control = next((
            control
            for control in actionable_controls
            if isinstance(control, dict) and str(control.get('selector') or '').strip() == selector
        ), None)
        if selected_control is not None and str(selected_control.get('url') or '').strip():
            raise GlobalPlanError('Planner Vision must not prove absence by following a navigation link away from the target context.')

    @staticmethod
    def _validate_offscreen_search_action(
        actions: list[dict[str, Any]],
        page_metrics: dict[str, Any],
        actionable_controls: list[dict[str, Any]],
        prior_actions: list[dict[str, Any]],
        step_description: str = '',
        assertions: list[dict[str, Any]] | None = None,
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
        if action_name == 'scroll':
            selector = str(action.get('selector') or '').strip()
            selected_container = next((
                container
                for container in scroll_containers
                if isinstance(container, dict)
                and str(container.get('selector') or '').strip() == selector
            ), None)
            if selected_container is None:
                raise GlobalPlanError(
                    'Planner Vision scroll target must be a container discovered in current page metrics.'
                )
            if float(selected_container.get('client_height') or 0) * 0.8 < 2:
                raise GlobalPlanError(
                    'Planner Vision scroll target has no usable viewport; choose a larger discovered container or a visible target control.'
                )
        if action_name == 'wait':
            raise GlobalPlanError('Planner Vision must scroll a discovered container instead of waiting while off-screen content remains.')
    @staticmethod
    def _validate_non_repeating_action(
        actions: list[dict[str, Any]],
        prior_actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]] | None = None,
    ) -> None:
        action = actions[0] if len(actions) == 1 else {}
        action_name = str(action.get('action') or '').strip()
        selector = str(action.get('selector') or '').strip()
        role = str(action.get('role') or '').strip().casefold()
        accessible_name = str(action.get('accessible_name') or '').strip()
        locator_identity = f'css:{selector}' if selector else f'ax:{role}:{accessible_name}' if role and accessible_name else ''
        if action_name not in {'click', 'double_click', 'right_click', 'hover', 'fill', 'press', 'select'} or not locator_identity:
            return

        def prior_identity(prior_action: dict[str, Any]) -> str:
            prior_selector = str(prior_action.get('selector') or '').strip()
            if prior_selector:
                return f'css:{prior_selector}'
            prior_role = str(prior_action.get('role') or '').strip().casefold()
            prior_name = str(prior_action.get('accessible_name') or '').strip()
            return f'ax:{prior_role}:{prior_name}' if prior_role and prior_name else ''

        previous_action = prior_actions[-1] if prior_actions and isinstance(prior_actions[-1], dict) else {}
        immediate_repeat = (
            str(previous_action.get('action') or '').strip() == action_name
            and prior_identity(previous_action) == locator_identity
        )
        repeated_earlier = any(
            isinstance(prior_action, dict)
            and str(prior_action.get('action') or '').strip() == action_name
            and prior_identity(prior_action) == locator_identity
            for prior_action in prior_actions
        )
        selected_control = next(
            (
                control
                for control in actionable_controls or []
                if isinstance(control, dict) and (
                    (selector and str(control.get('selector') or '').strip() == selector)
                    or (
                        role and accessible_name
                        and str(control.get('role') or '').strip().casefold() == role
                        and str(control.get('name') or '').strip() == accessible_name
                    )
                )
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
    def _resolve_visible_record_action(
        actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
        execution_resources: list[dict[str, Any]],
        page_metrics: dict[str, Any] | None = None,
        verified_predecessors: list[dict[str, Any]] | None = None,
        correlates_resource: str = '',
    ) -> list[dict[str, Any]]:
        resource_type = correlates_resource.strip()
        if not resource_type or not any(
            isinstance(resource, dict) and str(resource.get('resource_type') or '').strip() == resource_type
            for resource in execution_resources
        ):
            return actions
        predecessor_locators = {
            str(target.get('locator') or '').strip()
            for predecessor in verified_predecessors or []
            if isinstance(predecessor, dict)
            for assertion in predecessor.get('assertions') or []
            if isinstance(assertion, dict)
            for target in [assertion.get('target')]
            if isinstance(target, dict) and str(target.get('locator') or '').strip()
        }
        actionable_selectors = {
            str(control.get('selector') or '').strip()
            for control in actionable_controls
            if isinstance(control, dict) and str(control.get('selector') or '').strip()
        }
        if any(
            locator == selector or locator.startswith(f'{selector} > ')
            for locator in predecessor_locators
            for selector in actionable_selectors
        ):
            return actions
        action = actions[0] if len(actions) == 1 else {}
        action_name = str(action.get('action') or '').strip()
        if action_name in {'fill', 'press', 'select', 'select_option', 'scroll', 'wait'}:
            return actions
        match_values: list[str] = []
        for resource in execution_resources:
            if (
                not isinstance(resource, dict)
                or str(resource.get('resource_type') or '').strip() != resource_type
            ):
                continue
            payload = resource.get('resource') if isinstance(resource.get('resource'), dict) else resource
            correlation = payload.get('result_correlation') if isinstance(payload, dict) else None
            values = correlation.get('match_values') if isinstance(correlation, dict) else None
            if isinstance(values, list):
                match_values.extend(str(value).strip().casefold() for value in values if str(value).strip())
        if not match_values:
            return actions
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
                return [{'action': 'scroll', 'selector': str(target['selector']), 'value': 'down'}]
            raise GlobalPlanError(
                'Planner Vision cannot select or assert an uncorrelated or partially correlated record; no current control contains every result correlation value.'
            )
        best_selectors = {selector for score, selector in scored_controls if score == max_score}
        if len(best_selectors) > 1:
            raise GlobalPlanError(
                'Planner Vision cannot select a correlated record because multiple controls have the same complete match.'
            )
        if not best_selectors:
            raise GlobalPlanError(
                'Planner Vision cannot select a correlated record because no actionable control has a complete match.'
            )
        best_selector = next(iter(best_selectors))
        if action_name == 'assert' or (
            action_name in {'click', 'double_click', 'right_click'}
            and str(action.get('selector') or '').strip() != best_selector
        ):
            return [{
                'action': 'click',
                'selector': best_selector,
            }]
        return actions

    @staticmethod
    def _validate_blocking_layer_action(
        actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
        bindings: list[dict[str, Any]] | None = None,
        blocking_state: dict[str, Any] | None = None,
    ) -> None:
        observed_blocking_locators = {
            str(control.get('selector') or '')
            for control in actionable_controls
            if isinstance(control, dict) and control.get('blocking_layer') is True
        }
        state = blocking_state if isinstance(blocking_state, dict) else {}
        blocking_locators = {
            str(selector).strip()
            for selector in state.get('allowed_selectors', [])
            if str(selector).strip()
        } or observed_blocking_locators
        if not blocking_locators:
            return
        action = actions[0] if len(actions) == 1 else {}
        action_role = str(action.get('role') or '').strip().casefold()
        action_name = str(action.get('accessible_name') or '').strip()
        semantic_targets = state.get('allowed_semantic_targets') or [
            {
                'role': str(control.get('role') or '').strip().casefold(),
                'accessible_name': str(control.get('name') or '').strip(),
            }
            for control in actionable_controls
            if isinstance(control, dict) and control.get('blocking_layer') is True
        ]
        semantic_blocking_matches = [
            target
            for target in semantic_targets
            if isinstance(target, dict)
            and str(target.get('role') or '').strip().casefold() == action_role
            and str(target.get('accessible_name') or '').strip() == action_name
        ]
        if action_role and action_name and len(semantic_blocking_matches) == 1:
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

    @staticmethod
    def _load_active_model_config():
        close_old_connections()
        from apps.ai_testing.models import AITestModelConfig

        return AITestModelConfig.objects.filter(role='planner_vision', is_active=True).first()

    async def _get_active_model_config(self):
        return await sync_to_async(self._load_active_model_config)()

    @staticmethod
    def _load_active_prompt_content() -> str:
        close_old_connections()
        from apps.ai_testing.models import AITestPromptConfig

        config = AITestPromptConfig.get_active_config('planner_vision')
        return config.content.strip() if config and config.content else ''

    async def _get_active_prompt_content(self) -> str:
        return await sync_to_async(self._load_active_prompt_content)()


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
                    'For browser, output step_mode="ai", a concrete description, a non-empty allowed_capabilities array, verification_required=true, and at least one required assertion for the immediate state produced by that transition. No browser step may pass from action completion alone. '
                    'When a browser step selects a record produced from an earlier data_factory resource, set correlates_resource to that exact resource_type; omit it from all other steps. '
                    'Each browser step must perform exactly one user-visible state transition and assert only its immediate resulting state. Split navigation, record selection, status changes, modal choices, confirmations, and subsequent page verification into separate ordered steps. '
                    'For a state change that opens menus or dialogs and requires additional choices or confirmation, plan every intermediate transition: open the control and assert its options, select the requested option and assert the next dialog, make required dialog selections and assert them, then confirm and only then assert the committed final state. Never assert the final state before the commit action. '
                    'When the goal requires both updating a field and reaching a final status, plan and verify the field update before the irreversible status transition. Do not assume a status transition will expose a field dialog; only handle such a dialog during visual replanning when current page evidence proves it exists. '
                    'Never create conditional steps such as "if a dialog appears" because execution plans do not have conditional branches. Plan only states required by the goal; assertion-driven replanning will handle a blocking dialog when current page evidence proves it exists. '
                    'Browser allowed_capabilities may contain only browser.navigate, browser.inspect, browser.act, and browser.capture. '
                    'Configured environment authentication is completed by the runtime before the plan begins; do not output login steps or login assertions. '
                    'Do not add a step solely to establish a generic post-login landing page; begin with the first goal-specific user-visible transition. '
                    'Every fill, press, and select action must include a non-empty value. '
                    'Use fill only when the selected actionable control has editable=true; use click, press, or select for readonly controls. '
                    'Every assertion must use action="assert" and include assert_kind, target, operator, '
                    'expected, and evidence_requirements. Use only registered generic kinds: text, field_value, '
                    'popup, media, video, stream_state, playback, element_state, url, network, '
                    'api_resource, command_result, download_task, collection, absence, theme. '
                    'Do not treat names from the user goal as exact rendered UI text unless the goal explicitly requires that wording. After selecting a mode or option, assert the newly introduced control or panel needed by the next transition instead of repeating the selected label as a text assertion. '
                    'Use element_state or collection for static UI elements such as images, thumbnails, cards, and controls. element_state supports objective visibility through exists/not_exists and visible text through equals/contains/matches; never assert inferred CSS states such as selected, active, highlighted, or focused. After selecting a record, assert an objectively observable detail element, dialog, text, or URL introduced by that transition. '
                    'Collection assertions compare the observed item count: use exists/not_exists or a numeric expected.value with equals/greater_than/less_than; never use contains or descriptive count text. The target intent must describe the repeated items, not their parent container, summary, loading element, or empty-state placeholder. '
                    'For page-bound element_state, collection, and popup assertions, use target.intent for the semantic target; the Visual Planner will bind a runtime locator after observing the page. '
                    'Use media or video only for native audio/video elements and compare native fields such as paused, ended, readyState, currentTime, videoWidth, videoHeight, or currentSrc. To prove that media is playing, always use playback with time-progress evidence; never use a descriptive media/video expected.value such as playing. '
                    'For stream_state and playback, expected must include numeric minimum_advanced_seconds; do not use descriptive expected.value strings. '
                    'For completion of a user-triggered file download, use download_task with operator="equals", expected.value="completed", evidence_requirements=["download_task_state"], and preserve the requested timeout_ms. Do not model download completion as element_state. '
                    'For dark or light appearance, use theme with operator="equals", expected.value="dark" or "light", and theme_state evidence. Do not use visual_change as proof of a semantic final state because unrelated movement also changes pixels. '
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
                if raw_step.get('verification_required', True) is False:
                    raise GlobalPlanError(
                        f'Planner 浏览器步骤 {index} 禁止关闭验证；每个状态转换都必须声明立即后置断言。'
                    )
                assertions = GlobalTestPlanner._normalize_assertions(raw_step.get('assertions'), index)
                correlates_resource = str(raw_step.get('correlates_resource') or '').strip()
                available_resource_types = {
                    str(step.get('resource_type') or '').strip()
                    for step in normalized_steps
                    if step.get('executor') == 'data_factory'
                }
                if correlates_resource and correlates_resource not in available_resource_types:
                    raise GlobalPlanError(
                        f'Planner 浏览器步骤 {index} 的 correlates_resource 未引用此前创建的 data_factory 资源。'
                    )
                if GlobalTestPlanner._asserts_field_dialog_after_status_selection(description, assertions):
                    raise GlobalPlanError(
                        f'Planner 浏览器步骤 {index} 假设状态选择后才出现字段对话框；必须先设置并验证字段，再执行最终状态转换。'
                    )
                from apps.ai_testing.execution.step_compiler import StepCompilationError, compile_browser_step

                try:
                    normalized_step = compile_browser_step(
                        description=description,
                        allowed_capabilities=allowed_capabilities,
                        assertions=assertions,
                        step_index=index,
                        correlates_resource=correlates_resource,
                    )
                except StepCompilationError as error:
                    raise GlobalPlanError(str(error)) from error
                normalized_steps.append(normalized_step)
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
        GlobalTestPlanner._validate_status_control_preconditions(normalized_steps)
        GlobalTestPlanner._validate_field_updates_before_status_selection(normalized_steps)
        return normalized_steps

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
                if assert_kind.strip() == 'visual_change':
                    raise GlobalPlanError(
                        f'Planner 浏览器步骤 {step_index} 的断言 {assertion_index} 无效：'
                        'visual_change cannot prove a semantic final state.'
                    )
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


def _action_submission_tool(assertion_count: int) -> dict[str, Any]:
    tool = deepcopy(ACTION_SUBMISSION_TOOL)
    binding = tool['function']['parameters']['properties']['assertion_bindings']['items']['properties']['assertion_index']
    binding['minimum'] = 1
    binding['maximum'] = max(1, assertion_count)
    return tool