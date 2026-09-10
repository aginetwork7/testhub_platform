import inspect
import json

from django.test import SimpleTestCase
from types import SimpleNamespace

from apps.core.browser_auth import resolve_browser_login
from apps.ai_testing.execution.capabilities import allowed_browser_actions
from apps.ai_testing.global_planner import GlobalPlanError, GlobalTestPlanner
from apps.ai_testing.views import has_canonical_freeform_plan


class GlobalTestPlannerTests(SimpleTestCase):
    def test_planner_retry_feedback_includes_specific_contract_error(self) -> None:
        source = inspect.getsource(GlobalTestPlanner.create_plan)

        self.assertIn('previous plan violated this contract', source)
        self.assertIn('Correct that specific violation', source)
        self.assertIn('Rebuild the full ordered plan rather than appending a repair step', source)
        self.assertNotIn('max_tokens=', source)

    def test_cached_plan_is_revalidated_without_reusing_execution_results(self) -> None:
        create_source = inspect.getsource(GlobalTestPlanner.create_plan)
        cache_source = inspect.getsource(GlobalTestPlanner._load_cached_plan_steps)

        self.assertIn('return self.normalize_response(', create_source)
        self.assertIn("reason='initial'", cache_source)
        self.assertIn('environment_configuration_id=environment_configuration_id', cache_source)
        self.assertNotIn('attempt', cache_source)
        self.assertNotIn('evidence', cache_source)
        self.assertNotIn('quality', cache_source)
        self.assertIn('require_transition=True', create_source)

    def test_strict_normalization_rejects_browser_step_without_transition(self) -> None:
        response = {
            'choices': [{'message': {'tool_calls': [{'function': {
                'name': 'submit_execution_plan',
                'arguments': json.dumps({'steps': [{
                    'executor': 'browser',
                    'description': 'Verify current page',
                    'allowed_capabilities': ['browser.inspect'],
                    'assertions': [{
                        'action': 'assert',
                        'assert_kind': 'text',
                        'target': {'page': 'current'},
                        'operator': 'contains',
                        'expected': {'value': 'Ready'},
                        'evidence_requirements': ['dom_snapshot'],
                    }],
                }]})
            }}]}}],
        }

        with self.assertRaisesRegex(GlobalPlanError, '缺少结构化 transition'):
            GlobalTestPlanner.normalize_response(
                response,
                configuration_id=None,
                require_transition=True,
            )

    def test_canonical_freeform_plan_accepts_valid_persisted_steps(self) -> None:
        planned_steps = [{
            'executor': 'browser',
            'description': 'Verify current page',
            'allowed_capabilities': ['browser.inspect'],
            'transition': {'kind': 'generic'},
            'assertions': [{
                'action': 'assert',
                'assert_kind': 'text',
                'target': {'page': 'current'},
                'operator': 'contains',
                'expected': {'value': 'Ready'},
                'evidence_requirements': ['dom_snapshot'],
            }],
        }]

        self.assertTrue(has_canonical_freeform_plan(planned_steps, None, 'Verify current page'))

    def test_canonical_freeform_plan_rejects_step_without_transition(self) -> None:
        planned_steps = [{
            'executor': 'browser',
            'description': 'Verify current page',
            'allowed_capabilities': ['browser.inspect'],
            'assertions': [{
                'action': 'assert',
                'assert_kind': 'text',
                'target': {'page': 'current'},
                'operator': 'contains',
                'expected': {'value': 'Ready'},
                'evidence_requirements': ['dom_snapshot'],
            }],
        }]

        self.assertFalse(has_canonical_freeform_plan(planned_steps, None, 'Verify current page'))

    def test_browser_login_uses_global_environment_configuration(self) -> None:
        configuration = SimpleNamespace(
            web_url='https://example.test',
            runtime_settings={'ai_testing_browser': {'login_path': '/login'}},
            auth_profiles={
                'tester': {
                    'is_default_role': True,
                    'username': 'tester@example.test',
                    'password': 'secret',
                },
            },
        )

        login = resolve_browser_login(configuration)

        self.assertIsNotNone(login)
        self.assertEqual(login.login_url, 'https://example.test/login')
        self.assertEqual(login.username, 'tester@example.test')

    def test_allowed_browser_actions_follow_capability_boundary(self) -> None:
        actions = allowed_browser_actions(['browser.act', 'browser.inspect'])

        self.assertNotIn('navigate', actions)
        self.assertEqual(actions[-1], 'assert')

    def test_visual_planner_rejects_background_action_while_dialog_blocks_page(self) -> None:
        actions = [{'action': 'click', 'selector': '#background'}]
        controls = [
            {'selector': '#background', 'blocking_layer': False},
            {'selector': '#close-dialog', 'blocking_layer': True},
        ]

        with self.assertRaisesRegex(GlobalPlanError, 'blocking dialog'):
            from apps.ai_testing.global_planner import VisualStepReplanner

            VisualStepReplanner._validate_blocking_layer_action(actions, controls)

    def test_visual_planner_rejects_wait_while_dialog_blocks_page(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'blocking dialog'):
            VisualStepReplanner._validate_blocking_layer_action(
                [{'action': 'wait', 'value': '1000'}],
                [{'selector': '#close-dialog', 'blocking_layer': True}],
            )

    def test_visual_planner_allows_assertion_bound_to_blocking_layer(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_blocking_layer_action(
            [{'action': 'assert'}],
            [{'selector': '#status-menu', 'blocking_layer': True}],
            [{'assertion_index': 1, 'locator': '#status-menu'}],
        )

    def test_visual_planner_allows_unique_accessible_action_on_blocking_layer(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_blocking_layer_action(
            [{'action': 'click', 'role': 'button', 'accessible_name': 'Confirm'}],
            [{'selector': '#confirm', 'role': 'button', 'name': 'Confirm', 'blocking_layer': True}],
        )

    def test_blocking_state_limits_actions_to_highest_layer(self) -> None:
        from apps.ai_testing.execution.blocking_state import build_blocking_state
        from apps.ai_testing.global_planner import VisualStepReplanner

        controls = [
            {'selector': '#lower', 'blocking_layer': True, 'blocking_layer_id': '#first', 'z_index': 10},
            {'selector': '#upper', 'blocking_layer': True, 'blocking_layer_id': '#second', 'z_index': 20},
        ]
        state = build_blocking_state(controls)

        self.assertEqual(state['active_layer_ids'], ['#second'])
        with self.assertRaisesRegex(GlobalPlanError, 'blocking dialog'):
            VisualStepReplanner._validate_blocking_layer_action(
                [{'action': 'click', 'selector': '#lower'}],
                controls,
                blocking_state=state,
            )
        VisualStepReplanner._validate_blocking_layer_action(
            [{'action': 'click', 'selector': '#upper'}],
            controls,
            blocking_state=state,
        )

    def test_blocking_state_allows_controls_on_tied_active_layers(self) -> None:
        from apps.ai_testing.execution.blocking_state import build_blocking_state
        from apps.ai_testing.global_planner import VisualStepReplanner

        controls = [
            {'selector': '#first', 'blocking_layer': True, 'blocking_layer_id': '#layer-a', 'z_index': 'auto'},
            {'selector': '#second', 'blocking_layer': True, 'blocking_layer_id': '#layer-b', 'z_index': 0},
        ]
        state = build_blocking_state(controls)

        self.assertEqual(state['active_layer_ids'], ['#layer-a', '#layer-b'])
        VisualStepReplanner._validate_blocking_layer_action(
            [{'action': 'click', 'selector': '#first'}],
            controls,
            blocking_state=state,
        )

    def test_blocking_state_is_inactive_without_blocking_controls(self) -> None:
        from apps.ai_testing.execution.blocking_state import build_blocking_state

        state = build_blocking_state([{'selector': '#page', 'blocking_layer': False}])

        self.assertFalse(state['is_blocked'])
        self.assertEqual(state['active_layer_ids'], [])

    def test_visual_planner_receives_normalized_blocking_state(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('Blocking state:', source)
        self.assertIn('blocking_state)', source)

    def test_visual_planner_accepts_unique_accessibility_action(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_accessible_action(
            [{'action': 'click', 'role': 'button', 'accessible_name': 'Settings'}],
            {'nodes': [{'node_id': 'ax:button', 'role': 'button', 'name': 'Settings'}]},
        )

    def test_visual_planner_rejects_disabled_accessibility_action(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'target is disabled'):
            VisualStepReplanner._validate_accessible_action(
                [{'action': 'click', 'role': 'button', 'accessible_name': 'Offline camera'}],
                {'nodes': [{
                    'node_id': 'ax:camera',
                    'role': 'button',
                    'name': 'Offline camera',
                    'states': {'disabled': True},
                }]},
            )

    def test_visual_planner_prefers_discovered_selector_over_partial_accessibility_locator(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        action = {'action': 'click', 'selector': '#settings', 'role': 'button'}

        VisualStepReplanner._validate_accessible_action(
            [action],
            {'nodes': []},
            [{'selector': '#settings', 'role': 'button', 'name': 'Settings'}],
        )

        self.assertIsNone(action['role'])
        self.assertIsNone(action['accessible_name'])

    def test_visual_planner_rejects_ambiguous_accessibility_action(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        nodes = [
            {'node_id': 'ax:button-1', 'role': 'button', 'name': 'Save'},
            {'node_id': 'ax:button-2', 'role': 'button', 'name': 'Save'},
        ]

        with self.assertRaisesRegex(GlobalPlanError, 'exactly one current AX node or actionable control'):
            VisualStepReplanner._validate_accessible_action(
                [{'action': 'click', 'role': 'button', 'accessible_name': 'Save'}],
                {'nodes': nodes},
            )

    def test_visual_planner_accepts_discovered_collection_group_selector(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = [{'assertion_index': 1, 'locator': '#results > .result'}]
        assertions = [{'assert_kind': 'collection'}]
        elements = [{
            'selector': '#results > .result:nth-of-type(1)',
            'group_selector': '#results > .result',
            'group_size': 3,
        }]

        VisualStepReplanner._validate_collection_bindings(bindings, assertions, elements)

    def test_visual_planner_rejects_single_item_selector_for_collection(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = [{'assertion_index': 1, 'locator': '#results > .result:nth-of-type(1)'}]
        assertions = [{'assert_kind': 'collection'}]
        elements = [{
            'selector': '#results > .result:nth-of-type(1)',
            'group_selector': '#results > .result',
            'group_size': 3,
        }]

        with self.assertRaisesRegex(GlobalPlanError, 'group_selector'):
            VisualStepReplanner._validate_collection_bindings(bindings, assertions, elements)

    def test_visual_planner_ignores_locator_binding_for_playback_assertion(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = [{'assertion_index': 1, 'locator': '#video-player'}]
        assertions = [{'assert_kind': 'playback'}]

        filtered = VisualStepReplanner._filter_non_dom_assertion_bindings(bindings, assertions)

        self.assertEqual(filtered, [])

    def test_visual_planner_preserves_invalid_binding_index_for_validation(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = [{'assertion_index': 2, 'locator': '#video-player'}]
        assertions = [{'assert_kind': 'playback'}]

        filtered = VisualStepReplanner._filter_non_dom_assertion_bindings(bindings, assertions)

        self.assertEqual(filtered, bindings)

    def test_visual_planner_resolves_duplicate_ax_nodes_with_unique_actionable_control(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        action = {'action': 'click', 'role': 'button', 'accessible_name': 'Save'}
        nodes = [
            {'node_id': 'ax:button-1', 'role': 'button', 'name': 'Save'},
            {'node_id': 'ax:button-2', 'role': 'button', 'name': 'Save'},
        ]

        VisualStepReplanner._validate_accessible_action(
            [action],
            {'nodes': nodes},
            [{'role': 'button', 'name': 'Save', 'selector': '#save'}],
        )

        self.assertEqual(action['selector'], '#save')
        self.assertIsNone(action['role'])
        self.assertIsNone(action['accessible_name'])

    def test_visual_planner_rejects_repeated_accessibility_action(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        action = {'action': 'click', 'role': 'button', 'accessible_name': 'Settings'}

        with self.assertRaisesRegex(GlobalPlanError, 'must not repeat'):
            VisualStepReplanner._validate_non_repeating_action(
                [action],
                [action],
                [{'role': 'button', 'name': 'Settings', 'blocking_layer': False}],
            )

    def test_visual_planner_rejects_immediate_repeated_scroll(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        action = {'action': 'scroll', 'selector': '#results'}

        with self.assertRaisesRegex(GlobalPlanError, 'must not repeat'):
            VisualStepReplanner._validate_non_repeating_action(
                [action],
                [action],
                [{'selector': '#results', 'blocking_layer': False}],
            )

    def test_visual_planner_rejects_immediate_repeated_blocking_action(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        action = {'action': 'click', 'selector': '#confirm'}

        with self.assertRaisesRegex(GlobalPlanError, 'must not repeat'):
            VisualStepReplanner._validate_non_repeating_action(
                [action],
                [action],
                [{'selector': '#confirm', 'blocking_layer': True}],
            )

    def test_visual_planner_rejects_navigation_as_absence_proof(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{'assert_kind': 'absence', 'required': True}]

        with self.assertRaisesRegex(GlobalPlanError, 'navigating away'):
            VisualStepReplanner._validate_absence_recovery(
                [{'action': 'navigate', 'url': '/other'}], [], assertions,
            )
        with self.assertRaisesRegex(GlobalPlanError, 'navigation link'):
            VisualStepReplanner._validate_absence_recovery(
                [{'action': 'click', 'selector': '#other'}],
                [{'selector': '#other', 'url': '/other'}],
                assertions,
            )

    def test_unbound_assertion_error_directs_state_changing_recovery(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('return one state-changing action', source)
        self.assertIn('instead of assert', source)
        self.assertIn("{'field_value', 'popup', 'element_state', 'collection', 'absence'}", source)

    def test_visual_planner_waits_for_observed_loading_state(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('return assert with complete discovered bindings', source)
        self.assertIn('do not repeat the transition', source)
        self.assertIn('use one bounded wait action', source)
        self.assertIn('never resubmit the triggering action while loading', source)


    def test_planner_prompt_distinguishes_static_ui_from_native_media(self) -> None:
        messages = GlobalTestPlanner._build_messages('Verify a static image', None, 'Base prompt')

        self.assertIn('Use element_state or collection for static UI elements', messages[0]['content'])
        self.assertIn('never assert inferred CSS states such as selected', messages[0]['content'])
        self.assertIn('assert an objectively observable detail element', messages[0]['content'])
        self.assertIn('Use media or video only for native audio/video elements', messages[0]['content'])
        self.assertIn('Every fill, press, and select action must include a non-empty value', messages[0]['content'])
        self.assertIn('use download_task', messages[0]['content'])
        self.assertIn('Do not model download completion as element_state', messages[0]['content'])
        self.assertIn('Use fill only when the selected actionable control has editable=true', messages[0]['content'])
        self.assertIn('minimum_advanced_seconds', messages[0]['content'])
        self.assertIn('do not output login steps or login assertions', messages[0]['content'])
        self.assertIn('Do not add a step solely to establish a generic post-login landing page', messages[0]['content'])
        self.assertIn('action="create" exactly', messages[0]['content'])
        self.assertIn('allowed_capabilities exactly as ["data_factory.create"]', messages[0]['content'])
        self.assertIn('exactly one user-visible state transition', messages[0]['content'])
        self.assertIn('No browser step may pass from action completion alone', messages[0]['content'])
        self.assertIn('Never assert the final state before the commit action', messages[0]['content'])
        self.assertIn('Never create conditional steps', messages[0]['content'])
        self.assertIn('plan and verify the field update before the irreversible status transition', messages[0]['content'])
        self.assertIn('operator="phone_digits_equals"', messages[0]['content'])
        self.assertIn('Do not treat names from the user goal as exact rendered UI text', messages[0]['content'])
        self.assertIn('assert the newly introduced control or panel', messages[0]['content'])
        self.assertIn('existence of an unrelated control does not prove selection', messages[0]['content'])

    def test_phone_field_assertion_is_upgraded_for_cached_plans(self) -> None:
        assertions = GlobalTestPlanner._normalize_assertions([
            {
                'action': 'assert',
                'assert_kind': 'field_value',
                'target': {'intent': 'Phone Number input'},
                'operator': 'equals',
                'expected': {'value': '+1 6465180948'},
                'evidence_requirements': ['structured_value'],
            },
        ], step_index=7)

        self.assertEqual(assertions[0]['operator'], 'phone_digits_equals')

    def test_dropdown_selection_rejects_unrelated_existence_assertion(self) -> None:
        with self.assertRaisesRegex(GlobalPlanError, '未验证所选值'):
            GlobalTestPlanner._validate_dropdown_selection_assertion(
                'Select the Site Manager option from the role dropdown.',
                [{
                    'assert_kind': 'element_state',
                    'target': {'intent': 'submit control'},
                    'operator': 'exists',
                    'expected': {'value': True},
                }],
                step_index=9,
            )

    def test_dropdown_selection_accepts_requested_selected_value(self) -> None:
        GlobalTestPlanner._validate_dropdown_selection_assertion(
            'Select the requested option from the role dropdown.',
            [{
                'assert_kind': 'field_value',
                'target': {'intent': 'role dropdown'},
                'operator': 'equals',
                'expected': {'value': 'requested option'},
            }],
            step_index=9,
        )

    def test_dropdown_selection_accepts_transaction_dialog_without_committed_value(self) -> None:
        GlobalTestPlanner._validate_dropdown_selection_assertion(
            'Select the requested option from the status dropdown.',
            [{
                'assert_kind': 'element_state',
                'target': {'intent': 'reason dialog opened by the selection'},
                'operator': 'exists',
                'expected': {'value': True},
            }],
            step_index=5,
            transition={'kind': 'select_option', 'value': 'Investigate'},
        )

    def test_dropdown_selection_rejects_committed_value_before_transaction_dialog(self) -> None:
        with self.assertRaisesRegex(GlobalPlanError, 'before the transaction dialog is confirmed'):
            GlobalTestPlanner._validate_dropdown_selection_assertion(
                'Select the requested option from the status dropdown.',
                [
                    {
                        'assert_kind': 'element_state',
                        'target': {'intent': 'selected status value'},
                        'operator': 'contains',
                        'expected': {'value': 'Investigate'},
                    },
                    {
                        'assert_kind': 'element_state',
                        'target': {'intent': 'reason dialog opened by the selection'},
                        'operator': 'exists',
                        'expected': {'value': True},
                    },
                ],
                step_index=5,
                transition={'kind': 'select_option', 'value': 'Investigate'},
            )

    def test_dropdown_selection_uses_contains_for_rendered_label(self) -> None:
        assertions = [{
            'assert_kind': 'field_value',
            'target': {'intent': 'role dropdown'},
            'operator': 'equals',
            'expected': {'value': 'requested option'},
        }]

        GlobalTestPlanner._normalize_dropdown_selection_operator(
            'Select the requested option from the role dropdown.',
            assertions,
        )

        self.assertEqual(assertions[0]['operator'], 'starts_with')

    def test_dropdown_selection_does_not_weaken_ordinary_field_equality(self) -> None:
        assertions = [{
            'assert_kind': 'field_value',
            'target': {'intent': 'email input'},
            'operator': 'equals',
            'expected': {'value': 'requested@example.com'},
        }]

        GlobalTestPlanner._normalize_dropdown_selection_operator(
            'Fill the email input with requested@example.com.',
            assertions,
        )

        self.assertEqual(assertions[0]['operator'], 'equals')

    def test_structured_dropdown_transition_is_language_independent(self) -> None:
        transition = {'kind': 'select_option', 'value': 'Site Manager'}
        assertions = [{
            'assert_kind': 'field_value',
            'target': {'intent': 'role control'},
            'operator': 'equals',
            'expected': {'value': 'Site Manager'},
        }]

        GlobalTestPlanner._normalize_dropdown_selection_operator('选择指定角色', assertions, transition)
        GlobalTestPlanner._validate_dropdown_selection_assertion(
            '选择指定角色', assertions, step_index=1, transition=transition,
        )

        self.assertEqual(assertions[0]['operator'], 'starts_with')

    def test_select_option_removes_redundant_label_when_new_control_proves_mode(self) -> None:
        assertions = [
            {
                'assert_kind': 'element_state',
                'target': {'intent': 'mode selected value'},
                'operator': 'contains',
                'expected': {'value': 'Magic Search V2'},
            },
            {
                'assert_kind': 'element_state',
                'target': {'intent': 'Magic Search V2 search input'},
                'operator': 'exists',
                'expected': {'value': True},
            },
        ]

        GlobalTestPlanner._remove_redundant_selection_label_assertion(
            assertions,
            {'kind': 'select_option', 'value': 'Magic Search V2'},
        )

        self.assertEqual(assertions, [{
            'assert_kind': 'element_state',
            'target': {'intent': 'Magic Search V2 search input'},
            'operator': 'exists',
            'expected': {'value': True},
        }])

    def test_search_result_rejects_unbindable_absence_assertion(self) -> None:
        with self.assertRaisesRegex(GlobalPlanError, 'text not_contains'):
            GlobalTestPlanner._validate_search_result_absence_assertion(
                'Search for the removed record to verify removal.',
                [{
                    'assert_kind': 'absence',
                    'target': {'intent': 'removed record result'},
                    'operator': 'not_exists',
                    'expected': {'value': True},
                }],
                step_index=14,
            )

    def test_structured_absent_results_transition_is_language_independent(self) -> None:
        with self.assertRaisesRegex(GlobalPlanError, 'text not_contains'):
            GlobalTestPlanner._validate_search_result_absence_assertion(
                '查询并验证记录已移除',
                [{
                    'assert_kind': 'absence',
                    'target': {'intent': 'removed record result'},
                }],
                step_index=1,
                transition={
                    'kind': 'filter_results',
                    'value': 'record identifier',
                    'result_presence': 'absent',
                },
            )

    def test_dropdown_value_binding_rejects_clicked_option(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{
            'assert_kind': 'field_value',
            'target': {'intent': 'role dropdown'},
            'operator': 'equals',
            'expected': {'value': 'requested option'},
        }]

        with self.assertRaisesRegex(GlobalPlanError, 'clicked option'):
            VisualStepReplanner._validate_dropdown_value_binding(
                [{'assertion_index': 1, 'locator': '#requested-option'}],
                assertions,
                [{'action': 'click', 'selector': '#requested-option'}],
                'Select the requested option from the role dropdown.',
            )

    def test_dropdown_value_binding_accepts_selected_control(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_dropdown_value_binding(
            [{'assertion_index': 1, 'locator': '#role-control'}],
            [{
                'assert_kind': 'field_value',
                'target': {'intent': 'role dropdown'},
                'operator': 'equals',
                'expected': {'value': 'requested option'},
            }],
            [{'action': 'click', 'selector': '#requested-option'}],
            'Choose the requested option from the role menu.',
        )

    def test_dropdown_text_binding_rejects_mismatched_observed_value(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'expected selected value'):
            VisualStepReplanner._validate_dropdown_value_binding(
                [{'assertion_index': 1, 'locator': '#selected-value'}],
                [{
                    'assert_kind': 'element_state',
                    'target': {'intent': 'selected option'},
                    'operator': 'contains',
                    'expected': {'value': 'Other'},
                }],
                [{'action': 'click', 'selector': '#other-option'}],
                'Select Other from the reason dropdown.',
                discovered_elements=[{'selector': '#selected-value', 'text': 'Investigate'}],
            )

    def test_visible_element_binding_does_not_require_state_word_in_text(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_dropdown_value_binding(
            [{'assertion_index': 1, 'locator': '#menu-option'}],
            [{
                'assert_kind': 'element_state',
                'target': {'text': 'Magic Search V2'},
                'operator': 'exists',
                'expected': {'value': 'visible'},
            }],
            [{'action': 'click', 'selector': '#menu-toggle'}],
            'Open the search mode menu.',
            discovered_elements=[{'selector': '#menu-option', 'text': 'Magic Search V2'}],
        )

    def test_select_option_step_rejects_second_state_change_after_completed_action(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'already completed its select-option transition'):
            VisualStepReplanner._validate_non_repeating_action(
                [{'action': 'click', 'selector': '#unrelated-control'}],
                [{'action': 'click', 'selector': '#requested-option', 'status': 'completed'}],
                [{'selector': '#unrelated-control', 'blocking_layer': True}],
                step_description='Select the requested option from the role dropdown.',
            )

    def test_completed_select_option_binds_unique_blocking_popup(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        actions, bindings = VisualStepReplanner._resolve_visible_popup_assertion(
            [{'action': 'click', 'selector': '#dialog-control'}],
            [],
            [{
                'assert_kind': 'popup',
                'operator': 'exists',
                'expected': {'value': True},
            }],
            [{'action': 'click', 'selector': '#requested-option', 'status': 'completed'}],
            'Select the requested option from the status dropdown.',
            None,
            {'is_blocked': True, 'active_layer_ids': ['#reason-dialog']},
        )

        self.assertEqual(actions, [{'action': 'assert'}])
        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '#reason-dialog'}])

    def test_completed_click_binds_unique_dialog_layer_popup(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        actions, bindings = VisualStepReplanner._resolve_visible_popup_assertion(
            [{'action': 'click', 'selector': '#download-again'}],
            [],
            [{'assert_kind': 'popup', 'operator': 'exists', 'expected': {'value': True}}],
            [{'action': 'click', 'selector': '#download', 'status': 'completed'}],
            'Click the Download control on the playback page to open the download confirmation dialog.',
            {'kind': 'generic'},
            {'is_blocked': True, 'active_layer_ids': ['#download-dialog'], 'dialog_layer_ids': ['#download-dialog']},
        )

        self.assertEqual(actions, [{'action': 'assert'}])
        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '#download-dialog'}])

    def test_completed_click_does_not_bind_non_dialog_blocking_layer_popup(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        original_actions = [{'action': 'click', 'selector': '#download-again'}]
        actions, bindings = VisualStepReplanner._resolve_visible_popup_assertion(
            original_actions,
            [],
            [{'assert_kind': 'popup', 'operator': 'exists', 'expected': {'value': True}}],
            [{'action': 'click', 'selector': '#download', 'status': 'completed'}],
            'Click the Download control on the playback page to open the download confirmation dialog.',
            {'kind': 'generic'},
            {'is_blocked': True, 'active_layer_ids': ['#fixed-sidebar'], 'dialog_layer_ids': []},
        )

        self.assertEqual(actions, original_actions)
        self.assertEqual(bindings, [])

    def test_blocking_layer_accepts_assert_binding_inside_active_layer(self) -> None:
        from apps.ai_testing.execution.blocking_state import build_blocking_state
        from apps.ai_testing.global_planner import GlobalPlanError, VisualStepReplanner

        layer_id = 'body > div:nth-of-type(3) > div:nth-of-type(1)'
        controls = [{
            'selector': f'{layer_id} > div:nth-of-type(2) > button:nth-of-type(1)',
            'blocking_layer': True,
            'blocking_layer_id': layer_id,
            'dialog_layer': True,
            'z_index': 1000,
        }]
        state = build_blocking_state(controls)

        self.assertEqual(state['dialog_layer_ids'], [layer_id])
        VisualStepReplanner._validate_blocking_layer_action(
            [{'action': 'assert'}],
            controls,
            bindings=[{'assertion_index': 1, 'locator': f'{layer_id} > div:nth-of-type(1) > span:nth-of-type(2)'}],
            blocking_state=state,
        )
        with self.assertRaisesRegex(GlobalPlanError, 'blocking dialog'):
            VisualStepReplanner._validate_blocking_layer_action(
                [{'action': 'assert'}],
                controls,
                bindings=[{'assertion_index': 1, 'locator': 'body > div:nth-of-type(1) > h1:nth-of-type(1)'}],
                blocking_state=state,
            )

    def test_blocking_state_without_dialog_controls_has_no_dialog_layer_ids(self) -> None:
        from apps.ai_testing.execution.blocking_state import build_blocking_state

        state = build_blocking_state([
            {'selector': '#banner-close', 'blocking_layer': True, 'blocking_layer_id': '#banner', 'z_index': 5},
        ])

        self.assertEqual(state['active_layer_ids'], ['#banner'])
        self.assertEqual(state['dialog_layer_ids'], [])

    def test_dropdown_value_binding_accepts_shared_selector_when_it_now_names_the_display(self) -> None:
        from apps.ai_testing.global_planner import GlobalPlanError, VisualStepReplanner

        assertions = [{'assert_kind': 'field_value', 'operator': 'starts_with', 'expected': {'value': 'Site Manager'}, 'target': {'intent': 'role dropdown'}}]
        prior = [{'action': 'click', 'selector': '[title="Site Manager (Can manage sites)"]', 'status': 'completed'}]
        bindings = [{'assertion_index': 1, 'locator': '[title="Site Manager (Can manage sites)"]'}]

        VisualStepReplanner._validate_dropdown_value_binding(
            bindings, assertions, prior, 'Select the Site Manager option from the role dropdown.', {'kind': 'select_option'},
            [{'selector': '[title="Site Manager (Can manage sites)"]', 'tag': 'span', 'role': '', 'top_layer': False, 'group_size': 1}],
        )
        with self.assertRaisesRegex(GlobalPlanError, 'clicked option'):
            VisualStepReplanner._validate_dropdown_value_binding(
                bindings, assertions, prior, 'Select the Site Manager option from the role dropdown.', {'kind': 'select_option'},
                [{'selector': '[title="Site Manager (Can manage sites)"]', 'tag': 'div', 'role': 'option', 'top_layer': True, 'group_size': 5}],
            )
        with self.assertRaisesRegex(GlobalPlanError, 'clicked option'):
            VisualStepReplanner._validate_dropdown_value_binding(
                bindings, assertions, prior, 'Select the Site Manager option from the role dropdown.', {'kind': 'select_option'}, [],
            )

    def test_popup_absence_reuses_unique_verified_popup_locator(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = VisualStepReplanner._bind_verified_popup_absence(
            [{'assertion_index': 2, 'locator': '#committed-status'}],
            [
                {
                    'assert_kind': 'popup',
                    'operator': 'not_exists',
                    'expected': {'value': True},
                },
                {
                    'assert_kind': 'field_value',
                    'operator': 'starts_with',
                    'expected': {'value': 'requested status'},
                },
            ],
            [{
                'assertions': [{
                    'assert_kind': 'popup',
                    'operator': 'exists',
                    'target': {'locator': '#reason-dialog'},
                }],
            }],
        )

        self.assertEqual(bindings, [
            {'assertion_index': 2, 'locator': '#committed-status'},
            {'assertion_index': 1, 'locator': '#reason-dialog'},
        ])

    def test_exact_text_binding_prefers_unique_semantic_control(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = VisualStepReplanner._bind_exact_text_assertions(
            [{'assertion_index': 1, 'locator': '#wrong-control'}],
            [{
                'assert_kind': 'element_state',
                'operator': 'exists',
                'target': {'text': 'Requested Mode'},
                'expected': {'value': True},
            }],
            [
                {'role': '', 'name': 'Requested Mode', 'selector': '#container'},
                {'role': 'menuitem', 'name': 'Requested Mode', 'selector': '#option'},
            ],
        )

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '#option'}])

    def test_exact_text_binding_rejects_existing_mismatched_control(self) -> None:
        from apps.ai_testing.global_planner import GlobalPlanError, VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'does not uniquely match'):
            VisualStepReplanner._bind_exact_text_assertions(
                [{'assertion_index': 1, 'locator': '#wrong-control'}],
                [{
                    'assert_kind': 'element_state',
                    'operator': 'exists',
                    'target': {'text': 'Requested Mode'},
                    'expected': {'value': True},
                }],
                [{'role': 'button', 'name': 'Other Mode', 'selector': '#wrong-control'}],
            )

    def test_exact_text_binding_keeps_equal_semantic_matches_unbound(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = VisualStepReplanner._bind_exact_text_assertions(
            [],
            [{
                'assert_kind': 'element_state',
                'operator': 'exists',
                'target': {'text': 'Requested Mode'},
                'expected': {'value': True},
            }],
            [
                {'role': 'menuitem', 'name': 'Requested Mode', 'selector': '#first'},
                {'role': 'menuitem', 'name': 'Requested Mode', 'selector': '#second'},
            ],
        )

        self.assertEqual(bindings, [])

    def test_completed_action_uses_complete_exact_text_bindings(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        actions = VisualStepReplanner._resolve_completed_bound_assertion(
            [{'action': 'click', 'selector': '#other-control'}],
            [{'assertion_index': 1, 'locator': '#requested-option'}],
            {1},
            [{'action': 'click', 'selector': '#menu', 'status': 'completed'}],
        )

        self.assertEqual(actions, [{'action': 'assert'}])

    def test_visual_planner_supplies_react_context_and_enforces_absence_bindings(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('Prior actions:', source)
        self.assertIn('Verified predecessor steps:', source)
        self.assertIn('Accessibility snapshot:', source)
        self.assertIn('Assertions to verify:', source)
        self.assertIn('Only absence or discovered collection assertions may be bound before a state-changing action.', source)
        self.assertIn('Its locator must use a discovered observable element group_selector', source)
        self.assertIn("assertions[binding['assertion_index'] - 1].get('assert_kind') not in {'absence', 'collection'}", source)
        self.assertGreater(
            source.index('_validate_accessible_action'),
            source.index('_resolve_completed_bound_assertion'),
        )

    def test_visual_planner_rejects_repeating_failed_state_change(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'must not repeat'):
            VisualStepReplanner._validate_non_repeating_action(
                [{'action': 'click', 'selector': '#candidate'}],
                [{'action': 'click', 'selector': '#candidate'}],
            )

    def test_visible_record_correlation_does_not_select_populated_input(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        actions = [{'action': 'click', 'selector': '#model-choice'}]
        resolved_actions = VisualStepReplanner._resolve_visible_record_action(
            actions,
            [
                {'tag': 'input', 'editable': True, 'selector': '#search', 'name': 'Camera A'},
                {'tag': 'div', 'selector': '#record', 'container_text': 'Camera A'},
            ],
            [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['Camera A']}}}],
            correlates_resource='alert_event',
        )

        self.assertEqual(resolved_actions[0]['selector'], '#record')
        self.assertEqual(actions[0]['selector'], '#model-choice')

    def test_visible_correlated_detail_replaces_scroll_with_bound_assertion(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        resolved_actions = VisualStepReplanner._resolve_visible_record_action(
            [{'action': 'scroll', 'selector': '#records', 'value': 'down'}],
            [{'tag': 'div', 'selector': '#detail', 'container_text': 'Person Camera A'}],
            [{
                'resource_type': 'alert_event',
                'resource': {'result_correlation': {'match_values': ['Person', 'Camera A']}},
            }],
            correlates_resource='alert_event',
            assertions=[{
                'assert_kind': 'element_state',
                'operator': 'exists',
                'expected': {'value': True},
            }],
        )

        self.assertEqual(resolved_actions, [{
            'action': 'assert',
            'assertion_bindings': [{'assertion_index': 1, 'locator': '#detail'}],
        }])

        VisualStepReplanner._validate_non_repeating_action(
            [{'action': 'click', 'selector': '#confirm'}],
            [
                {'action': 'click', 'selector': '#confirm'},
                {'action': 'click', 'selector': '#required-choice'},
            ],
            [{'selector': '#confirm', 'blocking_layer': True}],
        )

        with self.assertRaisesRegex(GlobalPlanError, 'failed non-blocking'):
            VisualStepReplanner._validate_non_repeating_action(
                [{'action': 'click', 'selector': '#edit'}],
                [
                    {'action': 'click', 'selector': '#edit'},
                    {'action': 'click', 'selector': '#close-modal'},
                ],
                [{'selector': '#edit', 'blocking_layer': False}],
            )

        VisualStepReplanner._validate_non_repeating_action(
            [{'action': 'scroll', 'selector': '#panel'}],
            [
                {'action': 'scroll', 'selector': '#panel'},
                {'action': 'click', 'selector': '#expand'},
            ],
        )

    def test_visual_planner_rejects_undiscovered_navigation_url(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        controls = [{'selector': '[href="/records"]', 'url': 'https://example.test/records'}]

        VisualStepReplanner._validate_discovered_navigation(
            [{'action': 'navigate', 'url': 'https://example.test/records'}],
            controls,
        )
        with self.assertRaisesRegex(GlobalPlanError, 'was not discovered'):
            VisualStepReplanner._validate_discovered_navigation(
                [{'action': 'navigate', 'url': 'https://example.test/invented'}],
                controls,
            )

    def test_visual_planner_rejects_scroll_for_navigation_when_links_exist(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'must use a discovered actionable link'):
            VisualStepReplanner._validate_offscreen_search_action(
                [{'action': 'scroll', 'selector': '#content'}],
                {'scroll_containers': [{'selector': '#content', 'remaining': 100}]},
                [{'selector': '#records-link', 'url': 'https://example.test/records'}],
                [],
                'Navigate to the records view',
            )

    def test_visual_planner_passes_execution_resources_to_runtime_resolver(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('Execution-scoped resources:', source)
        self.assertIn('_resolve_visible_record_action', source)

    def test_visual_planner_requires_unique_runtime_correlated_visible_record(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        controls = [
            {'selector': '#unrelated', 'name': 'Other record', 'container_text': 'Camera B'},
            {'selector': '#matched', 'name': 'Generated record', 'container_text': 'Camera A person'},
        ]
        resources = [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}}}]

        VisualStepReplanner._resolve_visible_record_action(
            [{'action': 'click', 'selector': '#matched'}], controls, resources,
            correlates_resource='alert_event',
        )
        lower_scoring_action = [{'action': 'click', 'selector': '#unrelated'}]
        lower_scoring_action = VisualStepReplanner._resolve_visible_record_action(
            lower_scoring_action, controls, resources,
            correlates_resource='alert_event',
        )
        self.assertEqual(lower_scoring_action, [{'action': 'click', 'selector': '#matched'}])

        search_action = [{'action': 'fill', 'selector': '#search', 'value': 'Camera A'}]
        search_action = VisualStepReplanner._resolve_visible_record_action(
            search_action, controls, resources,
            correlates_resource='alert_event',
        )
        self.assertEqual(search_action, [{'action': 'fill', 'selector': '#search', 'value': 'Camera A'}])
        VisualStepReplanner._resolve_visible_record_action(
            [{'action': 'click', 'selector': '#navigation-link'}],
            controls,
            resources,
            'Navigate to records\nChoose a different action sequence.',
        )

    def test_visual_planner_ignores_values_from_unrelated_resource_types(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        controls = [
            {'selector': '#alert', 'container_text': 'Camera A person'},
            {'selector': '#device', 'container_text': 'Device 42'},
        ]
        resources = [
            {'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}}},
            {'resource_type': 'device', 'resource': {'result_correlation': {'match_values': ['Device 42']}}},
        ]

        resolved_actions = VisualStepReplanner._resolve_visible_record_action(
            [{'action': 'click', 'selector': '#device'}], controls, resources,
            correlates_resource='alert_event',
        )

        self.assertEqual(resolved_actions, [{'action': 'click', 'selector': '#alert'}])

    def test_visual_planner_scrolls_until_all_record_correlation_values_are_visible(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        actions = [{'action': 'assert'}]

        resolved_actions = VisualStepReplanner._resolve_visible_record_action(
            actions,
            [{'selector': '#partial-record', 'container_text': 'person'}],
            [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}}}],
            {'scroll_containers': [{'selector': '#record-list', 'remaining': 500}]},
            correlates_resource='alert_event',
        )

        self.assertEqual(resolved_actions, [{'action': 'scroll', 'selector': '#record-list', 'value': 'down'}])
        self.assertEqual(actions, [{'action': 'assert'}])

    def test_visual_planner_opens_correlated_record_before_asserting(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        resolved_actions = VisualStepReplanner._resolve_visible_record_action(
            [{'action': 'assert'}],
            [{'selector': '#matched', 'container_text': 'Camera A person'}],
            [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}}}],
            correlates_resource='alert_event',
        )

        self.assertEqual(resolved_actions, [{'action': 'click', 'selector': '#matched'}])

    def test_visual_planner_does_not_apply_record_correlation_to_search(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        actions = [{'action': 'fill', 'selector': '#search', 'value': 'Camera A'}]
        resolved_actions = VisualStepReplanner._resolve_visible_record_action(
            actions,
            [{'selector': '#partial-record', 'container_text': 'person'}],
            [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}}}],
        )

        self.assertEqual(resolved_actions, actions)

    def test_visual_planner_does_not_apply_record_correlation_to_unrelated_open_step(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        actions = [{'action': 'assert'}]
        resolved_actions = VisualStepReplanner._resolve_visible_record_action(
            actions,
            [{'selector': '#camera', 'container_text': 'Default device camera'}],
            [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['generated alert']}}}],
        )

        self.assertEqual(resolved_actions, actions)

    def test_visual_planner_rejects_image_binding_to_placeholder(self) -> None:
        from apps.ai_testing.global_planner import GlobalPlanError, VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'rendered image content'):
            VisualStepReplanner._validate_visual_content_bindings(
                [{'assertion_index': 1, 'locator': '#placeholder'}],
                [{'assert_kind': 'element_state', 'target': {'visual_content': 'image'}}],
                [{'selector': '#placeholder', 'has_visual_content': False}],
            )

    def test_visual_planner_accepts_image_binding_with_rendered_content(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_visual_content_bindings(
            [{'assertion_index': 1, 'locator': '#thumb'}],
            [{'assert_kind': 'element_state', 'target': {'visual_content': 'image'}}],
            [{'selector': '#thumb', 'has_visual_content': True}],
        )

        VisualStepReplanner._validate_visual_content_bindings(
            [{'assertion_index': 1, 'locator': '#thumb > img'}],
            [{'assert_kind': 'element_state', 'target': {'visual_content': 'image'}}],
            [{'selector': '#thumb', 'group_selector': '#thumb > img', 'has_visual_content': True}],
        )

    def test_exact_text_binding_leaves_image_assertion_bindings_to_visual_validation(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = [{'assertion_index': 1, 'locator': '#hero'}]
        resolved = VisualStepReplanner._bind_exact_text_assertions(
            bindings,
            [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'text': 'camera', 'visual_content': 'image'}}],
            [{'selector': '#hero', 'text': 'Front door camera', 'has_visual_content': True}],
        )

        self.assertEqual(resolved, bindings)

    def test_exact_text_binding_accepts_model_binding_containing_target_text(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = [{'assertion_index': 1, 'locator': '#row'}]
        resolved = VisualStepReplanner._bind_exact_text_assertions(
            bindings,
            [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'text': 'camera'}}],
            [{'selector': '#row', 'text': 'Camera 01'}, {'selector': '#other', 'text': 'Settings'}],
        )

        self.assertEqual(resolved, bindings)

    def test_exact_text_binding_accepts_model_choice_among_equal_matches(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        bindings = [{'assertion_index': 1, 'locator': '#team-b'}]
        resolved = VisualStepReplanner._bind_exact_text_assertions(
            bindings,
            [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'text': 'Team'}}],
            [
                {'selector': '#team-a', 'name': 'Team', 'role': 'button'},
                {'selector': '#team-b', 'name': 'Team', 'role': 'button'},
            ],
        )

        self.assertEqual(resolved, bindings)

    def test_exact_text_binding_still_rejects_unrelated_model_binding(self) -> None:
        from apps.ai_testing.global_planner import GlobalPlanError, VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'does not uniquely match'):
            VisualStepReplanner._bind_exact_text_assertions(
                [{'assertion_index': 1, 'locator': '#other'}],
                [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'text': 'camera'}}],
                [{'selector': '#other', 'text': 'Settings'}],
            )

    def test_visual_planner_does_not_override_verified_identity_with_record_correlation(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        actions = [{'action': 'click', 'selector': '#record-7'}]
        VisualStepReplanner._resolve_visible_record_action(
            actions,
            [{'selector': '#record-7', 'name': 'Requested item'}],
            [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['unrelated response value']}}}],
            verified_predecessors=[{
                'assertions': [{'target': {'locator': '#record-7 > img'}}],
            }],
            correlates_resource='alert_event',
        )

        self.assertEqual(actions, [{'action': 'click', 'selector': '#record-7'}])

    def test_visual_planner_rejects_scroll_container_without_usable_viewport(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'no usable viewport'):
            VisualStepReplanner._validate_offscreen_search_action(
                [{'action': 'scroll', 'selector': '#clipped-label'}],
                {'scroll_containers': [{
                    'selector': '#clipped-label',
                    'client_height': 1,
                    'remaining': 24,
                }]},
                [],
                [],
            )

    def test_visual_planner_allows_scroll_container_with_usable_viewport(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_offscreen_search_action(
            [{'action': 'scroll', 'selector': '#record-list'}],
            {'scroll_containers': [{
                'selector': '#record-list',
                'client_height': 500,
                'remaining': 900,
            }]},
            [],
            [],
        )

    def test_visual_planner_rejects_partial_record_match_without_search_path(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'uncorrelated or partially correlated record'):
            VisualStepReplanner._resolve_visible_record_action(
                [{'action': 'assert'}],
                [{'selector': '#partial-record', 'container_text': 'person'}],
                [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}}}],
                correlates_resource='alert_event',
            )

    def test_visual_planner_rejects_unrelated_action_when_no_record_matches(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'uncorrelated or partially correlated record'):
            VisualStepReplanner._resolve_visible_record_action(
                [{'action': 'click', 'selector': '#date-filter'}],
                [{'selector': '#date-filter', 'container_text': 'Select date'}],
                [{'resource_type': 'alert_event', 'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}}}],
                correlates_resource='alert_event',
            )

    def test_visual_planner_rejects_ambiguous_fully_correlated_records(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'multiple controls'):
            VisualStepReplanner._resolve_visible_record_action(
                [{'action': 'click', 'selector': '#first-record'}],
                [
                    {'selector': '#first-record', 'container_text': 'Camera A person'},
                    {'selector': '#second-record', 'container_text': 'Camera A person'},
                ],
                [{
                    'resource_type': 'alert_event',
                    'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}},
                }],
                correlates_resource='alert_event',
            )

    def test_visual_planner_uses_platform_ai_request_timeout(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('asyncio.wait_for', source)
        self.assertIn('settings.TIMEOUTS_AI_REQUEST', source)
        self.assertNotIn('max_tokens=', source)

    def test_sync_planner_database_loaders_close_old_connections(self) -> None:
        from apps.ai_testing.global_planner import GlobalTestPlanner, VisualStepReplanner

        loaders = (
            VisualStepReplanner._load_active_model_config,
            VisualStepReplanner._load_active_prompt_content,
            GlobalTestPlanner._load_active_model_configs,
            GlobalTestPlanner._load_active_prompt_content,
            GlobalTestPlanner._load_data_factory_resources,
        )

        for loader in loaders:
            with self.subTest(loader=loader.__name__):
                self.assertIn('close_old_connections()', inspect.getsource(loader))

    def test_visual_planner_uses_configured_prompt_as_policy_source(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('prompt_content = await self._get_active_prompt_content()', source)
        self.assertIn("f'{prompt_content}\\n\\nRuntime contract:\\n'", source)
        self.assertIn('Never bind a collection assertion to a collection container', source)
        self.assertNotIn('For theme assertions', source)

    def test_visual_planner_rejects_choice_control_as_collection_evidence(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{'assert_kind': 'collection', 'target': {'intent': 'search result items'}}]
        bindings = [{'assertion_index': 1, 'locator': '#mode-option'}]
        controls = [{'selector': '#mode-option', 'role': 'menuitem', 'top_layer': True}]

        with self.assertRaisesRegex(GlobalPlanError, 'choice control'):
            VisualStepReplanner._validate_collection_bindings(bindings, assertions, controls)

    def test_visual_planner_allows_repeated_item_collection_evidence(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_collection_bindings(
            [{'assertion_index': 1, 'locator': '.result-card'}],
            [{'assert_kind': 'collection', 'target': {'intent': 'search result items'}}],
            [{
                'selector': '.result-card:nth-of-type(1)',
                'group_selector': '.result-card',
                'role': '',
                'group_size': 3,
                'top_layer': False,
            }],
        )

    def test_visual_planner_supplies_page_metrics_to_offscreen_validator(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('Page metrics:', source)
        self.assertIn('_validate_offscreen_search_action', source)

    def test_visual_planner_allows_discovered_icon_control_with_offscreen_content(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        validator = VisualStepReplanner._validate_offscreen_search_action
        metrics = {'scroll_containers': [{'selector': '#panel', 'remaining': 500}]}
        controls = [{'selector': '#anonymous', 'name': '', 'blocking_layer': False}]

        with self.assertRaisesRegex(GlobalPlanError, 'must scroll'):
            validator([{'action': 'wait'}], metrics, controls, [])

        validator(
            [{'action': 'click', 'selector': '#anonymous'}],
            metrics,
            controls,
            [],
        )

    def test_planner_rejects_conditional_browser_step(self) -> None:
        response = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_execution_plan',
            'arguments': '{"steps":[{"executor":"browser","description":"Confirm if a dialog appears","allowed_capabilities":["browser.act"],"assertions":[],"verification_required":false}]}',
        }}]}}]}

        with self.assertRaisesRegex(GlobalPlanError, 'contains a conditional branch'):
            GlobalTestPlanner.normalize_response(response, None)

    def test_planner_uses_five_bounded_contract_retries(self) -> None:
        source = inspect.getsource(GlobalTestPlanner.create_plan)

        self.assertIn('for attempt in range(5)', source)

    def test_planner_rejects_field_dialog_assertion_after_status_selection(self) -> None:
        response = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_execution_plan',
            'arguments': '{"steps":[{"executor":"browser","description":"Select final status","allowed_capabilities":["browser.act"],"assertions":[{"action":"assert","assert_kind":"element_state","target":{"intent":"category dialog"},"operator":"exists","expected":{"value":true},"evidence_requirements":["element_state"]}]}]}',
        }}]}}]}

        with self.assertRaisesRegex(GlobalPlanError, '必须先设置并验证字段'):
            GlobalTestPlanner.normalize_response(response, None)

    def test_planner_rejects_status_control_without_open_record_precondition(self) -> None:
        steps = [
            {'description': 'Verify target record is visible'},
            {'description': 'Open the status control'},
        ]

        with self.assertRaisesRegex(GlobalPlanError, '缺少独立的记录或详情打开步骤'):
            GlobalTestPlanner._validate_status_control_preconditions(steps)

    def test_planner_accepts_status_control_after_open_record_precondition(self) -> None:
        steps = [
            {'description': 'Open the target record detail'},
            {'description': 'Set and verify a required field'},
            {'description': 'Open the status control'},
        ]

        GlobalTestPlanner._validate_status_control_preconditions(steps)

    def test_planner_rejects_field_update_after_status_selection_in_same_detail(self) -> None:
        steps = [
            {'description': 'Open the target record detail'},
            {'description': 'Select Close as the status'},
            {'description': 'Select investigation category Other'},
        ]

        with self.assertRaisesRegex(GlobalPlanError, 'updates a field after selecting a status'):
            GlobalTestPlanner._validate_field_updates_before_status_selection(steps)

    def test_planner_accepts_field_update_before_status_selection(self) -> None:
        steps = [
            {'description': 'Open the target record detail'},
            {'description': 'Select investigation category Other'},
            {'description': 'Select Close as the status'},
        ]

        GlobalTestPlanner._validate_field_updates_before_status_selection(steps)

    def test_normalize_capabilities_canonicalizes_generic_browser_aliases(self) -> None:
        capabilities = GlobalTestPlanner._normalize_capabilities(['navigate', 'inspect', 'read', 'read_page', 'write'], 1)

        self.assertEqual(
            capabilities,
            ['browser.navigate', 'browser.inspect', 'browser.inspect', 'browser.inspect', 'browser.act'],
        )

    def test_normalize_capabilities_adds_action_for_navigation(self) -> None:
        capabilities = GlobalTestPlanner._normalize_capabilities(['browser.navigate'], 1)

        self.assertEqual(capabilities, ['browser.navigate', 'browser.act'])

    def test_normalize_assertions_canonicalizes_string_target(self) -> None:
        assertions = GlobalTestPlanner._normalize_assertions([
            {
                'action': 'assert', 'assert_kind': 'text', 'target': 'page body',
                'operator': 'contains', 'expected': {'value': 'Dashboard'},
                'evidence_requirements': ['dom_snapshot'],
            },
        ], 1)

        self.assertEqual(assertions[0]['target'], {'locator': 'page body'})

    def test_normalize_assertions_canonicalizes_visual_operator(self) -> None:
        assertions = GlobalTestPlanner._normalize_assertions([
            {
                'action': 'assert', 'assert_kind': 'media', 'target': {'locator': 'video'},
                'operator': 'displays_normally', 'expected': {'value': True},
                'evidence_requirements': ['media_state'],
            },
        ], 1)

        self.assertEqual(assertions[0]['operator'], 'exists')

    def test_normalize_assertions_canonicalizes_comparison_operator(self) -> None:
        assertions = GlobalTestPlanner._normalize_assertions([{
            'action': 'assert', 'assert_kind': 'playback', 'target': {'locator': 'video'},
            'operator': 'gte', 'expected': {'minimum_advanced_seconds': 10},
            'evidence_requirements': ['media_state_before', 'media_state_after', 'playback_time_progress'],
        }], 1)

        self.assertEqual(assertions[0]['operator'], 'greater_than')

    def test_normalize_assertions_canonicalizes_scalar_expected(self) -> None:
        assertions = GlobalTestPlanner._normalize_assertions([
            {
                'action': 'assert', 'assert_kind': 'text', 'target': {'locator': 'body'},
                'operator': 'contains', 'expected': 'Dashboard',
                'evidence_requirements': ['dom_snapshot'],
            },
        ], 1)

        self.assertEqual(assertions[0]['expected'], {'value': 'Dashboard'})

    def test_normalize_assertions_uses_registered_media_evidence(self) -> None:
        assertions = GlobalTestPlanner._normalize_assertions([
            {
                'action': 'assert', 'assert_kind': 'media', 'target': {'locator': 'video'},
                'operator': 'exists', 'expected': {'value': True},
                'evidence_requirements': ['model-invented-screenshot', 'media_state'],
            },
        ], 1)

        self.assertEqual(assertions[0]['evidence_requirements'], ['media_state'])

    def test_normalize_response_extracts_embedded_json_plan(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': 'Plan follows:\n```json\n{"steps":[{"executor":"browser","description":"Verify dashboard","allowed_capabilities":["browser.inspect"],"assertions":[{"action":"assert","assert_kind":"text","target":{"page":"current"},"operator":"contains","expected":{"value":"Dashboard"},"evidence_requirements":["dom_snapshot"]}]}]}\n```',
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(response, configuration_id=None)

        self.assertEqual(steps[0]['executor'], 'browser')

    def test_normalize_response_accepts_execution_plan_tool_call(self) -> None:
        response = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_execution_plan',
            'arguments': '{"steps":[{"executor":"browser","description":"Verify dashboard","allowed_capabilities":["browser.inspect"],"assertions":[{"action":"assert","assert_kind":"text","target":{"page":"current"},"operator":"contains","expected":{"value":"Dashboard"},"evidence_requirements":["dom_snapshot"]}]}]}',
        }}]}}]}

        steps = GlobalTestPlanner.normalize_response(response, configuration_id=None)

        self.assertEqual(steps[0]['description'], 'Verify dashboard')

    def test_visual_binding_normalizes_complete_zero_based_indexes(self) -> None:
        bindings = [{'assertion_index': 0}, {'assertion_index': 1}]

        normalized = [{**binding, 'assertion_index': binding['assertion_index'] + 1} for binding in bindings]

        self.assertEqual([binding['assertion_index'] for binding in normalized], [1, 2])

    def test_visual_binding_normalizes_numeric_string_index(self) -> None:
        binding = {'assertion_index': '1'}

        normalized = int(binding['assertion_index']) if binding['assertion_index'].isdigit() else binding['assertion_index']

        self.assertEqual(normalized, 1)
    def test_normalize_response_supports_ordered_browser_and_device_steps(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': (
                        '{"steps":[{"executor":"device_cli","description":"检查设备服务",'
                        '"device_id":"ainvr_5000"},{"executor":"browser",'
                        '"description":"确认设备在线","allowed_capabilities":["browser.inspect"],"assertions":[{"action":"assert",'
                        '"assert_kind":"text","target":{"locator":"body"},'
                        '"operator":"contains","expected":{"value":"在线"},'
                        '"evidence_requirements":["dom_snapshot"]}]}]}'
                    ),
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(
            response,
            configuration_id=7,
            task_description='检查 ainvr_5000 并确认设备在线',
        )

        self.assertEqual(steps[0]['executor'], 'device_cli')
        self.assertEqual(steps[0]['device_id'], 'ainvr_5000')
        self.assertEqual(steps[1]['executor'], 'browser')
        self.assertEqual(steps[1]['step_mode'], 'ai')
        self.assertEqual(steps[1]['assertions'][0]['assert_kind'], 'text')

    def test_normalize_response_rejects_browser_step_without_assertions(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"browser","description":"确认设备在线","allowed_capabilities":["browser.inspect"]}]}',
                },
            }],
        }

        with self.assertRaisesRegex(GlobalPlanError, '必须包含非空 assertions'):
            GlobalTestPlanner.normalize_response(
                response,
                configuration_id=7,
                task_description='确认设备在线',
            )

    def test_normalize_response_rejects_browser_step_with_verification_disabled(self) -> None:
        response = {'choices': [{'message': {'content': json.dumps({'steps': [{
            'executor': 'browser',
            'description': 'Open a menu',
            'allowed_capabilities': ['browser.act'],
            'assertions': [],
            'verification_required': False,
        }]})}}]}

        with self.assertRaisesRegex(GlobalPlanError, '禁止关闭验证'):
            GlobalTestPlanner.normalize_response(response, None)

    def test_normalize_response_rejects_browser_step_with_only_optional_assertions(self) -> None:
        response = {'choices': [{'message': {'content': json.dumps({'steps': [{
            'executor': 'browser',
            'description': 'Open a menu',
            'allowed_capabilities': ['browser.act', 'browser.inspect'],
            'assertions': [{
                'action': 'assert',
                'assert_kind': 'popup',
                'target': {'intent': 'opened menu'},
                'operator': 'exists',
                'expected': {'value': True},
                'evidence_requirements': ['element_state'],
                'required': False,
            }],
        }]})}}]}

        with self.assertRaisesRegex(GlobalPlanError, 'at least one required assertion'):
            GlobalTestPlanner.normalize_response(response, None)

    def test_normalize_response_adds_inspect_capability_for_postcondition(self) -> None:
        response = {'choices': [{'message': {'content': json.dumps({'steps': [{
            'executor': 'browser',
            'description': 'Open a menu',
            'allowed_capabilities': ['browser.act'],
            'assertions': [{
                'action': 'assert',
                'assert_kind': 'popup',
                'target': {'intent': 'opened menu'},
                'operator': 'exists',
                'expected': {'value': True},
                'evidence_requirements': ['element_state'],
            }],
        }]})}}]}

        steps = GlobalTestPlanner.normalize_response(response, None)

        self.assertEqual(steps[0]['allowed_capabilities'], ['browser.act', 'browser.inspect'])
        self.assertTrue(steps[0]['verification_required'])

    def test_normalize_response_rejects_visual_change_as_final_state_proof(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': json.dumps({'steps': [{
                        'executor': 'browser',
                        'step_mode': 'ai',
                        'description': 'Verify the requested state',
                        'allowed_capabilities': ['browser.inspect', 'browser.act', 'browser.capture'],
                        'assertions': [{
                            'action': 'assert',
                            'assert_kind': 'visual_change',
                            'target': {'page': 'current'},
                            'operator': 'equals',
                            'expected': {'value': True},
                            'evidence_requirements': ['visual_frame_before', 'visual_frame_after'],
                        }],
                    }]}),
                },
            }],
        }

        with self.assertRaisesRegex(GlobalPlanError, 'cannot prove a semantic final state'):
            GlobalTestPlanner.normalize_response(response, configuration_id=None)

    def test_normalize_response_rejects_device_step_without_environment(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"device_cli","description":"检查设备","device_id":"ainvr_5000"}]}',
                },
            }],
        }

        with self.assertRaisesRegex(GlobalPlanError, '未选择设备 CLI 环境'):
            GlobalTestPlanner.normalize_response(
                response,
                configuration_id=None,
                task_description='检查 ainvr_5000',
            )

    def test_normalize_response_rejects_device_id_not_in_user_goal(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"device_cli","description":"检查设备","device_id":"5"}]}',
                },
            }],
        }

        with self.assertRaisesRegex(GlobalPlanError, '未在原始需求中明确出现'):
            GlobalTestPlanner.normalize_response(
                response,
                configuration_id=5,
                task_description='连接 ainvr_5000 并检查服务状态',
            )

    def test_normalize_response_keeps_embedded_device_process_command(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"device_cli","description":"检查 manager 进程","device_id":"nvr_5003","command":"ps | grep \'[m]anager\'"}]}',
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(
            response,
            configuration_id=5,
            task_description='连接 nvr_5003，使用 ps 检查 manager 进程是否存在',
        )

        self.assertEqual(steps[0]['command'], "ps | grep '[m]anager'")

    def test_normalize_response_accepts_generic_data_factory_creation(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"data_factory","action":"create","description":"创建告警资源","resource_type":"alert_event","arguments":{"alert_type":"vehicle"},"allowed_capabilities":["data_factory.create"]}]}',
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(
            response,
            configuration_id=5,
            task_description='使用数据工厂创建告警资源',
        )

        self.assertEqual(steps[0]['executor'], 'data_factory')
        self.assertEqual(steps[0]['action'], 'create')
        self.assertEqual(steps[0]['resource_type'], 'alert_event')
        self.assertEqual(steps[0]['allowed_capabilities'], ['data_factory.create'])
        self.assertEqual(steps[0]['assertions'][0]['assert_kind'], 'api_resource')

    def test_normalize_response_preserves_prior_resource_correlation(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': json.dumps({'steps': [
                        {
                            'executor': 'data_factory',
                            'action': 'create',
                            'description': 'Create event',
                            'resource_type': 'alert_event',
                            'arguments': {'alert_type': 'person'},
                            'allowed_capabilities': ['data_factory.create'],
                        },
                        {
                            'executor': 'browser',
                            'description': 'Select its result',
                            'allowed_capabilities': ['browser.inspect', 'browser.act'],
                            'correlates_resource': 'alert_event',
                            'assertions': [{
                                'action': 'assert',
                                'assert_kind': 'element_state',
                                'target': {'intent': 'selected result detail'},
                                'operator': 'exists',
                                'expected': {'value': True},
                                'evidence_requirements': ['element_state'],
                            }],
                        },
                    ]}),
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(response, configuration_id=5)

        self.assertEqual(steps[1]['correlates_resource'], 'alert_event')

    def test_normalize_response_rejects_unknown_resource_correlation(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': json.dumps({'steps': [{
                        'executor': 'browser',
                        'description': 'Select a result',
                        'allowed_capabilities': ['browser.inspect', 'browser.act'],
                        'assertions': [{
                            'action': 'assert',
                            'assert_kind': 'element_state',
                            'target': {'intent': 'selected result'},
                            'operator': 'exists',
                            'expected': {'value': True},
                            'evidence_requirements': ['element_state'],
                        }],
                        'correlates_resource': 'alert_event',
                    }]}),
                },
            }],
        }

        with self.assertRaisesRegex(GlobalPlanError, 'correlates_resource'):
            GlobalTestPlanner.normalize_response(response, configuration_id=5)

    def test_normalize_response_rejects_legacy_data_factory_action(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': '{"steps":[{"executor":"data_factory","action":"report_vehicle_event"}]}',
                },
            }],
        }

        with self.assertRaisesRegex(GlobalPlanError, '只支持 action="create"'):
            GlobalTestPlanner.normalize_response(
                response,
                configuration_id=5,
                task_description='创建资源',
            )

    def test_normalize_response_preserves_browser_event_goal(self) -> None:
        response = {
            'choices': [{
                'message': {
                    'content': (
                        '{"steps":[{"executor":"browser","description":"使用事件构造工具产生真实 '
                        'Vehicle 事件，并在 Alert 页面验证","allowed_capabilities":["browser.inspect"],"assertions":[{"action":"assert",'
                        '"assert_kind":"text","target":{"locator":"body"},'
                        '"operator":"contains","expected":{"value":"Alert"},'
                        '"evidence_requirements":["dom_snapshot"]}]}]}'
                    ),
                },
            }],
        }

        steps = GlobalTestPlanner.normalize_response(
            response,
            configuration_id=5,
            task_description='为摄像头 5003_D13 通过事件构造工具产生真实 Vehicle 事件，并在 Alert 页面验证',
        )

        self.assertEqual([step['executor'] for step in steps], ['browser'])
        self.assertEqual(steps[0]['description'], '使用事件构造工具产生真实 Vehicle 事件，并在 Alert 页面验证')