import inspect
import json

from django.test import SimpleTestCase, TransactionTestCase
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

    def test_blocking_layer_accepts_assert_binding_to_layer_member_control(self) -> None:
        from apps.ai_testing.execution.blocking_state import build_blocking_state
        from apps.ai_testing.global_planner import VisualStepReplanner

        controls = [
            {'selector': '#dialog-confirm', 'blocking_layer': True, 'blocking_layer_id': 'body > div.ant-modal-root', 'dialog_layer': True, 'z_index': 1000},
            {'selector': '#dialog-title', 'blocking_layer': True, 'blocking_layer_id': 'body > div.ant-modal-root', 'dialog_layer': True, 'z_index': 1000},
        ]
        state = build_blocking_state(controls)

        VisualStepReplanner._validate_blocking_layer_action(
            [{'action': 'assert'}],
            controls,
            bindings=[{'assertion_index': 1, 'locator': '#dialog-title'}],
            blocking_state=state,
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

    def test_verify_only_step_inherits_verified_collection_locator(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        camera_group = '#root > div:nth-of-type(4) > div.cursor-grab'
        assertions = [{
            'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0},
            'target': {'intent': 'online camera entries in the site camera list'},
        }]
        predecessors = [
            {'assertions': [{'assert_kind': 'collection', 'operator': 'greater_than', 'target': {'intent': 'site search result rows matching the target site', 'locator': '#sites > div.site-item'}}]},
            {'assertions': [{'assert_kind': 'collection', 'operator': 'greater_than', 'target': {'intent': 'camera items listed for the selected site', 'locator': camera_group}}]},
        ]
        discovered = [
            {'selector': '#sites > div:nth-of-type(1)', 'group_selector': '#sites > div.site-item', 'group_size': 1},
            {'selector': '#root > div:nth-of-type(4) > div:nth-of-type(1)', 'group_selector': camera_group, 'group_size': 6},
        ]

        bindings = VisualStepReplanner._bind_verified_collection_continuation([], assertions, predecessors, [{'action': 'wait', 'status': 'completed'}], discovered)
        self.assertEqual(bindings[0]['assertion_index'], 1)
        self.assertEqual(bindings[0]['locator'], camera_group)

        # A completed state change means the collection is expected to come from this step's own action.
        self.assertEqual(
            VisualStepReplanner._bind_verified_collection_continuation([], assertions, predecessors, [{'action': 'click', 'status': 'completed', 'selector': '#tab'}], discovered),
            [],
        )
        # The predecessor group must still be a discovered repeated-item group on the current page.
        self.assertEqual(VisualStepReplanner._bind_verified_collection_continuation([], assertions, predecessors, [], discovered[:1]), [])
        # Two unbound collection assertions are ambiguous; leave them to the model.
        doubled = [*assertions, {'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'camera thumbnails'}}]
        self.assertEqual(VisualStepReplanner._bind_verified_collection_continuation([], doubled, predecessors, [], discovered), [])
        # Existing bindings are kept.
        existing = [{'assertion_index': 1, 'locator': camera_group}]
        self.assertEqual(VisualStepReplanner._bind_verified_collection_continuation(existing, assertions, predecessors, [], discovered), existing)

    def test_visual_planner_binds_verify_only_collection_from_verified_predecessor(self) -> None:
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from apps.ai_testing.global_planner import VisualStepReplanner

        camera_group = '#root > div:nth-of-type(4) > div.cursor-grab'
        # The model asserts but never names the group (the observed degenerate reply).
        model_reply = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_browser_actions',
            'arguments': json.dumps({'actions': [{'action': 'assert', 'assert_kind': 'collection', 'expected': {}}]}),
        }}]}}]}
        evidence = {
            'url': 'https://app.example.com/cameras',
            'visible_text': 'Site A Camera 13 Camera 14',
            'actionable_controls': [
                {'selector': '#search', 'name': 'Search site name...', 'role': 'textbox', 'tag': 'input', 'rect': {'x': 10, 'y': 10, 'width': 200, 'height': 24}},
            ],
            'observable_elements': [
                {'selector': '#root > div:nth-of-type(4) > div:nth-of-type(1)', 'group_selector': camera_group, 'group_size': 6, 'text': 'Camera 13', 'rect': {'x': 10, 'y': 80, 'width': 300, 'height': 60}},
            ],
            'accessibility_snapshot': {'snapshot_id': '', 'page_version': '', 'nodes': []},
            'blocking_state': {},
            'allowed_capabilities': ['browser.act', 'browser.inspect'],
            'assertions': [{'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'online camera entries in the site camera list'}}],
            'transition': None,
            'prior_actions': [],
            'verified_predecessors': [
                {'step_num': 3, 'description': 'Click the target site name in the search results.', 'assertions': [
                    {'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'camera items listed for the selected site', 'locator': camera_group}},
                ]},
            ],
            'page_metrics': {},
            'execution_resources': [],
        }

        with patch.object(VisualStepReplanner, '_get_active_model_config', new=AsyncMock(return_value=SimpleNamespace(model='m'))), \
                patch.object(VisualStepReplanner, '_get_active_prompt_content', new=AsyncMock(return_value='prompt')), \
                patch('apps.ai_testing.global_planner.OpenAICompatibleClient.complete', new=AsyncMock(return_value=model_reply)):
            actions = asyncio.run(VisualStepReplanner().create_actions('Wait 20 seconds for the site camera list and previews to finish loading.', evidence))

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['action'], 'assert')
        self.assertEqual([binding['locator'] for binding in actions[0]['assertion_bindings']], [camera_group])

    def test_create_plan_reports_whether_the_plan_came_from_cache(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, patch

        from apps.ai_testing.global_planner import GlobalTestPlanner

        cached_steps = [{'executor': 'browser', 'description': 'Open the page'}]
        with patch.object(GlobalTestPlanner, '_load_active_prompt_content', staticmethod(lambda prompt_type: 'prompt')), \
                patch.object(GlobalTestPlanner, '_load_environment_devices', staticmethod(lambda configuration_id: [])), \
                patch.object(GlobalTestPlanner, '_load_cached_plan_steps', staticmethod(lambda *args, **kwargs: cached_steps)), \
                patch.object(GlobalTestPlanner, 'normalize_response', lambda self, *args, **kwargs: cached_steps):
            planner = GlobalTestPlanner()
            steps = asyncio.run(planner.create_plan('Open the page and check it', 1, use_cache=True))
            self.assertEqual(steps, cached_steps)
            self.assertEqual(planner.last_plan_source, 'cache')

            bypass = GlobalTestPlanner()
            with patch.object(GlobalTestPlanner, '_get_active_model_configs', new=AsyncMock(return_value=[])):
                with self.assertRaises(GlobalPlanError):
                    asyncio.run(bypass.create_plan('Open the page and check it', 1, use_cache=False))
            self.assertEqual(bypass.last_plan_source, 'model')

    def test_bare_assert_is_rejected_on_an_unperformed_action_step(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        self.assertTrue(VisualStepReplanner._bare_assert_on_action_step('Click the Deactivate button for the selected user.', []))
        self.assertTrue(VisualStepReplanner._bare_assert_on_action_step('Select the Other option in the open reason dialog', [{'action': 'assert', 'status': 'completed'}]))
        self.assertFalse(VisualStepReplanner._bare_assert_on_action_step('Click the Deactivate button', [{'action': 'click', 'selector': '#x', 'status': 'completed'}]))
        self.assertFalse(VisualStepReplanner._bare_assert_on_action_step('Locate camera 5003_D13 and verify its thumbnail', []))
        self.assertFalse(VisualStepReplanner._bare_assert_on_action_step('Open the Magic dropdown control', []))
        self.assertFalse(VisualStepReplanner._bare_assert_on_action_step('In the left-side search box, search for ai@test.com.', []))
        source = inspect.getsource(VisualStepReplanner.create_actions)
        self.assertIn('_bare_assert_on_action_step(step_description', source)

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

    def test_exact_text_binding_derives_the_value_from_an_intent_and_prefers_the_anchored_control(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{
            'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True},
            'target': {'intent': 'monitoring view status control showing To Do'},
        }]
        elements = [
            {'name': 'To Do', 'selector': '#root > div:nth-of-type(1) > p:nth-of-type(1)', 'tag': 'p'},
            {'name': 'To Do', 'selector': '#root > div:nth-of-type(2) > p:nth-of-type(1)', 'tag': 'p'},
            {'name': 'To Do', 'selector': '[title="To Do"]', 'tag': 'span'},
        ]

        bindings = VisualStepReplanner._bind_exact_text_assertions([], assertions, elements)

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '[title="To Do"]'}])

    def test_exact_text_binding_leaves_value_display_assertions_to_the_runtime(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{
            'assert_kind': 'element_state', 'operator': 'contains', 'expected': {'value': 'Close'},
            'target': {'intent': 'status control displaying the selected value'},
        }]
        elements = [
            {'name': 'close', 'selector': '[aria-label="close"]', 'tag': 'button', 'role': 'button'},
            {'name': 'Close', 'selector': '[title="Close"]', 'tag': 'span', 'role': ''},
        ]

        self.assertEqual(VisualStepReplanner._bind_exact_text_assertions([], assertions, elements), [])

    def test_exact_text_binding_collapses_nested_menu_wrappers_to_the_innermost_element(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'text': 'Magic Search V2', 'intent': 'Magic Search V2 option'}}]
        base = 'body > div:nth-of-type(2) > div:nth-of-type(1)'
        elements = [
            {'name': 'Magic Search V2', 'selector': base, 'tag': 'div', 'role': ''},
            {'name': 'Magic Search V2', 'selector': f'{base} > ul:nth-of-type(1)', 'tag': 'ul', 'role': ''},
            {'name': 'Magic Search V2', 'selector': f'{base} > ul:nth-of-type(1) > li:nth-of-type(1)', 'tag': 'div', 'role': ''},
            {'name': 'Magic Search V2', 'selector': f'{base} > ul:nth-of-type(1) > li:nth-of-type(1) > span:nth-of-type(1)', 'tag': 'span', 'role': ''},
        ]

        bindings = VisualStepReplanner._bind_exact_text_assertions([], assertions, elements)
        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': f'{base} > ul:nth-of-type(1) > li:nth-of-type(1) > span:nth-of-type(1)'}])

        # Two unrelated exact matches stay ambiguous, but a model binding nested with one of them is accepted.
        elements.append({'name': 'Magic Search V2', 'selector': '#root > div:nth-of-type(9) > p:nth-of-type(1)', 'tag': 'p', 'role': ''})
        model = [{'assertion_index': 1, 'locator': f'{base} > ul:nth-of-type(1)'}]
        self.assertEqual(VisualStepReplanner._bind_exact_text_assertions(model, assertions, elements), model)
        with self.assertRaises(GlobalPlanError):
            VisualStepReplanner._bind_exact_text_assertions([{'assertion_index': 1, 'locator': '#elsewhere'}], assertions, elements)

    def test_plan_context_fingerprint_changes_with_prompt_or_devices(self) -> None:
        devices = [{'resource_type': 'environment_device', 'resource': {'role': 'main_device', 'camera_names': ['5003_D13'], 'site': '萧山区'}}]
        base = GlobalTestPlanner._plan_context_fingerprint('prompt', devices)

        self.assertEqual(base, GlobalTestPlanner._plan_context_fingerprint('prompt', devices))
        self.assertNotEqual(base, GlobalTestPlanner._plan_context_fingerprint('prompt v2', devices))
        self.assertNotEqual(base, GlobalTestPlanner._plan_context_fingerprint('prompt', []))
        self.assertEqual(len(base), 32)
        from unittest.mock import patch
        with patch('apps.ai_testing.global_planner.PLAN_CONTRACT_VERSION', 99):
            self.assertNotEqual(base, GlobalTestPlanner._plan_context_fingerprint('prompt', devices))

    def test_exact_text_mismatch_error_names_the_text_and_the_matching_elements(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': 'true'}, 'target': {'text': 'Magic Search V2', 'intent': 'option'}}]
        elements = [
            {'name': 'Magic Search V2', 'selector': '#menu > li:nth-of-type(1)', 'tag': 'li', 'role': 'menuitem'},
            {'name': 'Magic Search V2', 'selector': '#other > p:nth-of-type(1)', 'tag': 'li', 'role': 'menuitem'},
        ]
        with self.assertRaises(GlobalPlanError) as raised:
            VisualStepReplanner._bind_exact_text_assertions([{'assertion_index': 1, 'locator': '#search-box'}], assertions, elements)
        self.assertIn('Magic Search V2', str(raised.exception))
        self.assertIn('#menu > li:nth-of-type(1)', str(raised.exception))

        with self.assertRaises(GlobalPlanError) as raised:
            VisualStepReplanner._bind_exact_text_assertions([{'assertion_index': 1, 'locator': '#search-box'}], assertions, [{'name': 'Magic V2', 'selector': '#trigger', 'tag': 'button', 'role': 'button'}])
        self.assertIn('no discovered element shows it', str(raised.exception))

    def test_popup_resolution_accepts_a_serialised_true_expectation(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        layer = 'body > div:nth-of-type(3)'
        assertions = [{'assert_kind': 'popup', 'operator': 'exists', 'expected': {'value': 'true'}, 'target': {'intent': 'download confirmation dialog'}}]
        prior = [{'action': 'click', 'selector': '#download', 'status': 'completed'}]
        actions, bindings = VisualStepReplanner._resolve_visible_popup_assertion(
            [{'action': 'assert'}], [], assertions, prior, 'Open the download dialog', None,
            {'active_layer_ids': [layer], 'dialog_layer_ids': [layer]}, [{'selector': f'{layer} > h2:nth-of-type(1)', 'name': 'Download Clip', 'blocking_layer_id': layer}],
        )
        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': layer}])

    def test_exact_text_binding_keeps_model_binding_when_intent_value_is_ambiguous(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{
            'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True},
            'target': {'intent': 'status control showing To Do'},
        }]
        elements = [
            {'name': 'To Do', 'selector': '[title="To Do"]', 'tag': 'span'},
            {'name': 'To Do', 'selector': '#status-chip', 'tag': 'span'},
        ]
        model_bindings = [{'assertion_index': 1, 'locator': '#other'}]

        bindings = VisualStepReplanner._bind_exact_text_assertions(model_bindings, assertions, elements)

        self.assertEqual(bindings, model_bindings)

    def test_exact_text_binding_rejects_existing_mismatched_control(self) -> None:
        from apps.ai_testing.global_planner import GlobalPlanError, VisualStepReplanner

        with self.assertRaisesRegex(GlobalPlanError, 'assertion target text'):
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

    def test_visual_planner_drops_premature_bindings_instead_of_rejecting_the_action(self) -> None:
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from apps.ai_testing.global_planner import VisualStepReplanner

        model_reply = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_browser_actions',
            'arguments': json.dumps({
                'actions': [{'action': 'click', 'selector': '#site-manager-option'}],
                'assertion_bindings': [{'assertion_index': 1, 'locator': '#role-display'}],
            }),
        }}]}}]}
        evidence = {
            'url': 'https://app.example.com/team',
            'visible_text': 'Role Org Admin Site Manager',
            'actionable_controls': [
                {'selector': '#site-manager-option', 'name': 'Site Manager', 'role': 'option', 'tag': 'div', 'rect': {'x': 10, 'y': 10, 'width': 100, 'height': 20}},
                {'selector': '#role-display', 'name': 'Org Admin', 'role': '', 'tag': 'div', 'rect': {'x': 10, 'y': 60, 'width': 100, 'height': 20}},
            ],
            'observable_elements': [],
            'accessibility_snapshot': {'snapshot_id': '', 'page_version': '', 'nodes': []},
            'blocking_state': {},
            'allowed_capabilities': ['browser.act', 'browser.inspect'],
            'assertions': [{'assert_kind': 'field_value', 'operator': 'starts_with', 'expected': {'value': 'Site Manager'}, 'target': {'intent': 'role dropdown'}}],
            'transition': {'kind': 'select_option', 'value': 'Site Manager'},
            'prior_actions': [],
            'verified_predecessors': [],
            'page_metrics': {},
            'execution_resources': [],
        }

        with patch.object(VisualStepReplanner, '_get_active_model_config', new=AsyncMock(return_value=SimpleNamespace(model='m'))), \
                patch.object(VisualStepReplanner, '_get_active_prompt_content', new=AsyncMock(return_value='prompt')), \
                patch('apps.ai_testing.global_planner.OpenAICompatibleClient.complete', new=AsyncMock(return_value=model_reply)):
            actions = asyncio.run(VisualStepReplanner().create_actions('Select the Site Manager option from the role dropdown.', evidence))

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['action'], 'click')
        self.assertEqual(actions[0]['selector'], '#site-manager-option')
        self.assertNotIn('assertion_bindings', actions[0])

    def test_visible_dialog_resolution_never_rejects_but_respects_a_model_action_on_a_mismatching_dialog(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        layer = 'body > div:nth-of-type(3) > div:nth-of-type(1)'
        assertions = [{'assert_kind': 'popup', 'operator': 'exists', 'expected': {'value': True}, 'target': {'intent': 'download confirmation dialog'}}]
        prior = [{'action': 'click', 'selector': '#toolbar > button:nth-of-type(13)', 'status': 'completed'}]
        blocking = {'active_layer_ids': [layer], 'dialog_layer_ids': [layer]}
        case_dialog = [
            {'selector': f'{layer} > div:nth-of-type(1) > h2:nth-of-type(1)', 'name': 'Create Case from Playback', 'blocking_layer_id': layer},
            {'selector': f'{layer} > div:nth-of-type(2) > button:nth-of-type(1)', 'name': 'Cancel', 'blocking_layer_id': layer},
        ]
        download_dialog = [
            {'selector': f'{layer} > div:nth-of-type(1) > h2:nth-of-type(1)', 'name': 'Download Clip', 'blocking_layer_id': layer},
        ]

        for dialog in (download_dialog, case_dialog):
            actions, bindings = VisualStepReplanner._resolve_visible_popup_assertion(
                [{'action': 'assert'}], [], assertions, prior, 'Open the download dialog', None, blocking, dialog,
            )
            self.assertEqual((actions, bindings), ([{'action': 'assert'}], [{'assertion_index': 1, 'locator': layer}]))

        cancel = [{'action': 'click', 'selector': f'{layer} > div:nth-of-type(2) > button:nth-of-type(1)'}]
        self.assertEqual(
            VisualStepReplanner._resolve_visible_popup_assertion(cancel, [], assertions, prior, 'Open the download dialog', None, blocking, case_dialog),
            (cancel, []),
        )
        actions, bindings = VisualStepReplanner._resolve_visible_popup_assertion(
            cancel, [], assertions, prior, 'Open the download dialog', None, blocking, download_dialog,
        )
        self.assertEqual(actions, [{'action': 'assert'}])

        # A reason picker that only lists reasons must still verify a "reason selection dialog".
        reasons = [{'selector': f'{layer} > div:nth-of-type(1) > button:nth-of-type({n})', 'name': name, 'blocking_layer_id': layer} for n, name in enumerate(['Arson', 'Brawling', 'Other', 'Confirm'], start=1)]
        reason_assertion = [{'assert_kind': 'popup', 'operator': 'exists', 'expected': {'value': True}, 'target': {'intent': 'reason selection dialog opened after choosing Investigate'}}]
        actions, bindings = VisualStepReplanner._resolve_visible_popup_assertion(
            [{'action': 'assert'}], [], reason_assertion, prior, 'Select the Investigate option', None, blocking, reasons,
        )
        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': layer}])

    def test_layer_text_collects_names_inside_the_layer_only(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        layer = 'body > div:nth-of-type(3)'
        text = VisualStepReplanner._layer_text(layer, [
            {'selector': f'{layer} > h2:nth-of-type(1)', 'name': 'Download Clip'},
            {'selector': '#root > button:nth-of-type(1)', 'name': 'Go Live'},
            {'selector': '#confirm', 'name': 'Download', 'blocking_layer_id': layer},
            {'selector': f'{layer} > p:nth-of-type(1)', 'text': 'Select a clip'},
        ])

        self.assertEqual(text, 'Download Clip Download Select a clip')
        self.assertEqual(VisualStepReplanner._layer_text('', []), '')

    def test_camera_click_is_redirected_to_the_configured_test_camera_when_visible(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        resources = [{'resource_type': 'environment_device', 'resource_id': 'nvr_5003', 'resource': {'role': 'main_device', 'device_id': 'nvr_5003', 'camera_names': ['5003_D13']}}]
        parent = '#root > div:nth-of-type(1) > div:nth-of-type(16) > div:nth-of-type(1) > div:nth-of-type(1)'
        cards = [
            {'selector': f'{parent} > div:nth-of-type({n})', 'group_selector': f'{parent} > div', 'name': name, 'tag': 'div'}
            for n, name in enumerate(['5003_D03', '5003_D08', '5003_D09', '5003_D13'], start=1)
        ]
        click = [{'action': 'click', 'selector': cards[1]['selector']}]

        redirected = VisualStepReplanner._prefer_environment_device_control(click, cards, resources, 'Click the target camera thumbnail to open the live view')
        self.assertEqual(redirected[0]['selector'], cards[3]['selector'])

        # Wording that does not name the default/target device leaves the choice to the model.
        self.assertEqual(VisualStepReplanner._prefer_environment_device_control(click, cards, resources, 'Click the preview image of the first online camera'), click)
        # Already the configured camera, or target not visible, or no configured device: unchanged.
        right = [{'action': 'click', 'selector': cards[3]['selector']}]
        self.assertEqual(VisualStepReplanner._prefer_environment_device_control(right, cards, resources, 'Click the target camera thumbnail'), right)
        self.assertEqual(VisualStepReplanner._prefer_environment_device_control(click, cards[:3], resources, 'Click the target camera thumbnail'), click)
        self.assertEqual(VisualStepReplanner._prefer_environment_device_control(click, cards, [], 'Click the target camera thumbnail'), click)

    def test_field_value_binding_must_expose_the_expected_selected_value(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{'assert_kind': 'field_value', 'operator': 'starts_with', 'expected': {'value': 'Close'}, 'target': {'intent': 'Investigate dropdown selected value'}}]
        prior = [{'action': 'click', 'selector': '[title="Close"]', 'status': 'completed'}]
        elements = [
            {'selector': '[title="Investigate"]', 'name': 'Investigate', 'tag': 'span'},
            {'selector': '#status-display', 'name': 'Close', 'tag': 'span'},
        ]

        with self.assertRaises(GlobalPlanError):
            VisualStepReplanner._validate_dropdown_value_binding(
                [{'assertion_index': 1, 'locator': '[title="Investigate"]'}], assertions, prior, 'Select the Close option', None, elements,
            )
        VisualStepReplanner._validate_dropdown_value_binding(
            [{'assertion_index': 1, 'locator': '#status-display'}], assertions, prior, 'Select the Close option', None, elements,
        )

    def test_plan_prompt_lists_environment_test_devices(self) -> None:
        devices = [{'resource_type': 'environment_device', 'resource': {'role': 'main_device', 'device_id': 'nvr_5003', 'camera_names': ['5003_D13']}}]

        messages = GlobalTestPlanner._build_messages('goal', 1, 'prompt', [], devices)

        self.assertIn('5003_D13', messages[1]['content'])
        self.assertIn('Environment test devices', messages[1]['content'])
        self.assertIn('Prefer the search box', messages[1]['content'])
        self.assertIn('placeholder text', messages[0]['content'])
        self.assertNotIn('Environment test devices', GlobalTestPlanner._build_messages('goal', 1, 'prompt', [])[1]['content'])

    def test_missing_target_camera_hint_explains_how_to_reach_the_card(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        resources = [{'resource_type': 'environment_device', 'resource': {'role': 'main_device', 'camera_names': ['5003_D13']}}]
        hint = VisualStepReplanner._missing_target_camera_hint('Locate the camera for the default test device', resources, [{'name': '5003_D03'}, {'name': 'starred'}])
        self.assertIn('5003_D13', hint)
        self.assertIn('clear any search text', hint)
        # A search box echoing the camera name is not the camera card.
        self.assertIn('5003_D13', VisualStepReplanner._missing_target_camera_hint('Locate the camera for the default test device', resources, [{'name': '5003_D13', 'tag': 'input'}]))
        sited = [{'resource_type': 'environment_device', 'resource': {'role': 'main_device', 'camera_names': ['5003_D13'], 'site': '萧山区'}}]
        self.assertIn('萧山区', VisualStepReplanner._missing_target_camera_hint('Locate the camera for the default test device', sited, [{'name': 'starred'}]))
        self.assertEqual(VisualStepReplanner._missing_target_camera_hint('Locate the camera for the default test device', resources, [{'name': '5003_D13'}]), '')
        self.assertEqual(VisualStepReplanner._missing_target_camera_hint('Click the first online camera', resources, [{'name': 'x'}]), '')
        self.assertEqual(VisualStepReplanner._missing_target_camera_hint('Locate the default test device', [], [{'name': 'x'}]), '')

    def test_no_completed_action_hint_fires_only_for_unperformed_action_steps(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        hint = VisualStepReplanner._no_completed_action_hint('Click the target site name in the search results', [])
        self.assertIn('No action has been completed in this step yet', hint)
        self.assertEqual(VisualStepReplanner._no_completed_action_hint('Click the target site name', [{'action': 'click', 'status': 'completed'}]), '')
        self.assertEqual(VisualStepReplanner._no_completed_action_hint('Wait 20 seconds for previews to load', []), '')

    def test_visual_planner_accepts_assert_when_the_assertion_is_already_bound(self) -> None:
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from apps.ai_testing.global_planner import VisualStepReplanner

        model_reply = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_browser_actions',
            'arguments': json.dumps({'actions': [{'action': 'assert'}]}),
        }}]}}]}
        evidence = {
            'url': 'https://app.example.com/dashboard/streaming',
            'visible_text': 'cameras',
            'actionable_controls': [{'selector': '#cards > div:nth-of-type(1)', 'group_selector': '#cards > div', 'name': '5028/D1', 'tag': 'div', 'rect': {'x': 1, 'y': 1, 'width': 100, 'height': 60}}],
            'observable_elements': [],
            'accessibility_snapshot': {'snapshot_id': '', 'page_version': '', 'nodes': []},
            'blocking_state': {},
            'allowed_capabilities': ['browser.act', 'browser.inspect'],
            'assertions': [{'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'camera items', 'locator': '#cards > div'}}],
            'transition': {'kind': 'generic'},
            'prior_actions': [{'action': 'click', 'selector': '#btnSite', 'status': 'completed'}],
            'verified_predecessors': [],
            'page_metrics': {},
            'execution_resources': [],
        }

        with patch.object(VisualStepReplanner, '_get_active_model_config', new=AsyncMock(return_value=SimpleNamespace(model='m'))), \
                patch.object(VisualStepReplanner, '_get_active_prompt_content', new=AsyncMock(return_value='prompt')), \
                patch('apps.ai_testing.global_planner.OpenAICompatibleClient.complete', new=AsyncMock(return_value=model_reply)):
            actions = asyncio.run(VisualStepReplanner().create_actions('Click the target site name', evidence))

        self.assertEqual(actions[0]['action'], 'assert')

    def test_dropdown_selection_accepts_a_display_text_declared_in_the_step_description(self) -> None:
        transition = {'kind': 'select_option', 'value': 'Magic Search V2'}
        declared = [{'assert_kind': 'element_state', 'operator': 'equals', 'expected': {'value': 'Magic V2'}, 'target': {'intent': 'Magic dropdown label', 'text': 'Magic V2'}}]

        GlobalTestPlanner._validate_dropdown_selection_assertion(
            "Select the 'Magic Search V2' option; the Magic dropdown label then shows 'Magic V2'", declared, 2, transition,
        )
        GlobalTestPlanner._validate_dropdown_selection_assertion(
            "Select the 'Magic Search V2' option", [{'assert_kind': 'field_value', 'operator': 'starts_with', 'expected': {'value': 'Magic Search V2'}, 'target': {'intent': 'dropdown'}}], 2, transition,
        )
        with self.assertRaises(GlobalPlanError):
            GlobalTestPlanner._validate_dropdown_selection_assertion(
                "Select the 'Magic Search V2' option", declared, 2, transition,
            )

    def test_target_camera_thumbnail_is_bound_deterministically_when_rendered(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        resources = [{'resource_type': 'environment_device', 'resource': {'role': 'main_device', 'camera_names': ['5003_D13']}}]
        assertions = [{'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'intent': 'thumbnail on camera 5003_D13', 'text': '5003_D13', 'visual_content': 'image'}}]
        rendered = [{'selector': '#cards > div:nth-of-type(5)', 'name': '5003_D13', 'tag': 'div', 'has_visual_content': True}]
        placeholder = [{'selector': '#cards > div:nth-of-type(5)', 'name': '5003_D13', 'tag': 'div', 'has_visual_content': False}]
        search_box = [{'selector': '#search', 'name': '5003_D13', 'tag': 'input', 'has_visual_content': True}]

        self.assertEqual(
            VisualStepReplanner._bind_target_camera_thumbnail([], assertions, rendered, resources, 'Locate camera 5003_D13 among the results'),
            [{'assertion_index': 1, 'locator': '#cards > div:nth-of-type(5)', 'selection_basis': 'configured target camera card with rendered thumbnail'}],
        )
        self.assertEqual(VisualStepReplanner._bind_target_camera_thumbnail([], assertions, placeholder, resources, 'Locate camera 5003_D13'), [])
        self.assertEqual(VisualStepReplanner._bind_target_camera_thumbnail([], assertions, search_box, resources, 'Locate camera 5003_D13'), [])
        self.assertEqual(VisualStepReplanner._bind_target_camera_thumbnail([], assertions, rendered, resources, 'Click the first online camera'), [])
        existing = [{'assertion_index': 1, 'locator': '#other'}]
        self.assertEqual(VisualStepReplanner._bind_target_camera_thumbnail(existing, assertions, rendered, resources, 'Locate camera 5003_D13'), existing)

    def test_clicked_control_label_assertion_is_dropped_when_other_evidence_exists(self) -> None:
        assertions = [
            {'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'text': 'View Playback', 'intent': 'View Playback control'}},
            {'assert_kind': 'playback', 'operator': 'equals', 'expected': {'minimum_advanced_seconds': 2}, 'target': {'intent': 'recorded playback player'}},
        ]
        GlobalTestPlanner._remove_clicked_control_label_assertion('Click the View Playback button above the live view', assertions)
        self.assertEqual([a['assert_kind'] for a in assertions], ['playback'])

        only = [{'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'text': 'Team', 'intent': 'Team page header'}}]
        GlobalTestPlanner._remove_clicked_control_label_assertion('Click the Team option in the submenu', only)
        self.assertEqual(len(only), 1)

        hover = [
            {'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'text': 'Team', 'intent': 'Team submenu option'}},
            {'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'submenu items'}},
        ]
        GlobalTestPlanner._remove_clicked_control_label_assertion('Hover the organization control to reveal the Team submenu', hover)
        self.assertEqual(len(hover), 2)

    def test_vision_planning_fails_over_to_another_active_model_on_provider_outage(self) -> None:
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from apps.ai_testing.global_planner import VisualStepReplanner
        from apps.core.llm.client import LLMClientError

        model_reply = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_browser_actions',
            'arguments': json.dumps({'actions': [{'action': 'click', 'selector': '#go'}]}),
        }}]}}]}
        primary, backup = SimpleNamespace(id=1, name='primary'), SimpleNamespace(id=2, name='backup')
        complete = AsyncMock(side_effect=[LLMClientError('Google Gemini API返回错误 503: high demand'), model_reply])
        evidence = {
            'url': 'https://app.example.com/x', 'visible_text': '', 'actionable_controls': [{'selector': '#go', 'name': 'Go', 'tag': 'button', 'role': 'button', 'rect': {'x': 1, 'y': 1, 'width': 40, 'height': 20}}],
            'observable_elements': [], 'accessibility_snapshot': {'snapshot_id': '', 'page_version': '', 'nodes': []}, 'blocking_state': {},
            'allowed_capabilities': ['browser.act', 'browser.inspect'], 'assertions': [], 'transition': {'kind': 'generic'},
            'prior_actions': [], 'verified_predecessors': [], 'page_metrics': {}, 'execution_resources': [],
        }
        with patch.object(VisualStepReplanner, '_get_active_model_config', new=AsyncMock(return_value=primary)), \
                patch.object(VisualStepReplanner, '_get_fallback_model_configs', new=AsyncMock(return_value=[backup])), \
                patch.object(VisualStepReplanner, '_get_active_prompt_content', new=AsyncMock(return_value='prompt')), \
                patch('apps.ai_testing.global_planner.OpenAICompatibleClient.complete', new=complete):
            actions = asyncio.run(VisualStepReplanner().create_actions('Click go', evidence))

        self.assertEqual(actions[0]['selector'], '#go')
        self.assertEqual([call.args[0] for call in complete.await_args_list], [primary, backup])

        # Without a backup the outage propagates so the runtime's transient back-off can handle it.
        complete = AsyncMock(side_effect=LLMClientError('Google Gemini API返回错误 503: high demand'))
        with patch.object(VisualStepReplanner, '_get_active_model_config', new=AsyncMock(return_value=primary)), \
                patch.object(VisualStepReplanner, '_get_fallback_model_configs', new=AsyncMock(return_value=[])), \
                patch.object(VisualStepReplanner, '_get_active_prompt_content', new=AsyncMock(return_value='prompt')), \
                patch('apps.ai_testing.global_planner.OpenAICompatibleClient.complete', new=complete):
            with self.assertRaises(LLMClientError):
                asyncio.run(VisualStepReplanner().create_actions('Click go', evidence))

    def test_repeated_scroll_is_allowed_only_while_content_remains_to_scroll(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        scroll = [{'action': 'scroll', 'selector': '#alert-list'}]
        prior = [{'action': 'scroll', 'selector': '#alert-list', 'status': 'completed'}]
        more_below = {'scroll_containers': [{'selector': '#alert-list', 'remaining': 640, 'scroll_top': 300}]}
        VisualStepReplanner._validate_non_repeating_action(scroll, prior, [], '', None, more_below)
        exhausted = {'scroll_containers': [{'selector': '#alert-list', 'remaining': 0, 'scroll_top': 940}]}
        with self.assertRaises(GlobalPlanError):
            VisualStepReplanner._validate_non_repeating_action(scroll, prior, [], '', None, exhausted)
        with self.assertRaises(GlobalPlanError):
            VisualStepReplanner._validate_non_repeating_action(scroll, prior)

    def test_binding_collection_accepts_action_level_lists_aliases_and_assert_selectors(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        assertions = [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'status control showing To Do'}}]

        action_level = [{'action': 'assert', 'assertion_bindings': [{'assertion_index': 1, 'locator': '[title="To Do"]'}]}]
        self.assertEqual(
            VisualStepReplanner._collect_assertion_bindings({'actions': action_level}, action_level, assertions),
            [{'assertion_index': 1, 'locator': '[title="To Do"]'}],
        )
        self.assertNotIn('assertion_bindings', action_level[0])

        alias = [{'action': 'assert'}]
        self.assertEqual(
            VisualStepReplanner._collect_assertion_bindings({'bindings': [{'assertion_index': 1, 'locator': '#status'}]}, alias, assertions),
            [{'assertion_index': 1, 'locator': '#status'}],
        )

        selector_only = [{'action': 'assert', 'selector': '[title="To Do"]', 'assert_kind': 'element_state'}]
        self.assertEqual(
            VisualStepReplanner._collect_assertion_bindings({'actions': selector_only}, selector_only, assertions),
            [{'assertion_index': 1, 'locator': '[title="To Do"]', 'selection_basis': 'assert action selector'}],
        )

        two_assertions = assertions + [{'assert_kind': 'field_value', 'operator': 'equals', 'target': {'intent': 'role'}}]
        self.assertEqual(VisualStepReplanner._collect_assertion_bindings({'actions': selector_only}, selector_only, two_assertions), [])

        click = [{'action': 'click', 'selector': '#row'}]
        self.assertEqual(VisualStepReplanner._collect_assertion_bindings({'actions': click}, click, assertions), [])

        duplicated = {'assertion_bindings': [{'assertion_index': 1, 'locator': '#a'}, {'assertion_index': 1, 'locator': '#a'}]}
        self.assertEqual(len(VisualStepReplanner._collect_assertion_bindings(duplicated, [{'action': 'assert'}], assertions)), 1)

        with self.assertRaises(GlobalPlanError):
            VisualStepReplanner._collect_assertion_bindings({'assertion_bindings': 'bad'}, [{'action': 'assert'}], assertions)

    def test_visual_planner_binds_assert_action_selector_when_top_level_bindings_are_missing(self) -> None:
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from apps.ai_testing.global_planner import VisualStepReplanner

        model_reply = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_browser_actions',
            'arguments': json.dumps({
                'actions': [{'action': 'assert', 'selector': '[title="To Do"]', 'assert_kind': 'element_state'}],
            }),
        }}]}}]}
        evidence = {
            'url': 'https://app.example.com/dashboard/alerts/basic',
            'visible_text': 'Alert To Do Critical',
            'actionable_controls': [
                {'selector': '[title="To Do"]', 'name': 'To Do', 'role': '', 'tag': 'span', 'rect': {'x': 520, 'y': 819, 'width': 104, 'height': 30}},
                {'selector': '#root > div:nth-of-type(1) > p:nth-of-type(1)', 'name': 'To Do', 'role': '', 'tag': 'p', 'rect': {'x': 274, 'y': 274, 'width': 55, 'height': 20}},
            ],
            'observable_elements': [],
            'accessibility_snapshot': {'snapshot_id': '', 'page_version': '', 'nodes': []},
            'blocking_state': {},
            'allowed_capabilities': ['browser.act', 'browser.inspect'],
            'assertions': [{'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'intent': 'monitoring view status control showing To Do'}}],
            'transition': {'kind': 'generic'},
            'prior_actions': [{'action': 'click', 'selector': '#row-1', 'status': 'completed'}],
            'verified_predecessors': [],
            'page_metrics': {},
            'execution_resources': [],
        }

        with patch.object(VisualStepReplanner, '_get_active_model_config', new=AsyncMock(return_value=SimpleNamespace(model='m'))), \
                patch.object(VisualStepReplanner, '_get_active_prompt_content', new=AsyncMock(return_value='prompt')), \
                patch('apps.ai_testing.global_planner.OpenAICompatibleClient.complete', new=AsyncMock(return_value=model_reply)):
            actions = asyncio.run(VisualStepReplanner().create_actions('Click the first result in the alerts list to open its monitoring detail view', evidence))

        self.assertEqual(actions[0]['action'], 'assert')
        self.assertEqual([b['locator'] for b in actions[0]['assertion_bindings']], ['[title="To Do"]'])

    def test_non_repeating_rule_allows_retrying_a_selector_that_did_not_resolve(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        VisualStepReplanner._validate_non_repeating_action(
            [{'action': 'click', 'selector': '#toolbar > button:nth-of-type(15)'}],
            [{'action': 'click', 'selector': '#toolbar > button:nth-of-type(15)', 'status': 'failed', 'error': 'ValueError: click selector did not resolve on the current page: #toolbar > button:nth-of-type(15)'}],
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

        with self.assertRaisesRegex(GlobalPlanError, 'assertion target text'):
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

        source = inspect.getsource(VisualStepReplanner._complete_with_failover)

        self.assertIn('asyncio.wait_for', source)
        self.assertIn('settings.TIMEOUTS_AI_REQUEST', source)
        self.assertNotIn('max_tokens=', source)
        self.assertIn('self._complete_with_failover(config, messages, len(assertions))', inspect.getsource(VisualStepReplanner.create_actions))

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

class PlanCacheFingerprintTests(TransactionTestCase):
    serialized_rollback = True

    def test_cached_plan_is_reused_only_under_the_same_planning_context(self) -> None:
        from apps.ai_testing.execution.plan_persistence import persist_execution_plan
        from apps.ai_testing.models import AIExecutionRecord

        record = AIExecutionRecord.objects.create(case_name='Cache fingerprint')
        persist_execution_plan(record.id, 'goal text', [{'description': 'step one', 'executor': 'browser'}], context_fingerprint='ctx-a')

        self.assertEqual(len(GlobalTestPlanner._load_cached_plan_steps('goal text', None, 'ctx-a')), 1)
        self.assertEqual(GlobalTestPlanner._load_cached_plan_steps('goal text', None, 'ctx-b'), [])
        # Legacy callers without a fingerprint keep the latest plan.
        self.assertEqual(len(GlobalTestPlanner._load_cached_plan_steps('goal text', None)), 1)

        legacy = AIExecutionRecord.objects.create(case_name='Legacy plan')
        persist_execution_plan(legacy.id, 'legacy goal', [{'description': 'old step', 'executor': 'browser'}])
        # Proven plans without a fingerprint stay valid for ordinary goals but not for device goals.
        self.assertEqual(len(GlobalTestPlanner._load_cached_plan_steps('legacy goal', None, 'ctx-a')), 1)
        self.assertEqual(GlobalTestPlanner._load_cached_plan_steps('legacy goal', None, 'ctx-a', allow_legacy=False), [])

    def test_passed_plan_is_preferred_over_a_newer_failed_regeneration(self) -> None:
        from apps.ai_testing.execution.plan_persistence import persist_execution_plan
        from apps.ai_testing.models import AIExecutionRecord

        passed = AIExecutionRecord.objects.create(case_name='Passed run', status='passed')
        persist_execution_plan(passed.id, 'stable goal', [{'description': 'proven step', 'executor': 'browser'}], context_fingerprint='ctx-old')
        failed = AIExecutionRecord.objects.create(case_name='Failed run', status='failed')
        persist_execution_plan(failed.id, 'stable goal', [{'description': 'regenerated step', 'executor': 'browser'}], context_fingerprint='ctx-new')

        steps = GlobalTestPlanner._load_cached_plan_steps('stable goal', None, 'ctx-new')
        self.assertEqual(steps[0]['description'], 'proven step')
        # Device goals may not reuse a plan generated under another device configuration.
        steps = GlobalTestPlanner._load_cached_plan_steps('stable goal', None, 'ctx-new', allow_legacy=False)
        self.assertEqual(steps[0]['description'], 'regenerated step')

    def test_create_plan_scopes_device_fingerprint_to_device_goals(self) -> None:
        import inspect
        source = inspect.getsource(GlobalTestPlanner.create_plan)
        self.assertIn('device_goal = refers_to_target_device(task_description, default_device_camera_names(devices))', source)
        self.assertIn('devices if device_goal else []', source)
        self.assertIn('allow_legacy=not device_goal', source)
