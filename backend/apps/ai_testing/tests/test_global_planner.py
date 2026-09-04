import inspect

from django.test import SimpleTestCase
from types import SimpleNamespace

from apps.core.browser_auth import resolve_browser_login
from apps.ai_testing.execution.capabilities import allowed_browser_actions
from apps.ai_testing.global_planner import GlobalPlanError, GlobalTestPlanner


class GlobalTestPlannerTests(SimpleTestCase):
    def test_planner_retry_feedback_includes_specific_contract_error(self) -> None:
        source = inspect.getsource(GlobalTestPlanner.create_plan)

        self.assertIn('previous plan violated this contract', source)
        self.assertIn('Correct that specific violation', source)
        self.assertIn('Rebuild the full ordered plan rather than appending a repair step', source)
        self.assertIn('max_tokens=4096', source)

    def test_cached_plan_is_revalidated_without_reusing_execution_results(self) -> None:
        create_source = inspect.getsource(GlobalTestPlanner.create_plan)
        cache_source = inspect.getsource(GlobalTestPlanner._load_cached_plan_steps)

        self.assertIn('return self.normalize_response(', create_source)
        self.assertIn("reason='initial'", cache_source)
        self.assertIn('environment_configuration_id=environment_configuration_id', cache_source)
        self.assertNotIn('attempt', cache_source)
        self.assertNotIn('evidence', cache_source)
        self.assertNotIn('quality', cache_source)

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

    def test_unbound_assertion_error_directs_state_changing_recovery(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('return one state-changing action', source)
        self.assertIn('instead of assert', source)
        self.assertIn("{'field_value', 'popup', 'element_state', 'collection'}", source)

    def test_final_field_assertion_supersedes_matching_precondition_assertion(self) -> None:
        steps = [
            {'assertions': [{
                'assert_kind': 'element_state',
                'target': {'intent': 'investigation category options'},
                'operator': 'exists',
                'required': True,
            }]},
            {'assertions': [{
                'assert_kind': 'field_value',
                'target': {'intent': 'investigation category field'},
                'operator': 'contains',
                'required': True,
            }]},
        ]

        GlobalTestPlanner._demote_superseded_precondition_assertions(steps)

        self.assertFalse(steps[0]['assertions'][0]['required'])
        self.assertFalse(steps[0]['verification_required'])
        self.assertTrue(steps[1]['assertions'][0]['required'])

    def test_unrelated_precondition_assertion_remains_required(self) -> None:
        steps = [
            {'assertions': [{
                'assert_kind': 'element_state',
                'target': {'intent': 'selected record detail'},
                'operator': 'exists',
                'required': True,
            }]},
            {'assertions': [{
                'assert_kind': 'field_value',
                'target': {'intent': 'investigation category field'},
                'operator': 'contains',
                'required': True,
            }]},
        ]

        GlobalTestPlanner._demote_superseded_precondition_assertions(steps)

        self.assertTrue(steps[0]['assertions'][0]['required'])

    def test_planner_prompt_distinguishes_static_ui_from_native_media(self) -> None:
        messages = GlobalTestPlanner._build_messages('Verify a static image', None, 'Base prompt')

        self.assertIn('Use element_state or collection for static UI elements', messages[0]['content'])
        self.assertIn('never assert inferred CSS states such as selected', messages[0]['content'])
        self.assertIn('assert an objectively observable detail element', messages[0]['content'])
        self.assertIn('Use media or video only for native audio/video elements', messages[0]['content'])
        self.assertIn('Every fill, press, and select action must include a non-empty value', messages[0]['content'])
        self.assertIn('Use fill only when the selected actionable control has editable=true', messages[0]['content'])
        self.assertIn('minimum_advanced_seconds', messages[0]['content'])
        self.assertIn('do not output login steps or login assertions', messages[0]['content'])
        self.assertIn('action="create" exactly', messages[0]['content'])
        self.assertIn('allowed_capabilities exactly as ["data_factory.create"]', messages[0]['content'])
        self.assertIn('exactly one user-visible state transition', messages[0]['content'])
        self.assertIn('Never assert the final state before the commit action', messages[0]['content'])
        self.assertIn('Never create conditional steps', messages[0]['content'])
        self.assertIn('plan and verify the field update before the irreversible status transition', messages[0]['content'])

    def test_visual_planner_prompt_uses_prior_actions_to_advance_transactions(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('Prior actions:', source)
        self.assertIn('do not repeat the same action and selector', source)
        self.assertIn('return action="assert" with that locator binding immediately', source)
        self.assertIn('query or filter control whose name contains only the field label', source)
        self.assertIn('detail-context control whose own name or container_text contains that current value', source)

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
        VisualStepReplanner._validate_visible_record_correlation(
            actions,
            [
                {'tag': 'input', 'editable': True, 'selector': '#search', 'name': 'Camera A'},
                {'tag': 'div', 'selector': '#record', 'container_text': 'Camera A'},
            ],
            [{'resource': {'result_correlation': {'match_values': ['Camera A']}}}],
            'Open the created record',
        )

        self.assertEqual(actions[0]['selector'], '#record')

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
            [{'action': 'scroll', 'selector': '#panel'}],
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

    def test_visual_planner_correlates_records_by_resource_values_before_order(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('result_correlation.match_values', source)
        self.assertIn('select the unique highest-scoring record', source)
        self.assertIn('never fall back to first_visible', source)

    def test_visual_planner_requires_unique_runtime_correlated_visible_record(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        controls = [
            {'selector': '#unrelated', 'name': 'Other record', 'container_text': 'Camera B'},
            {'selector': '#matched', 'name': 'Generated record', 'container_text': 'Camera A person'},
        ]
        resources = [{'resource': {'result_correlation': {'match_values': ['Camera A', 'person']}}}]

        VisualStepReplanner._validate_visible_record_correlation(
            [{'action': 'click', 'selector': '#matched'}], controls, resources, 'Open generated record',
        )
        lower_scoring_action = [{'action': 'click', 'selector': '#unrelated'}]
        VisualStepReplanner._validate_visible_record_correlation(
            lower_scoring_action, controls, resources, 'Open generated record',
        )
        self.assertEqual(lower_scoring_action, [{'action': 'click', 'selector': '#matched'}])

        search_action = [{'action': 'fill', 'selector': '#search', 'value': 'Camera A'}]
        VisualStepReplanner._validate_visible_record_correlation(
            search_action, controls, resources, 'Open generated record',
        )
        self.assertEqual(search_action, [{'action': 'click', 'selector': '#matched'}])
        VisualStepReplanner._validate_visible_record_correlation(
            [{'action': 'click', 'selector': '#navigation-link'}],
            controls,
            resources,
            'Navigate to records\nChoose a different action sequence.',
        )

    def test_visual_planner_uses_platform_ai_request_timeout(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('asyncio.wait_for', source)
        self.assertIn('settings.TIMEOUTS_AI_REQUEST', source)
        self.assertIn('max(config.max_tokens, 8192)', source)

    def test_sync_planner_database_loaders_close_old_connections(self) -> None:
        from apps.ai_testing.global_planner import GlobalTestPlanner, VisualStepReplanner

        loaders = (
            VisualStepReplanner._load_active_model_config,
            GlobalTestPlanner._load_active_model_configs,
            GlobalTestPlanner._load_active_prompt_content,
            GlobalTestPlanner._load_data_factory_resources,
        )

        for loader in loaders:
            with self.subTest(loader=loader.__name__):
                self.assertIn('close_old_connections()', inspect.getsource(loader))

    def test_visual_planner_prompt_uses_page_metrics_for_offscreen_controls(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        source = inspect.getsource(VisualStepReplanner.create_actions)

        self.assertIn('Page metrics:', source)
        self.assertIn('scroll to reveal more content', source)
        self.assertIn('page_metrics.scroll_containers', source)
        self.assertIn('continue scrolling that container instead of guessing an unnamed icon control', source)

    def test_visual_planner_enforces_offscreen_search_before_unnamed_controls(self) -> None:
        from apps.ai_testing.global_planner import VisualStepReplanner

        validator = VisualStepReplanner._validate_offscreen_search_action
        metrics = {'scroll_containers': [{'selector': '#panel', 'remaining': 500}]}
        controls = [{'selector': '#anonymous', 'name': '', 'blocking_layer': False}]

        with self.assertRaisesRegex(GlobalPlanError, 'must scroll'):
            validator([{'action': 'wait'}], metrics, controls, [])
        with self.assertRaisesRegex(GlobalPlanError, 'before guessing an unnamed control'):
            validator([{'action': 'click', 'selector': '#anonymous'}], metrics, controls, [])

        validator(
            [{'action': 'click', 'selector': '#anonymous'}],
            metrics,
            controls,
            [{'action': 'scroll', 'selector': '#panel'}],
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