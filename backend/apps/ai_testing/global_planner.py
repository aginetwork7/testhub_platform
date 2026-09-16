from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import logging
import re
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections

from apps.ai_testing.execution.intent_text import (
    continuing_collection_locator,
    display_value_from_target,
    expects_true,
    innermost_selectors,
    is_anchored_selector,
    popup_intent_mismatch,
    selectors_are_nested,
)
from apps.ai_testing.execution.environment_resources import default_device_camera_names, default_device_site, environment_device_resources, is_text_input, refers_to_target_device
from apps.ai_testing.execution.model_errors import is_transient_llm_error

from apps.core.llm import LLMCallContext, OpenAICompatibleClient


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
                'transition': {'type': 'object', 'properties': {
                    'kind': {'type': 'string', 'enum': ['generic', 'select_option', 'filter_results']},
                    'value': {'type': 'string'},
                    'result_presence': {'type': 'string', 'enum': ['present', 'absent']},
                }, 'required': ['kind']},
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


# Bump when the planning instructions in _build_messages change in a way that should invalidate cached plans.
PLAN_CONTRACT_VERSION = 5


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

        visible_text = str(evidence.get('visible_text') or '')[:600]
        actionable_controls = evidence.get('actionable_controls') or []
        observable_elements = (evidence.get('observable_elements') or [])[:120]
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
                    'A state-changing action is not proof. Assert only an already-observed state, and bind only assertions that require a discovered locator. A collection group_selector may be bound before a filtering action so the resulting collection can be measured afterward. '
                    'After choosing a dropdown or menu option, bind a field_value assertion to the control that now displays the selected value, never to the option that was clicked. '
                    'Never bind a collection assertion to a collection container, summary, loading element, empty-state placeholder, or one item selector. Its locator must use a discovered observable element group_selector that selects the actual repeated items. If no group_selector is currently observed, do not substitute another element as evidence. A group_selector whose group_size is 1 is valid when a search or filter legitimately yields a single matching item. '
                    'For an assertion whose target.visual_content is image, bind only a discovered element whose has_visual_content is true and that shows the rendered image, video, or canvas the step introduced; never bind a text label, an empty container, or a loading placeholder, and never substitute an unrelated rendered element. '
                    'If current evidence already satisfies the step after a prior action, return assert with complete discovered bindings; do not repeat the transition. '
                    'When current evidence shows loading after a prior state-changing action, use one bounded wait action; never resubmit the triggering action while loading. '
                    'If a blocking layer exists, resolve it before background actions. If prior actions failed verification, choose a distinct supported action. '
                    'If the dialog that opened is not the one the step expects, close it and choose a different control instead of asserting. '
                    'Execution-scoped resources of type environment_device name the default test device and its cameras; when the step refers to the default, target, or test device or camera, act on exactly those camera names and never on a neighbouring camera. '
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

        response = await self._complete_with_failover(config, messages, len(assertions))
        try:
            payload = _response_payload(response, 'submit_browser_actions')
            actions = payload.get('actions') if isinstance(payload, dict) else None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise GlobalPlanError('Planner Vision 未返回有效 JSON 动作计划。') from error
        if not isinstance(actions, list) or not actions or not all(isinstance(item, dict) for item in actions):
            raise GlobalPlanError(
                f'Planner Vision 动作计划为空或格式无效：{json.dumps(payload, ensure_ascii=True)[:1200]}。'
            )
        bindings = self._collect_assertion_bindings(payload, actions, assertions)
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
        verified_predecessors = evidence.get('verified_predecessors') or []
        bindable_indexes = {
            index
            for index, assertion in enumerate(assertions, start=1)
            if assertion.get('assert_kind') in {'field_value', 'popup', 'element_state', 'collection', 'absence'}
            # A locator bound earlier in this step (by a binder or a previous attempt) is already evidence.
            and not str(((assertion.get('target') or {}) if isinstance(assertion.get('target'), dict) else {}).get('locator') or '').strip()
        }
        completed_prior_action = any(
            isinstance(action, dict) and action.get('status') == 'completed'
            for action in evidence.get('prior_actions') or []
        )
        if assertion_check or completed_prior_action:
            exact_bindings = self._bind_exact_text_assertions(
                bindings,
                assertions,
                [*actionable_controls, *observable_elements],
            )
            exact_bindings = self._bind_target_camera_thumbnail(
                exact_bindings,
                assertions,
                actionable_controls,
                execution_resources,
                step_description,
            )
            resolved_actions = self._resolve_completed_bound_assertion(
                actions,
                exact_bindings,
                bindable_indexes,
                evidence.get('prior_actions') or [],
            )
            if resolved_actions != actions or assertion_check:
                actions = resolved_actions
                bindings = exact_bindings
        assertion_check = len(actions) == 1 and str(actions[0].get('action') or '') == 'assert'
        if assertion_check:
            bindings = self._bind_verified_popup_absence(bindings, assertions, verified_predecessors)
            bindings = self._bind_verified_collection_continuation(
                bindings,
                assertions,
                verified_predecessors,
                evidence.get('prior_actions') or [],
                [*actionable_controls, *observable_elements],
            )
        # early_popup_resolution: a dialog introduced by the completed action is objective evidence.
        actions, bindings = self._resolve_visible_popup_assertion(
            actions,
            bindings,
            assertions,
            evidence.get('prior_actions') or [],
            step_description,
            evidence.get('transition'),
            blocking_state,
            [*actionable_controls, *observable_elements],
        )
        assertion_check = len(actions) == 1 and str(actions[0].get('action') or '') == 'assert'
        if not assertion_check:
            structurally_invalid = {
                binding.get('assertion_index')
                for binding in bindings
                if not isinstance(binding.get('assertion_index'), int)
                or binding['assertion_index'] < 1
                or binding['assertion_index'] > len(assertions)
            }
            if structurally_invalid:
                raise GlobalPlanError('Only absence or discovered collection assertions may be bound before a state-changing action.')
            premature_indexes = {
                binding['assertion_index']
                for binding in bindings
                if assertions[binding['assertion_index'] - 1].get('assert_kind') not in {'absence', 'collection'}
            }
            if premature_indexes:
                # A binding offered before the action is not evidence yet. Drop it and let the post-action
                # binding pass rediscover the locator instead of rejecting an otherwise valid action.
                logging.getLogger(__name__).info(
                    'planner_v2 dropped %s premature assertion binding(s) attached to a state-changing action',
                    len(premature_indexes),
                )
                bindings = [binding for binding in bindings if binding.get('assertion_index') not in premature_indexes]
        bindings = self._filter_non_dom_assertion_bindings(bindings, assertions)
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
                str(locator or '')
                for control in [*actionable_controls, *observable_elements]
                if isinstance(control, dict)
                for locator in (control.get('selector'), control.get('group_selector'))
            }
            discovered_locators.update(
                str(layer_id).strip()
                for layer_id in blocking_state.get('active_layer_ids') or []
                if str(layer_id).strip()
            )
            discovered_locators.update(
                str(target.get('locator') or '').strip()
                for predecessor in verified_predecessors
                if isinstance(predecessor, dict)
                for assertion in predecessor.get('assertions') or []
                if isinstance(assertion, dict)
                for target in [assertion.get('target')]
                if isinstance(target, dict) and str(target.get('locator') or '').strip()
            )
            if locator not in discovered_locators:
                raise GlobalPlanError('Planner Vision assertion binding locator was not discovered on the current page.')
        self._validate_collection_bindings(bindings, assertions, [*actionable_controls, *observable_elements])
        self._validate_visual_content_bindings(bindings, assertions, [*actionable_controls, *observable_elements])
        self._validate_dropdown_value_binding(
            bindings,
            assertions,
            evidence.get('prior_actions') or [],
            step_description,
            evidence.get('transition'),
            [*actionable_controls, *observable_elements],
        )
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
        actions = self._prefer_environment_device_control(
            actions,
            actionable_controls,
            evidence.get('execution_resources') or [],
            step_description,
        )
        actions = self._resolve_visible_record_action(
            actions,
            actionable_controls,
            evidence.get('execution_resources') or [],
            evidence.get('page_metrics') or {},
            evidence.get('verified_predecessors') or [],
            correlates_resource=str(evidence.get('correlates_resource') or ''),
            assertions=assertions,
        )
        actions, bindings = self._resolve_visible_popup_assertion(
            actions,
            bindings,
            assertions,
            evidence.get('prior_actions') or [],
            step_description,
            evidence.get('transition'),
            blocking_state,
            [*actionable_controls, *observable_elements],
        )
        self._validate_accessible_action(actions, accessibility_snapshot, actionable_controls)
        self._validate_non_repeating_action(
            actions,
            evidence.get('prior_actions') or [],
            actionable_controls,
            step_description,
            evidence.get('transition'),
            evidence.get('page_metrics') or {},
        )
        self._validate_blocking_layer_action(actions, actionable_controls, bindings, blocking_state)
        assertion_check = len(actions) == 1 and str(actions[0].get('action') or '') == 'assert'
        if assertion_check and self._bare_assert_on_action_step(step_description, evidence.get('prior_actions') or []):
            raise GlobalPlanError(
                'The step describes an action that has not been performed yet; return that state-changing action '
                f'("{str(step_description or "").strip()[:80]}") instead of assert. An assertion cannot stand in for the action.'
            )
        if assertion_check and {binding['assertion_index'] for binding in bindings} != bindable_indexes:
            raise GlobalPlanError(
                'Planner Vision returned assert without complete locator bindings. If the required state is not currently visible, return one state-changing action using a current actionable selector instead of assert. If it is visible, return assert with every required DOM binding. '
                f'Bindings: {json.dumps(bindings, ensure_ascii=True)}. '
                f'Returned action: {json.dumps(actions[0], ensure_ascii=True)[:400]}.'
                + self._no_completed_action_hint(step_description, evidence.get('prior_actions') or [])
                + self._missing_target_camera_hint(step_description, execution_resources, [*actionable_controls, *observable_elements])
            )
        if bindings:
            actions[0]['assertion_bindings'] = bindings
        return actions

    @staticmethod
    def _collect_assertion_bindings(
        payload: dict[str, Any],
        actions: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Gather locator bindings wherever the model placed them.

        The contract asks for a top-level ``assertion_bindings`` list, but models regularly attach the
        list to the action, alias it as ``bindings``, or put the locator straight on the assert action.
        All of those carry the same evidence, so accept them instead of failing the attempt.
        """
        collected: list[Any] = []
        for container in (payload, *(action for action in actions if isinstance(action, dict))):
            for key in ('assertion_bindings', 'bindings'):
                value = container.get(key)
                if value is None:
                    continue
                if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                    raise GlobalPlanError('Planner Vision assertion_bindings 格式无效。')
                collected.extend(value)
        for action in actions:
            if not isinstance(action, dict) or str(action.get('action') or '') != 'assert':
                continue
            action.pop('assertion_bindings', None)
            action.pop('bindings', None)
        bindable_indexes = [
            index
            for index, assertion in enumerate(assertions, start=1)
            if isinstance(assertion, dict)
            and assertion.get('assert_kind') in {'field_value', 'popup', 'element_state', 'collection', 'absence'}
            and not str((assertion.get('target') or {}).get('locator') or '').strip()
        ]
        if not collected and len(bindable_indexes) == 1:
            for action in actions:
                if not isinstance(action, dict) or str(action.get('action') or '') != 'assert':
                    continue
                target = action.get('target') if isinstance(action.get('target'), dict) else {}
                locator = str(action.get('selector') or action.get('locator') or target.get('locator') or '').strip()
                if locator:
                    collected.append({'assertion_index': bindable_indexes[0], 'locator': locator, 'selection_basis': 'assert action selector'})
                break
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[Any, str]] = set()
        for binding in collected:
            key = (binding.get('assertion_index'), str(binding.get('locator') or ''))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(binding)
        return deduped

    @staticmethod
    def _resolve_completed_bound_assertion(
        actions: list[dict[str, Any]],
        bindings: list[dict[str, Any]],
        bindable_indexes: set[int],
        prior_actions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        completed_prior_action = any(
            isinstance(action, dict) and action.get('status') == 'completed'
            for action in prior_actions
        )
        bound_indexes = {
            binding.get('assertion_index')
            for binding in bindings
            if isinstance(binding.get('assertion_index'), int)
        }
        if completed_prior_action and bindable_indexes and bound_indexes == bindable_indexes:
            return [{'action': 'assert'}]
        return actions

    @staticmethod
    def _bind_exact_text_assertions(
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        discovered_elements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        resolved = list(bindings)
        bound_indexes = {
            binding.get('assertion_index')
            for binding in bindings
            if isinstance(binding.get('assertion_index'), int)
        }
        semantic_roles = {'button', 'link', 'menuitem', 'option', 'tab', 'checkbox', 'radio'}
        for index, assertion in enumerate(assertions, start=1):
            target = assertion.get('target') or {}
            operator = assertion.get('operator')
            expected_value = (assertion.get('expected') or {}).get('value')
            explicit_text = bool(str(target.get('text') or '').strip())
            # An intent such as "status control showing To Do" names the displayed text as well. Value-display
            # assertions (equals/contains) are left to the runtime binder, which knows the pre-action state.
            expected_text = display_value_from_target(target).casefold() if operator == 'exists' else ''
            if (
                assertion.get('assert_kind') != 'element_state'
                or not expected_text
                # Image assertions are proven by rendered content, not by label text;
                # _validate_visual_content_bindings owns that check.
                or target.get('visual_content') == 'image'
            ):
                continue
            candidates: list[tuple[int, str]] = []
            containing_locators: set[str] = set()
            for element in discovered_elements:
                if not isinstance(element, dict):
                    continue
                locator = str(element.get('selector') or '').strip()
                visible_text = ' '.join(str(element.get('name') or element.get('text') or '').split()).casefold()
                if not locator or not visible_text:
                    continue
                if expected_text in visible_text:
                    containing_locators.add(locator)
                if visible_text != expected_text:
                    continue
                role = str(element.get('role') or '').strip().casefold()
                tag = str(element.get('tag') or '').strip().casefold()
                priority = 2 if role in semantic_roles else 1 if tag in {'button', 'a', 'li', 'input'} else 0
                candidates.append((priority, locator))
            max_priority = max((priority for priority, _ in candidates), default=-1)
            best_locators = {locator for priority, locator in candidates if priority == max_priority}
            if len(best_locators) > 1:
                # Repeated list labels share structural selectors; the attribute-anchored element is the control.
                anchored = {locator for locator in best_locators if is_anchored_selector(locator)}
                if len(anchored) == 1:
                    best_locators = anchored
            if len(best_locators) > 1:
                # A menu item rendered as div > ul > li > span repeats one text at every level: the innermost
                # element is the text node the assertion is about.
                innermost = innermost_selectors(sorted(best_locators))
                if len(innermost) == 1:
                    best_locators = set(innermost)
            model_locator = next((
                str(binding.get('locator') or '').strip()
                for binding in bindings
                if binding.get('assertion_index') == index
            ), '')
            if len(best_locators) == 1:
                resolved = [
                    binding
                    for binding in resolved
                    if binding.get('assertion_index') != index
                ]
                resolved.append({
                    'assertion_index': index,
                    'locator': next(iter(best_locators)),
                })
            elif index in bound_indexes and explicit_text:
                if model_locator in best_locators:
                    continue
                if not best_locators and model_locator in containing_locators:
                    continue
                if any(selectors_are_nested(model_locator, locator) for locator in best_locators):
                    continue
                shown_text = str(target.get('text') or '').strip()
                if best_locators:
                    raise GlobalPlanError(
                        f'Planner Vision element-state binding does not show the assertion target text "{shown_text}". '
                        f'Bind one of the discovered elements whose visible text is exactly that: {json.dumps(sorted(best_locators)[:3], ensure_ascii=True)}.'
                    )
                raise GlobalPlanError(
                    f'Planner Vision element-state binding does not match the assertion target text "{shown_text}", and no discovered element shows it. '
                    'If the option list or panel that contains it is closed, open it first; otherwise the page does not show that text.'
                )
        return resolved

    @staticmethod
    def _bind_verified_popup_absence(
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        verified_predecessors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        bound_indexes = {
            binding.get('assertion_index')
            for binding in bindings
            if isinstance(binding.get('assertion_index'), int)
        }
        missing_popup_indexes = [
            index
            for index, assertion in enumerate(assertions, start=1)
            if index not in bound_indexes
            and assertion.get('assert_kind') == 'popup'
            and assertion.get('operator') == 'not_exists'
        ]
        if len(missing_popup_indexes) != 1:
            return bindings
        popup_locators = {
            str(target.get('locator') or '').strip()
            for predecessor in verified_predecessors
            if isinstance(predecessor, dict)
            for assertion in predecessor.get('assertions') or []
            if isinstance(assertion, dict)
            and assertion.get('assert_kind') == 'popup'
            and assertion.get('operator') == 'exists'
            for target in [assertion.get('target')]
            if isinstance(target, dict) and str(target.get('locator') or '').strip()
        }
        if len(popup_locators) != 1:
            return bindings
        return [
            *bindings,
            {
                'assertion_index': missing_popup_indexes[0],
                'locator': next(iter(popup_locators)),
            },
        ]

    @staticmethod
    def _bind_verified_collection_continuation(
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        verified_predecessors: list[dict[str, Any]],
        prior_actions: list[dict[str, Any]],
        discovered_elements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Inherit a verified predecessor's collection locator for a verify-only step's unbound collection assertion.

        "Wait for the site camera list to finish loading" asserts on the repeated items the previous step already
        proved. While this step has changed no state (at most waited, scrolled or hovered), that group is still the
        evidence whether or not the model managed to bind it. Applies only when exactly one collection assertion is
        unbound and the predecessor group is still a discovered repeated-item group on the current page.
        """
        bound_indexes = {
            binding.get('assertion_index')
            for binding in bindings
            if isinstance(binding.get('assertion_index'), int)
        }
        unbound_indexes = [
            index
            for index, assertion in enumerate(assertions, start=1)
            if index not in bound_indexes
            and isinstance(assertion, dict)
            and assertion.get('assert_kind') == 'collection'
            and not str(((assertion.get('target') or {}) if isinstance(assertion.get('target'), dict) else {}).get('locator') or '').strip()
        ]
        if len(unbound_indexes) != 1:
            return bindings
        state_changing = {'click', 'select', 'fill', 'type', 'press', 'navigate', 'upload', 'drag'}
        if any(
            isinstance(action, dict)
            and action.get('status') == 'completed'
            and str(action.get('action') or '').strip() in state_changing
            for action in prior_actions
        ):
            return bindings
        group_selectors = {
            str(element.get('group_selector') or '').strip()
            for element in discovered_elements
            if isinstance(element, dict) and str(element.get('group_selector') or '').strip()
        }
        assertion = assertions[unbound_indexes[0] - 1]
        target = assertion.get('target') if isinstance(assertion.get('target'), dict) else {}
        locator = continuing_collection_locator(str(target.get('intent') or ''), verified_predecessors, group_selectors)
        if not locator:
            return bindings
        logging.getLogger(__name__).info('planner_v2 verify-only step inherited verified collection %s', locator)
        return [
            *bindings,
            {
                'assertion_index': unbound_indexes[0],
                'locator': locator,
                'selection_basis': 'verified predecessor collection on an unchanged page',
            },
        ]

    @staticmethod
    def _resolve_visible_popup_assertion(
        actions: list[dict[str, Any]],
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        prior_actions: list[dict[str, Any]],
        step_description: str,
        transition: dict[str, Any] | None,
        blocking_state: dict[str, Any],
        discovered_elements: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        active_layer_ids = blocking_state.get('active_layer_ids') or []
        completed_state_change = any(
            isinstance(action, dict)
            and action.get('status') == 'completed'
            and str(action.get('action') or '').strip() in {'click', 'select'}
            for action in prior_actions
        )
        popup_assertion = (
            len(assertions) == 1
            and assertions[0].get('assert_kind') == 'popup'
            and assertions[0].get('operator') == 'exists'
            and expects_true((assertions[0].get('expected') or {}).get('value'))
        )
        dialog_layer_ids = {
            str(layer_id).strip()
            for layer_id in blocking_state.get('dialog_layer_ids') or []
            if str(layer_id).strip()
        }
        single_dialog_layer = len(active_layer_ids) == 1 and str(active_layer_ids[0]).strip() in dialog_layer_ids
        if not (
            completed_state_change
            and popup_assertion
            and len(active_layer_ids) == 1
            and (
                GlobalTestPlanner._is_select_option_transition(step_description, transition)
                or single_dialog_layer
            )
        ):
            return actions, bindings
        layer_id = str(active_layer_ids[0]).strip()
        model_asserts = len(actions) == 1 and str(actions[0].get('action') or '') == 'assert'
        if single_dialog_layer and discovered_elements is not None and not model_asserts:
            # Dialog text is only a weak hint about which dialog opened (a reason picker lists reasons without
            # saying "reason"), so it never rejects evidence. It only stops this resolution from overriding a
            # model that has looked at the dialog and decided to act on it instead of asserting.
            mismatch = popup_intent_mismatch(
                str((assertions[0].get('target') or {}).get('intent') or ''),
                VisualStepReplanner._layer_text(layer_id, discovered_elements),
            )
            if mismatch:
                logging.getLogger(__name__).info('planner_v2 kept the model action over popup auto-resolution: %s', mismatch[:160])
                return actions, bindings
        return (
            [{'action': 'assert'}],
            [{'assertion_index': 1, 'locator': layer_id}],
        )

    @staticmethod
    def _layer_text(locator: str, discovered_elements: list[dict[str, Any]] | None) -> str:
        """Visible text of the discovered elements that belong to a dialog layer or live under a locator."""
        locator = str(locator or '').strip()
        if not locator:
            return ''
        parts: list[str] = []
        for element in discovered_elements or []:
            if not isinstance(element, dict):
                continue
            selector = str(element.get('selector') or '').strip()
            inside = (
                selector == locator
                or selector.startswith(f'{locator} > ')
                or str(element.get('blocking_layer_id') or '').strip() == locator
            )
            if not inside:
                continue
            for key in ('name', 'text', 'container_text'):
                value = str(element.get(key) or '').strip()
                if value:
                    parts.append(value)
        return ' '.join(parts)[:3000]

    @staticmethod
    def _filter_non_dom_assertion_bindings(
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        bindable_kinds = {'field_value', 'popup', 'element_state', 'collection', 'absence'}
        return [
            binding
            for binding in bindings
            if (
                not isinstance(binding.get('assertion_index'), int)
                or binding['assertion_index'] < 1
                or binding['assertion_index'] > len(assertions)
                or assertions[binding['assertion_index'] - 1].get('assert_kind') in bindable_kinds
            )
        ]

    @staticmethod
    def _is_selected_value_display(
        locator: str,
        discovered_elements: list[dict[str, Any]] | None,
    ) -> bool:
        """An attribute selector shared with the clicked option resolves to the value display once the menu closes."""
        choice_roles = {'option', 'menuitem', 'menuitemcheckbox', 'menuitemradio'}
        matches = [
            element
            for element in discovered_elements or []
            if isinstance(element, dict) and str(element.get('selector') or '').strip() == locator
        ]
        if not matches:
            return False
        return all(
            str(element.get('role') or '').strip().casefold() not in choice_roles
            and str(element.get('tag') or '').strip().casefold() != 'option'
            and not (element.get('top_layer') and int(element.get('group_size') or 0) > 1)
            for element in matches
        )

    @staticmethod
    def _validate_dropdown_value_binding(
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        prior_actions: list[dict[str, Any]],
        step_description: str,
        transition: dict[str, Any] | None = None,
        discovered_elements: list[dict[str, Any]] | None = None,
    ) -> None:
        selects_dropdown_option = GlobalTestPlanner._is_select_option_transition(
            step_description,
            transition,
        )
        latest_action = prior_actions[-1] if prior_actions else {}
        clicked_selector = (
            str(latest_action.get('selector') or '').strip()
            if str(latest_action.get('action') or '') == 'click'
            else ''
        )

        for binding in bindings:
            assertion_index = binding.get('assertion_index')
            if not isinstance(assertion_index, int) or not 1 <= assertion_index <= len(assertions):
                continue
            assertion = assertions[assertion_index - 1]
            bound_locator = str(binding.get('locator') or '').strip()
            if (
                selects_dropdown_option
                and clicked_selector
                and assertion.get('assert_kind') == 'field_value'
                and bound_locator == clicked_selector
                and not VisualStepReplanner._is_selected_value_display(bound_locator, discovered_elements)
            ):
                raise GlobalPlanError(
                    'Planner Vision cannot bind a dropdown selected-value assertion to the clicked option; '
                    'bind the control that displays the selected value.'
                )
            expected_value = assertion.get('expected', {}).get('value')
            value_display = (
                (assertion.get('assert_kind') == 'element_state' and assertion.get('operator') in {'equals', 'contains'})
                or (assertion.get('assert_kind') == 'field_value' and assertion.get('operator') in {'equals', 'contains', 'starts_with'})
            )
            if not value_display or not isinstance(expected_value, str) or not expected_value.strip():
                continue
            binding_locator = str(binding.get('locator') or '').strip()
            element = next((
                candidate
                for candidate in discovered_elements or []
                if isinstance(candidate, dict)
                and binding_locator in {
                    str(candidate.get('selector') or '').strip(),
                    str(candidate.get('group_selector') or '').strip(),
                }
            ), None)
            if element is None:
                continue
            observed_text = ' '.join(
                str(element.get(key) or '').strip()
                for key in ('text', 'name', 'value', 'container_text')
                if str(element.get(key) or '').strip()
            )
            if observed_text and expected_value.casefold() not in observed_text.casefold():
                raise GlobalPlanError(
                    'Planner Vision selected-value binding does not expose the expected selected value.'
                )

    @staticmethod
    def _validate_accessible_action(
        actions: list[dict[str, Any]],
        accessibility_snapshot: dict[str, Any],
        actionable_controls: list[dict[str, Any]] | None = None,
    ) -> None:
        action = actions[0] if len(actions) == 1 else {}
        selector = str(action.get('selector') or '').strip()
        role = str(action.get('role') or '').strip()
        accessible_name = str(action.get('accessible_name') or '').strip()
        discovered_selectors = {
            str(control.get('selector') or '').strip()
            for control in actionable_controls or []
            if isinstance(control, dict) and str(control.get('selector') or '').strip()
        }
        if selector and selector in discovered_selectors:
            action['role'] = None
            action['accessible_name'] = None
            return
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
            disabled = (matches[0].get('states') or {}).get('disabled')
            if disabled is True or str(disabled).strip().casefold() == 'true':
                raise GlobalPlanError(
                    'Accessibility action target is disabled; choose an enabled current actionable control.'
                )
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
            str(locator or '').strip(): element
            for element in discovered_elements
            if isinstance(element, dict)
            for locator in (element.get('selector'), element.get('group_selector'))
            if str(locator or '').strip()
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
            if locator != str(element.get('group_selector') or '').strip():
                raise GlobalPlanError(
                    'Planner Vision collection binding must use a discovered repeated-item group_selector.'
                )

    @staticmethod
    def _validate_visual_content_bindings(
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        discovered_elements: list[dict[str, Any]],
    ) -> None:
        elements_by_locator = {
            str(locator or '').strip(): element
            for element in discovered_elements
            if isinstance(element, dict)
            for locator in (element.get('selector'), element.get('group_selector'))
            if str(locator or '').strip()
        }
        for binding in bindings:
            assertion_index = binding.get('assertion_index')
            if not isinstance(assertion_index, int) or not 1 <= assertion_index <= len(assertions):
                continue
            target = assertions[assertion_index - 1].get('target')
            if not isinstance(target, dict) or target.get('visual_content') != 'image':
                continue
            locator = str(binding.get('locator') or '').strip()
            element = elements_by_locator.get(locator, {})
            if not bool(element.get('has_visual_content')):
                raise GlobalPlanError(
                    'Planner Vision image binding must identify an element with rendered image content, not a placeholder.'
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
        step_description: str = '',
        transition: dict[str, Any] | None = None,
        page_metrics: dict[str, Any] | None = None,
    ) -> None:
        action = actions[0] if len(actions) == 1 else {}
        action_name = str(action.get('action') or '').strip()
        state_changing_actions = {'click', 'double_click', 'right_click', 'fill', 'press', 'select', 'navigate'}
        completed_state_change = any(
            isinstance(prior_action, dict)
            and prior_action.get('status') == 'completed'
            and str(prior_action.get('action') or '').strip() in state_changing_actions
            for prior_action in prior_actions
        )
        if (
            action_name in state_changing_actions
            and completed_state_change
            and GlobalTestPlanner._is_select_option_transition(step_description, transition)
        ):
            raise GlobalPlanError(
                'Planner Vision step already completed its select-option transition; only assertion or read-only recovery is allowed within this step.'
            )
        selector = str(action.get('selector') or '').strip()
        role = str(action.get('role') or '').strip().casefold()
        accessible_name = str(action.get('accessible_name') or '').strip()
        locator_identity = f'css:{selector}' if selector else f'ax:{role}:{accessible_name}' if role and accessible_name else ''
        if action_name not in {'click', 'double_click', 'right_click', 'hover', 'fill', 'press', 'select', 'scroll'} or not locator_identity:
            return

        def prior_identity(prior_action: dict[str, Any]) -> str:
            prior_selector = str(prior_action.get('selector') or '').strip()
            if prior_selector:
                return f'css:{prior_selector}'
            prior_role = str(prior_action.get('role') or '').strip().casefold()
            prior_name = str(prior_action.get('accessible_name') or '').strip()
            return f'ax:{prior_role}:{prior_name}' if prior_role and prior_name else ''

        # A selector that merely failed to resolve (auto-hidden or re-indexed control) is not a
        # proven-wrong choice; retrying it after re-observation is legitimate.
        repeatable_prior = [
            prior_action
            for prior_action in prior_actions
            if isinstance(prior_action, dict) and 'did not resolve' not in str(prior_action.get('error') or '')
        ]
        previous_action = repeatable_prior[-1] if repeatable_prior else {}
        immediate_repeat = (
            str(previous_action.get('action') or '').strip() == action_name
            and prior_identity(previous_action) == locator_identity
        )
        repeated_earlier = any(
            str(prior_action.get('action') or '').strip() == action_name
            and prior_identity(prior_action) == locator_identity
            for prior_action in repeatable_prior
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
        if action_name == 'scroll' and immediate_repeat:
            # Paging through a list means scrolling the same container again; allow it while the page metrics
            # still report content left to scroll, otherwise a repeated scroll is the loop this rule prevents.
            containers = (page_metrics or {}).get('scroll_containers') or []
            remaining = [
                container for container in containers
                if isinstance(container, dict) and float(container.get('remaining') or 0) > 1
                and (not selector or str(container.get('selector') or '').strip() in {selector, ''} or selector.endswith(str(container.get('selector') or '').strip()[-40:]))
            ]
            if remaining or (not selector and containers):
                return
        reusable_after_intervening_action = action_name == 'scroll' or bool(
            selected_control is not None and selected_control.get('blocking_layer') is True
        )
        if immediate_repeat or (repeated_earlier and not reusable_after_intervening_action):
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
    def _bind_target_camera_thumbnail(
        bindings: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
        execution_resources: list[dict[str, Any]],
        step_description: str,
    ) -> list[dict[str, Any]]:
        """Bind an unbound image assertion about the configured target camera to its rendered card.

        Verify-only steps never run the runtime binders, so the model has to pick the card itself and often
        binds it before the thumbnail rendered. The card named after the camera with rendered visual content
        is objective evidence and needs no model judgement.
        """
        names = default_device_camera_names(execution_resources)
        if not names or not refers_to_target_device(step_description, names):
            return bindings
        bound_indexes = {binding.get('assertion_index') for binding in bindings if isinstance(binding, dict)}
        resolved = list(bindings)
        wanted = [name.casefold() for name in names]
        for index, assertion in enumerate(assertions, start=1):
            target = assertion.get('target') if isinstance(assertion.get('target'), dict) else {}
            if (
                index in bound_indexes
                or assertion.get('assert_kind') != 'element_state'
                or assertion.get('operator') != 'exists'
                or target.get('visual_content') != 'image'
                or str(target.get('locator') or '').strip()
            ):
                continue
            cards = [
                control for control in actionable_controls
                if isinstance(control, dict)
                and not is_text_input(control)
                and control.get('has_visual_content') is True
                and str(control.get('selector') or '').strip()
                and any(name in ' '.join(str(control.get('name') or '').split()).casefold() for name in wanted)
            ]
            selectors = sorted({str(control.get('selector')).strip() for control in cards})
            if len(selectors) != 1:
                named = sum(
                    1 for control in actionable_controls
                    if isinstance(control, dict) and any(name in ' '.join(str(control.get('name') or '').split()).casefold() for name in wanted)
                )
                logging.getLogger(__name__).info(
                    'planner_v2 target camera thumbnail rule declined: cameras=%s named_controls=%s rendered_cards=%s',
                    names, named, len(selectors),
                )
                continue
            resolved.append({'assertion_index': index, 'locator': selectors[0], 'selection_basis': 'configured target camera card with rendered thumbnail'})
            logging.getLogger(__name__).info('planner_v2 bound the target camera thumbnail assertion to %s', selectors[0][-60:])
        return resolved

    @staticmethod
    def _bare_assert_on_action_step(step_description: str, prior_actions: list[dict[str, Any]]) -> bool:
        """True when a step that literally starts with a state-changing verb has performed no action yet.

        "Click the Deactivate button" cannot be satisfied by observing the page: with a lenient assertion the
        model (and later the action cache) would skip the click entirely. Verbs that describe idempotent
        inspection or opening (open, expand, locate, verify) are left to the model's judgement.
        """
        if any(
            isinstance(action, dict) and action.get('status') == 'completed' and str(action.get('action') or '') not in {'assert', ''}
            for action in prior_actions
        ):
            return False
        first_word = re.match(r'\s*([A-Za-z]+)', str(step_description or ''))
        if not first_word:
            return False
        acting_verbs = {
            'click', 'press', 'fill', 'type', 'enter', 'select', 'choose', 'navigate', 'search', 'toggle', 'switch',
            'scroll', 'hover', 'confirm', 'submit', 'upload', 'delete', 'remove', 'deactivate', 'activate', 'drag', 'tap',
        }
        return first_word.group(1).casefold() in acting_verbs

    @staticmethod
    def _no_completed_action_hint(step_description: str, prior_actions: list[dict[str, Any]]) -> str:
        """Remind the model that a step described as an action must perform it before asserting its outcome."""
        if any(isinstance(action, dict) and action.get('status') == 'completed' for action in prior_actions):
            return ''
        first_word = re.match(r'\s*([A-Za-z]+)', str(step_description or ''))
        action_verbs = {'click', 'select', 'fill', 'type', 'enter', 'open', 'expand', 'hover', 'press', 'choose', 'navigate', 'search', 'scroll', 'toggle', 'switch', 'confirm', 'submit', 'upload', 'drag'}
        if not first_word or first_word.group(1).casefold() not in action_verbs:
            return ''
        return (
            ' No action has been completed in this step yet: perform the action the step describes '
            f'("{str(step_description or "").strip()[:80]}") before asserting its outcome.'
        )

    @staticmethod
    def _missing_target_camera_hint(
        step_description: str,
        execution_resources: list[dict[str, Any]],
        discovered_elements: list[dict[str, Any]],
    ) -> str:
        """Tell the model how to reach the configured target camera when no discovered element names it."""
        names = default_device_camera_names(execution_resources)
        if not names or not refers_to_target_device(step_description, names):
            return ''
        shown = ' '.join(
            ' '.join(str(element.get('name') or element.get('text') or '').split()).casefold()
            for element in discovered_elements
            if isinstance(element, dict) and not is_text_input(element)
        )
        if any(name.casefold() in shown for name in names):
            return ''
        site = default_device_site(execution_resources)
        where = (
            f' Its cameras are listed under the site group "{site}": clear any search text, then search "{site}" or expand that group.'
            if site else
            ' The search box may filter by site rather than by camera name: clear any search text, then expand the site groups one at a time or scroll the camera list.'
        )
        return (
            f' The target camera {", ".join(names)} is not among the discovered controls (a search box showing that text is not the camera).'
            f'{where} When the camera card is visible, wait for its thumbnail to render before asserting.'
        )

    @staticmethod
    def _prefer_environment_device_control(
        actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
        execution_resources: list[dict[str, Any]],
        step_description: str,
    ) -> list[dict[str, Any]]:
        """Redirect a click on a neighbouring camera card to the environment's default test camera.

        Applies only when the step speaks of the default/target device or camera, the clicked control sits
        in a repeated group (the camera list), and a card named after a configured camera is visible in that
        same group. A hidden target camera is left to the model (it may need to search or expand a site).
        """
        camera_names = default_device_camera_names(execution_resources)
        action = actions[0] if len(actions) == 1 else {}
        selector = str(action.get('selector') or '').strip()
        if not camera_names or str(action.get('action') or '') != 'click' or not selector or not refers_to_target_device(step_description, camera_names):
            return actions
        clicked = next((c for c in actionable_controls if isinstance(c, dict) and str(c.get('selector') or '').strip() == selector), None)
        if clicked is None or is_text_input(clicked):
            return actions
        wanted = {name.casefold() for name in camera_names}
        clicked_name = ' '.join(str(clicked.get('name') or '').split()).casefold()
        if any(name in clicked_name for name in wanted):
            return actions
        group = str(clicked.get('group_selector') or '').strip()
        parent = selector.rsplit(' > ', 1)[0] if ' > ' in selector else ''
        siblings = [
            control
            for control in actionable_controls
            if isinstance(control, dict)
            and str(control.get('selector') or '').strip() != selector
            and (
                (group and str(control.get('group_selector') or '').strip() == group)
                or (parent and str(control.get('selector') or '').startswith(f'{parent} > '))
            )
        ]
        targets = [
            control for control in siblings
            if not is_text_input(control)
            and any(name in ' '.join(str(control.get('name') or '').split()).casefold() for name in wanted)
        ]
        if len({str(control.get('selector') or '') for control in targets}) != 1:
            return actions
        target = targets[0]
        logging.getLogger(__name__).info(
            'planner_v2 redirected a camera click from %r to the configured test camera %r',
            clicked_name[:40], str(target.get('name') or '')[:40],
        )
        return [{**action, 'selector': str(target.get('selector') or '').strip(), 'role': None, 'accessible_name': None}]

    @staticmethod
    def _resolve_visible_record_action(
        actions: list[dict[str, Any]],
        actionable_controls: list[dict[str, Any]],
        execution_resources: list[dict[str, Any]],
        page_metrics: dict[str, Any] | None = None,
        verified_predecessors: list[dict[str, Any]] | None = None,
        correlates_resource: str = '',
        assertions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        resource_type = correlates_resource.strip()
        if not resource_type or not any(
            isinstance(resource, dict) and str(resource.get('resource_type') or '').strip() == resource_type
            for resource in execution_resources
        ):
            return actions
        action = actions[0] if len(actions) == 1 else {}
        action_name = str(action.get('action') or '').strip()
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
        best_selectors = {selector for score, selector in scored_controls if score == max_score}
        verifies_visible_detail = (
            len(assertions or []) == 1
            and assertions[0].get('assert_kind') == 'element_state'
            and assertions[0].get('operator') == 'exists'
            and expects_true((assertions[0].get('expected') or {}).get('value'))
        )
        if (
            action_name == 'scroll'
            and max_score >= required_score
            and len(best_selectors) == 1
            and verifies_visible_detail
        ):
            return [{
                'action': 'assert',
                'assertion_bindings': [{
                    'assertion_index': 1,
                    'locator': next(iter(best_selectors)),
                }],
            }]
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
        if action_name in {'fill', 'press', 'select', 'select_option', 'scroll', 'wait'}:
            return actions
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
        blocking_assertion_locators = blocking_locators | {
            str(layer_id).strip()
            for layer_id in state.get('active_layer_ids', [])
            if str(layer_id).strip()
        }
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
        active_layer_ids = [
            str(layer_id).strip()
            for layer_id in state.get('active_layer_ids', [])
            if str(layer_id).strip()
        ]

        layer_member_locators = {
            str(control.get('selector') or '').strip()
            for control in actionable_controls
            if isinstance(control, dict)
            and str(control.get('blocking_layer_id') or '').strip() in active_layer_ids
            and str(control.get('selector') or '').strip()
        }

        def _binds_inside_active_layer(locator: str) -> bool:
            return (
                locator in blocking_assertion_locators
                or locator in layer_member_locators
                or any(locator.startswith(f'{layer_id} > ') for layer_id in active_layer_ids)
            )

        if (
            len(actions) == 1
            and str(actions[0].get('action') or '').strip() == 'assert'
            and bindings
            and all(_binds_inside_active_layer(str(binding.get('locator') or '').strip()) for binding in bindings)
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

        return AITestModelConfig.objects.filter(role='planner_vision', is_active=True).order_by('id').first()

    async def _get_active_model_config(self):
        return await sync_to_async(self._load_active_model_config)()

    @staticmethod
    def _load_fallback_model_configs(primary) -> list:
        close_old_connections()
        from apps.ai_testing.models import AITestModelConfig

        primary_id = getattr(primary, 'id', None)
        return [
            config
            for config in AITestModelConfig.objects.filter(role='planner_vision', is_active=True).order_by('id')
            if config.id != primary_id
        ]

    async def _get_fallback_model_configs(self, primary) -> list:
        """Other active planner_vision models, in configuration order; [] when none or when no database is reachable."""
        try:
            return await sync_to_async(self._load_fallback_model_configs)(primary)
        except Exception as error:
            logging.getLogger(__name__).info('planner_v2 fallback vision models unavailable: %s', type(error).__name__)
            return []

    async def _complete_with_failover(self, config, messages, assertion_count: int):
        """Call the primary vision model and, on a provider outage, each other active planner_vision model in turn.

        Enabling a second planner_vision model in the AI model configuration is what turns this on; with a single
        active model the behaviour is unchanged and the runtime's transient back-off still applies.
        """
        candidates = [config, *await self._get_fallback_model_configs(config)]
        last_error: BaseException | None = None
        for index, candidate in enumerate(candidates):
            try:
                return await asyncio.wait_for(
                    OpenAICompatibleClient.complete(
                        candidate,
                        messages,
                        context=LLMCallContext(
                            component='ai_testing',
                            operation='planner_vision',
                        ),
                        enable_thinking=True,
                        tools=[_action_submission_tool(assertion_count)],
                        tool_choice={'type': 'function', 'function': {'name': 'submit_browser_actions'}},
                    ),
                    timeout=settings.TIMEOUTS_AI_REQUEST,
                )
            except Exception as error:  # noqa: BLE001 - classified below
                last_error = error
                if index + 1 >= len(candidates) or not is_transient_llm_error(error):
                    raise
                logging.getLogger(__name__).warning(
                    'planner_v2 vision model %s unavailable (%s); failing over to %s',
                    getattr(candidate, 'name', '?'), type(error).__name__, getattr(candidates[index + 1], 'name', '?'),
                )
        raise last_error  # pragma: no cover - loop always returns or raises

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
        prompt_content = await sync_to_async(self._load_active_prompt_content)('planner_text')
        devices = await sync_to_async(self._load_environment_devices)(environment_configuration_id)
        device_goal = refers_to_target_device(task_description, default_device_camera_names(devices))
        context_fingerprint = self._plan_context_fingerprint(prompt_content, devices if device_goal else [])
        self.last_context_fingerprint = context_fingerprint
        self.last_plan_source = 'model'
        if use_cache:
            cached_steps = await sync_to_async(self._load_cached_plan_steps)(
                task_description,
                environment_configuration_id,
                context_fingerprint,
                allow_legacy=not device_goal,
            )
            if cached_steps:
                cached_response = {
                    'choices': [{'message': {'tool_calls': [{'function': {
                        'name': 'submit_execution_plan',
                        'arguments': json.dumps({'steps': cached_steps}, ensure_ascii=True),
                    }}]}}],
                }
                try:
                    normalized = self.normalize_response(
                        cached_response,
                        environment_configuration_id,
                        task_description,
                        require_transition=True,
                    )
                except GlobalPlanError:
                    pass
                else:
                    self.last_plan_source = 'cache'
                    return normalized

        configs = await self._get_active_model_configs()
        if not configs:
            raise GlobalPlanError('未配置可用的 Planner 模型。')

        if not prompt_content:
            raise GlobalPlanError('未配置可用的 Planner 文本提示词。')
        resources = await sync_to_async(self._load_data_factory_resources)(environment_configuration_id)
        messages = self._build_messages(task_description, environment_configuration_id, prompt_content, resources, devices)
        last_error: GlobalPlanError | None = None
        for config in configs:
            retry_messages = list(messages)
            for attempt in range(5):
                try:
                    response = await asyncio.wait_for(
                        OpenAICompatibleClient.complete(
                            config,
                            retry_messages,
                            context=LLMCallContext(
                                component='ai_testing',
                                operation='planner_text',
                            ),
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
                    return self.normalize_response(
                        response,
                        environment_configuration_id,
                        task_description,
                        require_transition=True,
                    )
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
        environment_devices: list[dict[str, object]] | None = None,
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
                    'Every browser step must include transition. Use kind="select_option" with value set to the requested option, kind="filter_results" with value set to the query identifier and result_presence="present" or "absent", or kind="generic" for all other transitions. These fields are semantic contracts and must not depend on the language used in description. '
                    'For a state change that opens menus or dialogs and requires additional choices or confirmation, plan every intermediate transition: open the control and assert its options, select the requested option and assert the next dialog, make required dialog selections and assert them, then confirm and only then assert the committed final state. Never assert the final state before the commit action. '
                    'When the goal requires both updating a field and reaching a final status, plan and verify the field update before the irreversible status transition. Do not assume a status transition will expose a field dialog; only handle such a dialog during visual replanning when current page evidence proves it exists. '
                    'Never create conditional steps such as "if a dialog appears" because execution plans do not have conditional branches. Plan only states required by the goal; assertion-driven replanning will handle a blocking dialog when current page evidence proves it exists. '
                    'Browser allowed_capabilities may contain only browser.navigate, browser.inspect, browser.act, and browser.capture. '
                    'Configured environment authentication is completed by the runtime before the plan begins; do not output login steps or login assertions. '
                    'Do not add a step solely to establish a generic post-login landing page; begin with the first goal-specific user-visible transition. '
                    'Every fill, press, and select action must include a non-empty value. '
                    'Use fill only when the selected actionable control has editable=true; use click, press, or select for readonly controls. '
                    'After selecting an option from a dropdown or menu, assert the selected control value with field_value starts_with, or its displayed selected text with element_state equals/contains/matches. When the selection opens a required transaction dialog, assert only that dialog in the selection step and defer the committed selected value until the later confirmation step. The expected string must be the requested option; the existence of an unrelated control does not prove selection. '
                    'Every assertion must use action="assert" and include assert_kind, target, operator, '
                    'expected, and evidence_requirements. Use only registered generic kinds: text, field_value, '
                    'popup, media, video, stream_state, playback, element_state, url, network, '
                    'api_resource, command_result, download_task, collection, absence, theme. '
                    'For phone-number field_value assertions, use operator="phone_digits_equals" so UI formatting such as spaces, parentheses, or hyphens does not change the verified number. Use equals for non-phone field values. '
                    'field_value compares the value a user entered or selected and is empty for an untouched input; verify an input\'s placeholder text or a control\'s visible label with element_state equals/contains instead. '
                    'Do not treat names from the user goal as exact rendered UI text unless the goal explicitly requires that wording. After selecting a mode or option, assert the newly introduced control or panel needed by the next transition instead of repeating the selected label as a text assertion. '
                    'Use element_state or collection for static UI elements such as images, thumbnails, cards, and controls. For an image or thumbnail that must be loaded and displayed normally, use element_state exists and set target.visual_content="image"; visibility alone does not prove image content loaded. element_state otherwise supports objective visibility through exists/not_exists and visible text through equals/contains/matches; never assert inferred CSS states such as selected, active, highlighted, or focused. After selecting a record, assert an objectively observable detail element, dialog, text, or URL introduced by that transition. '
                    'Collection assertions compare the observed item count: use exists/not_exists or a numeric expected.value with equals/greater_than/less_than; never use contains or descriptive count text. The target intent must describe the repeated items, not their parent container, summary, loading element, or empty-state placeholder. '
                    'For page-bound element_state, collection, and popup assertions, use target.intent for the semantic target; the Visual Planner will bind a runtime locator after observing the page. '
                    'For element_state exists assertions that verify a visible named option or control, also set target.text to the exact visible label required by the goal. target.text is language-independent evidence metadata, not a selector. '
                    'To verify that filtering or searching returns no result for a requested identifier, use text with operator="not_contains", expected.value set to that identifier, and evidence_requirements=["dom_snapshot"]. Do not use absence for a result that no longer has a discoverable locator. '
                    'Use media or video only for native audio/video elements and compare native fields such as paused, ended, readyState, currentTime, videoWidth, videoHeight, or currentSrc. '
                    'To prove that a live camera, WebRTC, or live video stream is active, use stream_state with time-progress or changing-canvas evidence. '
                    'Use playback with time-progress evidence only for recorded playback, timeline navigation, or seeking. Never use a descriptive media/video expected.value such as playing. '
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
                    + (
                        '\n\nEnvironment test devices (the goal\'s "default test device" / "target camera" means these). '
                        'Name the camera and, when given, its site group explicitly in the step descriptions. Prefer the '
                        'search box: "type the site name X into the camera list search box, then locate camera Y among the '
                        'results"; expand the site group only when the list has no search box. Never leave the camera unnamed:\n'
                        + json.dumps([resource.get('resource') for resource in environment_devices if isinstance(resource, dict)], ensure_ascii=True)
                        if environment_devices else ''
                    )
                ),
            },
        ]

    @staticmethod
    def normalize_response(
        response: dict[str, Any],
        configuration_id: int | None,
        task_description: str = '',
        *,
        require_transition: bool = False,
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
                # A "locate and verify" step still has to be able to act (expand a group, dismiss a stray layer):
                # inspect-only steps dead-end whenever the state is not already on screen. Runtime validators,
                # not missing capabilities, keep actions in check.
                for required_capability in ('browser.inspect', 'browser.act'):
                    if required_capability not in allowed_capabilities:
                        allowed_capabilities.append(required_capability)
                if raw_step.get('verification_required', True) is False:
                    raise GlobalPlanError(
                        f'Planner 浏览器步骤 {index} 禁止关闭验证；每个状态转换都必须声明立即后置断言。'
                    )
                assertions = GlobalTestPlanner._normalize_assertions(raw_step.get('assertions'), index)
                transition = GlobalTestPlanner._normalize_transition(raw_step.get('transition'), index)
                if require_transition and transition is None:
                    raise GlobalPlanError(
                        f'Planner 浏览器步骤 {index} 缺少结构化 transition。'
                    )
                GlobalTestPlanner._remove_redundant_selection_label_assertion(assertions, transition)
                GlobalTestPlanner._remove_clicked_control_label_assertion(description, assertions)
                GlobalTestPlanner._normalize_dropdown_selection_operator(description, assertions, transition)
                GlobalTestPlanner._validate_dropdown_selection_assertion(
                    description,
                    assertions,
                    index,
                    transition,
                )
                GlobalTestPlanner._validate_search_result_absence_assertion(
                    description,
                    assertions,
                    index,
                    transition,
                )
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
                        transition=transition,
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
    def _normalize_dropdown_selection_operator(
        description: str,
        assertions: list[dict[str, Any]],
        transition: dict[str, Any] | None = None,
    ) -> None:
        selects_dropdown_option = GlobalTestPlanner._is_select_option_transition(description, transition)
        if not selects_dropdown_option:
            return
        for assertion in assertions:
            if assertion.get('assert_kind') == 'field_value' and assertion.get('operator') == 'equals':
                assertion['operator'] = 'starts_with'

    @staticmethod
    def _remove_clicked_control_label_assertion(description: str, assertions: list[dict[str, Any]]) -> None:
        """Drop an existence assertion on the very control the step clicks.

        "Click the View Playback button" followed by asserting that "View Playback" exists proves nothing about
        the transition and is impossible once the click navigates away. Kept only when it is the sole assertion.
        """
        text = str(description or '')
        if not re.match(r'\s*(click|tap|press|double[- ]?click)\b', text, flags=re.IGNORECASE):
            return
        lowered = text.casefold()
        redundant = [
            assertion
            for assertion in assertions
            if assertion.get('assert_kind') == 'element_state'
            and assertion.get('operator') == 'exists'
            and str(((assertion.get('target') or {}) if isinstance(assertion.get('target'), dict) else {}).get('text') or '').strip()
            and str(assertion['target']['text']).strip().casefold() in lowered
        ]
        if redundant and len(redundant) < len(assertions):
            for assertion in redundant:
                logging.getLogger(__name__).info(
                    'planner_v2 dropped an assertion on the clicked control label %r', str(assertion['target']['text'])[:40],
                )
            assertions[:] = [assertion for assertion in assertions if assertion not in redundant]

    @staticmethod
    def _remove_redundant_selection_label_assertion(
        assertions: list[dict[str, Any]],
        transition: dict[str, Any] | None,
    ) -> None:
        if not transition or transition.get('kind') != 'select_option':
            return
        selected_value = str(transition.get('value') or '').strip().casefold()
        if not selected_value:
            return
        introduced_control_exists = any(
            assertion.get('assert_kind') in {'element_state', 'popup'}
            and assertion.get('operator') == 'exists'
            and expects_true((assertion.get('expected') or {}).get('value'))
            and selected_value in str((assertion.get('target') or {}).get('intent') or '').casefold()
            for assertion in assertions
        )
        if not introduced_control_exists:
            return
        assertions[:] = [
            assertion
            for assertion in assertions
            if not (
                assertion.get('assert_kind') in {'field_value', 'element_state'}
                and isinstance((assertion.get('expected') or {}).get('value'), str)
                and str((assertion.get('expected') or {}).get('value') or '').strip().casefold() == selected_value
            )
        ]

    @staticmethod
    def _validate_search_result_absence_assertion(
        description: str,
        assertions: list[dict[str, Any]],
        step_index: int,
        transition: dict[str, Any] | None = None,
    ) -> None:
        verifies_absent_results = (
            transition is not None
            and transition.get('kind') == 'filter_results'
            and transition.get('result_presence') == 'absent'
        )
        if not verifies_absent_results and 'search' not in description.casefold():
            return
        if any(assertion.get('assert_kind') == 'absence' for assertion in assertions):
            raise GlobalPlanError(
                f'Planner 浏览器步骤 {step_index} 不能用 absence 验证搜索结果不存在；'
                '请使用 text not_contains 和 dom_snapshot 验证目标标识不在结果页面中。'
            )

    @staticmethod
    def _validate_dropdown_selection_assertion(
        description: str,
        assertions: list[dict[str, Any]],
        step_index: int,
        transition: dict[str, Any] | None = None,
    ) -> None:
        description_text = description.casefold()
        selects_dropdown_option = GlobalTestPlanner._is_select_option_transition(description, transition)
        if not selects_dropdown_option:
            return

        expected_selection = str((transition or {}).get('value') or '').strip().casefold()

        def _proves(assertion: dict[str, Any]) -> bool:
            if (
                assertion.get('assert_kind') not in {'field_value', 'element_state'}
                or assertion.get('operator') not in {'equals', 'contains', 'starts_with', 'matches'}
                or not isinstance((assertion.get('expected') or {}).get('value'), str)
            ):
                return False
            expected_text = str((assertion.get('expected') or {}).get('value') or '').strip().casefold()
            if not expected_text:
                return False
            # The requested option itself, or a display text the step description declares (a control may
            # abbreviate the chosen option, e.g. "Magic Search V2" shown as "Magic V2").
            return expected_text == expected_selection or expected_text in description_text

        proves_selected_value = any(_proves(assertion) for assertion in assertions)
        proves_transaction_dialog = any(
            assertion.get('assert_kind') == 'popup'
            or (
                assertion.get('assert_kind') == 'element_state'
                and assertion.get('operator') == 'exists'
                and any(
                    term in str((assertion.get('target') or {}).get('intent') or '').casefold()
                    for term in ('dialog', 'modal', 'chooser')
                )
            )
            for assertion in assertions
        )
        if proves_transaction_dialog:
            if proves_selected_value:
                raise GlobalPlanError(
                    f'Planner browser step {step_index} cannot assert a committed selected value before the transaction dialog is confirmed.'
                )
            return
        if not proves_selected_value:
            raise GlobalPlanError(
                f'Planner 浏览器步骤 {step_index} 选择下拉选项后未验证所选值；'
                '请使用 field_value 或 element_state 文本断言验证描述中的目标选项。'
            )

    @staticmethod
    def _normalize_transition(raw_transition: object, step_index: int) -> dict[str, Any] | None:
        if raw_transition is None:
            return None
        if not isinstance(raw_transition, dict):
            raise GlobalPlanError(f'Planner 浏览器步骤 {step_index} 的 transition 格式无效。')
        kind = str(raw_transition.get('kind') or '').strip()
        if kind not in {'generic', 'select_option', 'filter_results'}:
            raise GlobalPlanError(f'Planner 浏览器步骤 {step_index} 的 transition.kind 无效。')
        transition = {'kind': kind}
        value = str(raw_transition.get('value') or '').strip()
        if kind in {'select_option', 'filter_results'} and not value:
            raise GlobalPlanError(f'Planner 浏览器步骤 {step_index} 的 transition.value 不能为空。')
        if value:
            transition['value'] = value
        if kind == 'filter_results':
            result_presence = str(raw_transition.get('result_presence') or '').strip()
            if result_presence not in {'present', 'absent'}:
                raise GlobalPlanError(
                    f'Planner 浏览器步骤 {step_index} 的 transition.result_presence 无效。'
                )
            transition['result_presence'] = result_presence
        return transition

    @staticmethod
    def _is_select_option_transition(
        description: str,
        transition: dict[str, Any] | None,
    ) -> bool:
        if transition is not None:
            return transition.get('kind') == 'select_option'
        description_text = description.casefold()
        inferred = (
            any(verb in description_text for verb in ('select', 'choose'))
            and 'option' in description_text
            and any(control in description_text for control in ('dropdown', 'menu'))
        )
        if inferred:
            logging.getLogger(__name__).info(
                'planner keyword fallback: select_option inferred from description without a structured transition'
            )
        return inferred

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
                target_text = json.dumps(assertion_payload.get('target', {}), ensure_ascii=False).casefold()
                if (
                    assert_kind.strip() == 'field_value'
                    and assertion_payload.get('operator') == 'equals'
                    and any(term in target_text for term in ('phone', 'telephone', 'mobile', '电话', '手机'))
                ):
                    assertion_payload['operator'] = 'phone_digits_equals'
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
    def _plan_context_fingerprint(prompt_content: str, environment_devices: list[dict[str, object]] | None) -> str:
        """Identify the planning context a cached plan was generated under.

        The prompt text always participates; environment devices participate only for goals that speak of the
        default/target device, so a device configuration change regenerates exactly the plans that depend on it
        and leaves proven plans for unrelated goals untouched.
        """
        payload = {
            'contract_version': PLAN_CONTRACT_VERSION,
            'prompt': hashlib.sha256(str(prompt_content or '').encode('utf-8')).hexdigest(),
            'devices': [resource.get('resource') for resource in environment_devices or [] if isinstance(resource, dict)],
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode('utf-8')).hexdigest()[:32]

    @staticmethod
    def _load_cached_plan_steps(
        task_description: str,
        environment_configuration_id: int | None,
        context_fingerprint: str = '',
        allow_legacy: bool = True,
    ) -> list[dict[str, Any]]:
        """Latest initial plan for this goal and environment, generated under the same planning context.

        Plans persisted before fingerprints existed carry none; they stay valid for ordinary goals
        (``allow_legacy``) but a goal about the target device must be replanned once with the device names.
        """
        close_old_connections()
        from apps.ai_testing.models import AIExecutionPlanRevision

        revisions = list(
            AIExecutionPlanRevision.objects.filter(
                source_goal=task_description,
                reason='initial',
                execution_record__environment_configuration_id=environment_configuration_id,
            )
            .select_related('execution_record')
            .order_by('-created_at', '-id')[:25]
        )

        def proven(candidate) -> bool:
            return str(getattr(candidate.execution_record, 'status', '') or '') == 'passed'

        def acceptable(candidate) -> bool:
            if not isinstance(candidate.plan, dict):
                return False
            stored = str(candidate.plan.get('context_fingerprint') or '')
            if not context_fingerprint or stored == context_fingerprint:
                return True
            # A plan whose execution passed is proven for an ordinary goal even if the planning contract has
            # moved on; device goals must replan so the plan reflects the current device configuration.
            return allow_legacy and (not stored or proven(candidate))

        candidates = [candidate for candidate in revisions if acceptable(candidate)]
        # Prefer the newest proven plan; a freshly generated plan that failed must not shadow one that passed.
        revision = next((candidate for candidate in candidates if proven(candidate)), None) or (candidates[0] if candidates else None)
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
    def _load_environment_devices(configuration_id: int | None) -> list[dict[str, object]]:
        close_old_connections()
        if configuration_id is None:
            return []
        from apps.core.models import EnvironmentConfiguration

        configuration = EnvironmentConfiguration.objects.filter(id=configuration_id).first()
        return environment_device_resources(configuration) if configuration is not None else []

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