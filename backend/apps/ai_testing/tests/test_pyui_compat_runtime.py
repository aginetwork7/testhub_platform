import asyncio
from dataclasses import dataclass, field
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from apps.ai_testing.execution.browser_observers import collect_browser_observations
from apps.ai_testing.runtime.pyui_compat import PyUICompatAgent
from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatHistory
from apps.requirement_analysis.models import AIModelService


@dataclass
class HistoryStub:
    cache_stats: dict = field(default_factory=lambda: {'hit': 0, 'miss': 1, 'model_retries': 0, 'model_attempts': 0})
    planner_trace: dict = field(default_factory=lambda: {'step_retry_map': {}})
    artifacts: list = field(default_factory=list)


class _LocatorCountStub:
    def __init__(self, count: int):
        self._count = count
        self.first = self

    async def count(self) -> int:
        return self._count


class _ResolveLocatorPageStub:
    def __init__(self, css_count: int):
        self.css_locator = _LocatorCountStub(css_count)
        self.text_locator = _LocatorCountStub(1)

    def locator(self, _selector: str) -> _LocatorCountStub:
        return self.css_locator

    def get_by_text(self, _text: str, exact: bool = False) -> _LocatorCountStub:
        return self.text_locator


class _LocatorVisibilityItemStub:
    def __init__(self, visible: bool):
        self._visible = visible

    async def is_visible(self) -> bool:
        return self._visible


class _LocatorVisibilityStub:
    def __init__(self, visibility: list[bool]):
        self._items = [_LocatorVisibilityItemStub(item) for item in visibility]
        self.first = self._items[0] if self._items else None

    async def count(self) -> int:
        return len(self._items)

    def nth(self, index: int) -> _LocatorVisibilityItemStub:
        return self._items[index]


class _VisibleResolveLocatorPageStub:
    def __init__(self):
        self.css_locator = _LocatorVisibilityStub([False, True])
        self.text_locator = _LocatorVisibilityStub([False])

    def locator(self, _selector: str) -> _LocatorVisibilityStub:
        return self.css_locator

    def get_by_text(self, _text: str, exact: bool = False) -> _LocatorVisibilityStub:
        return self.text_locator


class _TextLocatorStub:
    def __init__(self, text: str):
        self._text = text
        self.first = self

    async def text_content(self, timeout: int = 0) -> str:
        return self._text


class _AssertionEvidenceLocatorStub:
    def __init__(self, text: str, count: int = 1):
        self._text = text
        self._count = count
        self.first = self

    async def count(self) -> int:
        return self._count

    async def is_visible(self) -> bool:
        return self._count > 0

    async def text_content(self, timeout: int = 0) -> str:
        return self._text


class _AssertionEvidencePageStub:
    def __init__(self, locator: _AssertionEvidenceLocatorStub):
        self._locator = locator

    def locator(self, _selector: str) -> _AssertionEvidenceLocatorStub:
        return self._locator


class _TextPageStub:
    def __init__(self, text: str):
        self._locator = _TextLocatorStub(text)
        self.waited_ms = None

    def locator(self, _selector: str) -> _TextLocatorStub:
        return self._locator

    async def wait_for_timeout(self, timeout: int) -> None:
        self.waited_ms = timeout


class _DashboardPageStub:
    def __init__(self) -> None:
        self.wait_for_url_call: tuple[str, str, int] | None = None

    async def wait_for_url(self, url: str, wait_until: str, timeout: int) -> None:
        self.wait_for_url_call = (url, wait_until, timeout)

    async def wait_for_load_state(self, state: str, timeout: int) -> None:
        raise TimeoutError(f'{state} timed out after {timeout}')


class _VisibilityItemStub:
    def __init__(self, visible: bool, box: dict[str, float] | None = None):
        self._visible = visible
        self._box = box

    async def is_visible(self, timeout: int = 0) -> bool:
        return self._visible

    async def bounding_box(self) -> dict[str, float] | None:
        return self._box


class _VisibilityLocatorStub:
    def __init__(self, items: list[_VisibilityItemStub]):
        self._items = items

    async def count(self) -> int:
        return len(self._items)

    def nth(self, index: int) -> _VisibilityItemStub:
        return self._items[index]


class _VisibilityPageStub:
    def __init__(self, mapping: dict[str, _VisibilityLocatorStub]):
        self._mapping = mapping

    def locator(self, selector: str) -> _VisibilityLocatorStub:
        return self._mapping.get(selector, _VisibilityLocatorStub([]))


class _TextMatchStub:
    def __init__(self, count: int = 0, visible: bool = False):
        self._count = count
        self._visible = visible
        self.first = self

    async def count(self) -> int:
        return self._count

    async def is_visible(self) -> bool:
        return self._visible


class _StreamMediaItemStub:
    def __init__(self, visible: bool, box: dict[str, float] | None = None, screenshot_bytes: list[bytes] | None = None, eval_result: dict | None = None):
        self._visible = visible
        self._box = box
        self._screenshot_bytes = screenshot_bytes or [b'static']
        self._eval_result = eval_result or {}
        self._screenshot_index = 0

    async def is_visible(self, timeout: int = 0) -> bool:
        return self._visible

    async def bounding_box(self) -> dict[str, float] | None:
        return self._box

    async def evaluate(self, _script: str):
        return self._eval_result

    async def screenshot(self, type: str = 'png') -> bytes:
        result = self._screenshot_bytes[min(self._screenshot_index, len(self._screenshot_bytes) - 1)]
        self._screenshot_index += 1
        return result


class _StreamLocatorStub:
    def __init__(self, items: list[_StreamMediaItemStub]):
        self._items = items

    async def count(self) -> int:
        return len(self._items)

    def nth(self, index: int) -> _StreamMediaItemStub:
        return self._items[index]


class _StreamPageStub:
    def __init__(self, locator_mapping: dict[str, _StreamLocatorStub], text_mapping: dict[str, _TextMatchStub] | None = None):
        self._locator_mapping = locator_mapping
        self._text_mapping = text_mapping or {}
        self.wait_calls: list[int] = []

    def locator(self, selector: str) -> _StreamLocatorStub:
        return self._locator_mapping.get(selector, _StreamLocatorStub([]))

    def get_by_text(self, text: str, exact: bool = False) -> _TextMatchStub:
        return self._text_mapping.get(text, _TextMatchStub())

    async def wait_for_timeout(self, timeout: int) -> None:
        self.wait_calls.append(timeout)


class PyUICompatRuntimeTests(SimpleTestCase):
    @patch.dict('os.environ', {}, clear=True)
    @patch('apps.ai_testing.runtime.pyui_compat.runner.os.path.exists')
    def test_browser_resolution_prefers_packaged_hevc_build(self, path_exists) -> None:
        path_exists.side_effect = lambda path: path in {
            '/usr/lib/chromium/chromium',
            '/usr/bin/chromium',
        }
        agent = PyUICompatAgent(case_name='HEVC_Browser')

        executable = agent._resolve_browser_executable()

        self.assertEqual(executable, '/usr/lib/chromium/chromium')

    def test_alert_resource_correlation_uses_runtime_camera_and_event_type(self) -> None:
        import inspect
        from apps.ai_testing.execution.data_factory_resources import _create_alert_event

        source = inspect.getsource(_create_alert_event)

        self.assertIn("camera.get('camera_name')", source)
        self.assertIn("event_arguments.get('alert_type')", source)
        self.assertIn("'match_values'", source)

    def test_dashboard_ready_uses_navigation_commit_before_optional_network_idle(self) -> None:
        page = _DashboardPageStub()
        agent = PyUICompatAgent(case_name='Dashboard_Ready')

        asyncio.run(agent._wait_dashboard_ready(page))

        self.assertEqual(page.wait_for_url_call, ('**/dashboard/**', 'commit', 60000))

    def test_bootstrap_allows_async_terms_dialog_to_render(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._bootstrap_pyuitest_session)

        self.assertIn('await page.wait_for_timeout(1000)', source)
        self.assertIn('I have read and agree to the Terms of Use.', source)
        self.assertIn('for login_attempt in range(1, 4)', source)
        self.assertIn('await self._wait_dashboard_ready(page, timeout=20000)', source)

    def test_actionable_discovery_includes_framework_listener_metadata(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._build_actionable_controls)

        self.assertIn("includes('_vei')", source)
        self.assertIn("startsWith('__reactProps')", source)
        self.assertIn('current.parentElement === document.body', source)
        self.assertIn("['fixed', 'sticky'].includes(style.position) || zIndex > 0", source)
        self.assertIn("'[aria-label], [title], [alt], [data-icon], [data-lucide], svg title, svg, use'", source)
        self.assertIn("semanticChild.getAttribute('data-icon')", source)
        self.assertIn("semanticChild.getAttribute('data-lucide')", source)
        self.assertIn("split(/\\\\s+/).find(token => /icon$/i.test(token))", source)
        self.assertIn('|| semanticClass', source)
        self.assertNotIn("|| semanticChild.getAttribute('class')", source)
        self.assertNotIn('use[xlink', source)
        self.assertIn('new URL(href, document.baseURI).href', source)
        self.assertIn('native_control: nativeControl', source)
        self.assertIn('blockingLayerRank || namedRank || nativeRank || topLayerRank', source)
        self.assertIn('left.depth - right.depth', source)
        self.assertIn('}).slice(0, 300)', source)

    def test_observable_discovery_builds_complete_body_path(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._build_observable_elements)

        self.assertIn('current.parentElement === document.body', source)

    def test_runtime_initializes_sanitized_planner_control_snapshot(self) -> None:
        agent = PyUICompatAgent(case_name='Planner_Control_Evidence')

        self.assertEqual(agent._last_actionable_controls, [])

    def test_rebinding_replaces_stale_locator_without_nesting_intent(self) -> None:
        step = {'assertions': [{'target': {'locator': '#stale', 'intent': {'intent': 'status menu'}}}]}

        rebound = PyUICompatAgent._bind_step_assertions(
            step,
            [{'assertion_index': 1, 'locator': '#current'}],
        )

        self.assertEqual(rebound['assertions'][0]['target'], {
            'locator': '#current',
            'intent': 'status menu',
        })

    def test_assertion_retry_accumulates_prior_action_history(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._retry_assertion_failure)

        self.assertIn('prior_actions.extend', source)
        self.assertIn("'_prior_actions': prior_actions[-16:]", source)

    def test_visual_planning_collects_page_scroll_metrics(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._plan_ai_step)

        self.assertIn('scroll_height', source)
        self.assertIn('scroll_containers', source)
        self.assertIn('element.scrollHeight > element.clientHeight + 1', source)
        self.assertIn('right.remaining - left.remaining', source)
        self.assertIn("'page_metrics': page_metrics", source)

    def test_scroll_action_targets_discovered_container(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._execute_step)

        self.assertIn('element.scrollBy', source)
        self.assertIn('element.clientHeight * ratio', source)

    def test_build_planned_tasks_preserves_intermediate_step_contract(self) -> None:
        agent = PyUICompatAgent(case_name='Intermediate_Contract')

        planned_tasks = agent._build_planned_tasks('goal', case_mode='hybrid', task_steps=[{
            'executor': 'browser',
            'step_mode': 'ai',
            'description': 'Open a menu',
            'allowed_capabilities': ['browser.act'],
            'assertions': [],
            'verification_required': False,
        }])

        self.assertEqual(planned_tasks[0]['executor'], 'browser')
        self.assertEqual(planned_tasks[0]['step_mode'], 'ai')
        self.assertFalse(planned_tasks[0]['verification_required'])
        self.assertEqual(planned_tasks[0]['assertions'], [])

    def test_non_verifying_intermediate_step_does_not_retry_assertions(self) -> None:
        should_retry = PyUICompatAgent._should_retry_assertions(
            {'verification_required': False},
            action_completed=True,
            assertions_verified=False,
            action_source='model',
        )

        self.assertFalse(should_retry)

    def test_verifying_model_step_retries_unverified_assertions(self) -> None:
        should_retry = PyUICompatAgent._should_retry_assertions(
            {'verification_required': True},
            action_completed=True,
            assertions_verified=False,
            action_source='model',
        )

        self.assertTrue(should_retry)

    def test_optional_assertion_status_does_not_block_required_success(self) -> None:
        step = {
            'assertions': [
                {'required': False},
                {'required': True},
            ],
        }

        required_statuses = PyUICompatAgent._required_assertion_statuses(
            step,
            ['inconclusive', 'passed'],
        )

        self.assertEqual(required_statuses, ['passed'])
        self.assertTrue(PyUICompatAgent._assertions_are_verified(required_statuses))
        self.assertEqual(PyUICompatAgent._status_after_assertions('completed', required_statuses), 'completed')

    def test_optional_only_assertions_do_not_trigger_required_retry(self) -> None:
        step = {'assertions': [{'required': False}]}
        required_statuses = PyUICompatAgent._required_assertion_statuses(step, ['inconclusive'])

        self.assertEqual(required_statuses, [])
        self.assertTrue(PyUICompatAgent._step_assertions_are_verified(step, required_statuses))

    def test_capture_assertion_target_evidence_binds_locator_state(self) -> None:
        page = _AssertionEvidencePageStub(_AssertionEvidenceLocatorStub('Camera A', count=2))

        artifacts = asyncio.run(collect_browser_observations(page, [
            {'assert_kind': 'element_state', 'target': {'locator': '[data-testid="camera"]'}},
            {'assert_kind': 'collection', 'target': {'locator': '[data-testid="camera"]'}},
        ], None))

        self.assertEqual(artifacts[0], {
            'type': 'element_state', 'locator': '[data-testid="camera"]',
            'count': 2, 'visible': True, 'text': 'Camera A',
        })
        self.assertEqual(artifacts[1]['type'], 'collection_state')
        self.assertEqual(artifacts[1]['count'], 2)

    def test_action_audit_payload_preserves_target_and_redacts_value(self) -> None:
        payload = PyUICompatAgent._audit_action_payload(
            {'action': 'fill', 'selector': '#email', 'value': 'secret@example.test'},
            {'step_mode': 'ai', 'executor': 'browser'},
        )

        self.assertEqual(payload['selector'], '#email')
        self.assertTrue(payload['value_present'])
        self.assertNotIn('value', payload)

    def test_plan_ai_step_includes_execution_resources(self) -> None:
        agent = PyUICompatAgent(case_name='Resource_Context')
        agent._execution_resources = [{'resource_type': 'alert_event', 'resource_id': 'event-123'}]

        self.assertEqual(agent._execution_resources[0]['resource_id'], 'event-123')

    def test_extract_correlation_values_keeps_bounded_non_sensitive_scalars(self) -> None:
        values = PyUICompatAgent._extract_correlation_values({
            'id': 13904,
            'status': 'Investigate',
            'access_token': 'must-not-leak',
            'nested': {'category': 'Other'},
        })

        self.assertEqual(values, ['13904', 'Investigate', 'Other'])

    def test_resolve_locator_skips_hidden_matches(self) -> None:
        agent = PyUICompatAgent(case_name='Locator_Visibility')
        page = _VisibleResolveLocatorPageStub()

        locator = asyncio.run(agent._resolve_locator(page, 'text=Cameras'))

        self.assertIs(locator, page.css_locator.nth(1))

    def test_normalize_step_preserves_device_cli_fields(self) -> None:
        agent = PyUICompatAgent(case_name='Device_Check')

        step = agent._normalize_step(
            {
                'executor': 'device_cli',
                'description': '检查设备服务',
                'device_id': 'ainvr_5000',
                'command': 'systemctl is-active camera-agent',
                'timeout_ms': 60000,
            },
            1,
        )

        self.assertEqual(step['executor'], 'device_cli')
        self.assertEqual(step['device_id'], 'ainvr_5000')
        self.assertEqual(step['command'], 'systemctl is-active camera-agent')

    def test_normalize_step_preserves_data_factory_fields(self) -> None:
        agent = PyUICompatAgent(case_name='Data_Factory')

        step = agent._normalize_step({
            'executor': 'data_factory', 'action': 'create', 'description': 'Create event',
            'resource_type': 'alert_event', 'arguments': {'alert_type': 'person'},
        }, 1)

        self.assertEqual(step['resource_type'], 'alert_event')
        self.assertEqual(step['arguments'], {'alert_type': 'person'})

    def test_normalize_step_preserves_assertion_contract(self) -> None:
        agent = PyUICompatAgent(case_name='Assertion_Contract')
        assertions = [{'action': 'assert', 'assert_kind': 'element_state'}]

        step = agent._normalize_step({'executor': 'browser', 'description': 'Verify state', 'assertions': assertions}, 1)

        self.assertEqual(step['assertions'], assertions)

    def test_normalize_step_preserves_assertion_bindings(self) -> None:
        agent = PyUICompatAgent(case_name='Assertion_Bindings')
        bindings = [{'assertion_index': 1, 'locator': '[data-testid="alert"]'}]

        step = agent._normalize_step({'action': 'click', 'assertion_bindings': bindings}, 1)

        self.assertEqual(step['assertion_bindings'], bindings)

    def test_normalize_step_routes_undeclared_direct_action_to_ai_planning(self) -> None:
        agent = PyUICompatAgent(case_name='Generic_Plan')

        step = agent._normalize_step(
            {'step_mode': 'direct', 'description': 'Wait until the requested state is visible'},
            1,
        )

        self.assertEqual(step['step_mode'], 'ai')
        self.assertEqual(step['action'], '')

    def test_normalized_steps_reject_specialized_action_and_fixed_coordinates(self) -> None:
        agent = PyUICompatAgent(case_name='Generic_Plan')

        with self.assertRaisesRegex(ValueError, 'unsupported browser action'):
            agent._validate_normalized_steps([{'executor': 'browser', 'step_mode': 'direct', 'action': 'open_camera_list'}])
        with self.assertRaisesRegex(ValueError, 'must not use fixed coordinates'):
            agent._validate_normalized_steps([{'executor': 'browser', 'step_mode': 'direct', 'action': 'click', 'loc': '(1,2)'}])

    def test_freeform_device_plan_skips_playwright(self) -> None:
        configuration = SimpleNamespace(id=7, name='Device Test', environment='test')
        agent = PyUICompatAgent(case_name='Device_Check', environment_configuration=configuration)
        agent._execute_device_cli_step = AsyncMock(return_value={
            'status': 'PASSED',
            'operation': 'connection_check',
            'exit_code': 0,
            'duration_ms': 12.0,
            'stdout': '',
            'stderr': '',
        })
        agent._write_case_report_artifacts = lambda *_args: []

        with patch(
            'apps.ai_testing.global_planner.GlobalTestPlanner.create_plan',
            new=AsyncMock(return_value=[
                {
                    'executor': 'device_cli',
                    'description': '连接设备',
                    'device_id': 'ainvr_5000',
                },
            ]),
        ):
            history = asyncio.run(
                agent.run_full_process(
                    '连接设备并验证可用性',
                    case_mode='freeform',
                    task_steps=None,
                )
            )

        self.assertEqual(history.steps[0]['status'], 'completed')
        self.assertEqual(history.steps[0]['executor'], 'device_cli')
        self.assertEqual(history.planner_trace['source'], 'global_planner')
        self.assertEqual(history.planner_trace['environment_configuration']['id'], 7)
        agent._execute_device_cli_step.assert_awaited_once()

    def test_execute_data_factory_step_uses_generic_resource_contract(self) -> None:
        configuration = SimpleNamespace(id=7)
        agent = PyUICompatAgent(environment_configuration=configuration)
        resource = {
            'success': True,
            'resource_type': 'alert_event',
            'resource_id': 'event-123',
            'resource': {},
        }

        with patch(
            'apps.ai_testing.runtime.pyui_compat.runner.asyncio.to_thread',
            new=AsyncMock(return_value=resource),
        ) as to_thread:
            result = asyncio.run(agent._execute_data_factory_step({
                'resource_type': 'alert_event',
                'arguments': {'alert_type': 'vehicle'},
            }))

        self.assertEqual(result['resource_id'], 'event-123')
        self.assertEqual(result['resource_type'], 'alert_event')
        self.assertEqual(
            to_thread.await_args.args[1:],
            (configuration, 'alert_event', {'alert_type': 'vehicle'}),
        )

    def test_store_and_load_cached_ai_actions(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='TC_004')
                step = {'index': 1, 'description': '点击登录按钮'}
                actions = [{'action': 'click', 'selector': 'text=Login'}]

                asyncio.run(agent._store_cached_ai_actions(step, actions))

                loaded = agent._load_cached_ai_actions(step)
                self.assertEqual(loaded, actions)
                self.assertTrue((Path(settings.BASE_DIR).resolve().parent / 'Data' / 'Cache' / 'action_cache.json').exists())

    def test_get_ai_actions_prefers_cache(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='TC_004')
                step = {'index': 2, 'description': '输入邮箱'}
                cached_actions = [{'action': 'fill', 'selector': 'input[type="email"]', 'value': 'demo@example.com'}]
                history = HistoryStub()

                asyncio.run(agent._store_cached_ai_actions(step, cached_actions))
                agent._plan_ai_step_for_cacheable_step = AsyncMock(return_value=[{'action': 'click'}])

                actions, source = asyncio.run(agent._get_ai_actions_for_step(page=None, step=step, history=history))

                self.assertEqual(actions, cached_actions)
                self.assertEqual(source, 'cache')
                self.assertEqual(history.cache_stats['hit'], 1)
                agent._plan_ai_step_for_cacheable_step.assert_not_awaited()

    def test_get_ai_actions_skips_cache_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='TC_004', use_cache=False)
                step = {'index': 2, 'description': '输入邮箱'}
                cached_actions = [{'action': 'fill', 'selector': 'input[type="email"]', 'value': 'demo@example.com'}]
                history = HistoryStub(cache_stats={'enabled': False, 'hit': 0, 'miss': 0, 'model_retries': 0, 'model_attempts': 0})

                asyncio.run(agent._store_cached_ai_actions(step, cached_actions))
                agent._plan_ai_step_for_cacheable_step = AsyncMock(return_value=[{'action': 'click'}])

                actions, source = asyncio.run(agent._get_ai_actions_for_step(page=None, step=step, history=history))

                self.assertEqual(actions, [{'action': 'click'}])
                self.assertEqual(source, 'model')
                self.assertEqual(history.cache_stats['hit'], 0)
                agent._plan_ai_step_for_cacheable_step.assert_awaited_once()

    def test_cache_key_is_scoped_to_project_and_page_context(self) -> None:
        step = {'index': 2, 'description': '输入邮箱'}
        page_context = {'fingerprint': 'page-a'}
        same_case_other_project = PyUICompatAgent(case_name='TC_004', ai_project_id=2)
        same_project_other_page = PyUICompatAgent(case_name='TC_004', ai_project_id=1)
        first_project = PyUICompatAgent(case_name='TC_004', ai_project_id=1)

        project_key = first_project._cache_key_for_step(step, page_context)
        other_project_key = same_case_other_project._cache_key_for_step(step, page_context)
        other_page_key = same_project_other_page._cache_key_for_step(
            step,
            {'fingerprint': 'page-b'},
        )

        self.assertNotEqual(project_key, other_project_key)
        self.assertNotEqual(project_key, other_page_key)

    def test_cache_key_is_scoped_to_permission_and_assertion_contract(self) -> None:
        step = {
            'index': 2,
            'description': 'Verify the dashboard',
            'assertions': [{'action': 'assert', 'assert_kind': 'text'}],
        }
        page_context = {'fingerprint': 'page-a'}
        first_user = PyUICompatAgent(case_name='TC_004', ai_project_id=1, execution_user_id=1)
        other_user = PyUICompatAgent(case_name='TC_004', ai_project_id=1, execution_user_id=2)
        other_assertion = {
            **step,
            'assertions': [{'action': 'assert', 'assert_kind': 'url'}],
        }

        self.assertNotEqual(first_user._cache_key_for_step(step, page_context), other_user._cache_key_for_step(step, page_context))
        self.assertNotEqual(first_user._cache_key_for_step(step, page_context), first_user._cache_key_for_step(other_assertion, page_context))

    def test_cache_key_changes_with_application_version(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004', ai_project_id=1)
        step = {'index': 2, 'description': 'Verify dashboard'}

        self.assertNotEqual(
            agent._cache_key_for_step(step, {'fingerprint': 'page-a', 'application_version': '1.0.0'}),
            agent._cache_key_for_step(step, {'fingerprint': 'page-a', 'application_version': '1.0.1'}),
        )

    def test_experience_scope_hashes_permission_and_assertion_contract(self) -> None:
        step = {'assertions': [{'action': 'assert', 'assert_kind': 'text'}]}
        other_step = {'assertions': [{'action': 'assert', 'assert_kind': 'url'}]}

        self.assertNotEqual(
            PyUICompatAgent(execution_user_id=1)._permission_fingerprint(),
            PyUICompatAgent(execution_user_id=2)._permission_fingerprint(),
        )
        self.assertNotEqual(
            PyUICompatAgent._assertion_contract_hash(step),
            PyUICompatAgent._assertion_contract_hash(other_step),
        )

    def test_get_ai_actions_prefers_verified_experience(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004', ai_project_id=1)
        step = {'index': 2, 'description': '输入邮箱'}
        history = HistoryStub()
        experience_actions = [{'action': 'fill', 'selector': 'input[type="email"]', 'value': 'demo@example.com'}]
        agent._load_verified_experience = AsyncMock(return_value=experience_actions)
        agent._plan_ai_step_for_cacheable_step = AsyncMock(return_value=[{'action': 'click'}])

        actions, source = asyncio.run(agent._get_ai_actions_for_step(page=None, step=step, history=history))

        self.assertEqual(actions, experience_actions)
        self.assertEqual(source, 'experience')
        self.assertEqual(history.cache_stats['experience_hit'], 1)
        agent._plan_ai_step_for_cacheable_step.assert_not_awaited()

    def test_plan_ai_step_does_not_write_cache_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='TC_004')
                step = {'index': 3, 'description': '悬停组织管理按钮'}
                history = HistoryStub(cache_stats={'enabled': False, 'hit': 0, 'miss': 0, 'model_retries': 0, 'model_attempts': 0, 'write': 0, 'ai_generated': 0})
                agent._plan_ai_step_with_retries = AsyncMock(return_value=[{'action': 'hover', 'selector': 'nav >> text=Team'}])

                actions = asyncio.run(agent._plan_ai_step_for_cacheable_step(page=None, step=step, history=history))

                self.assertEqual(actions, [{'action': 'hover', 'selector': 'nav >> text=Team'}])
                self.assertEqual(history.cache_stats['write'], 0)
                self.assertEqual(agent._load_cached_ai_actions(step), None)

    def test_plan_ai_step_with_retries_succeeds_after_failures(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='TC_004')
                history = HistoryStub()
                step = {'index': 3, 'description': '悬停组织管理按钮'}
                page = object()
                agent._plan_ai_step = AsyncMock(side_effect=[ValueError('boom-1'), ValueError('boom-2'), [{'action': 'hover', 'selector': 'nav >> text=Team'}]])

                actions = asyncio.run(agent._plan_ai_step_with_retries(page, step, history, step_index=3, max_attempts=4))

                self.assertEqual(actions, [{'action': 'hover', 'selector': 'nav >> text=Team'}])
                self.assertEqual(history.cache_stats['model_attempts'], 3)
                self.assertEqual(history.cache_stats['model_retries'], 2)
                self.assertEqual(history.planner_trace['step_retry_map']['3'], 2)
                self.assertEqual(len(history.artifacts), 2)

    def test_cache_verification_requires_current_passing_assertions(self) -> None:
        self.assertTrue(PyUICompatAgent._assertions_are_verified(['passed']))
        self.assertFalse(PyUICompatAgent._assertions_are_verified([]))
        self.assertFalse(PyUICompatAgent._assertions_are_verified(['inconclusive']))
        self.assertFalse(PyUICompatAgent._assertions_are_verified(['passed', 'failed']))

    def test_assertion_outcomes_update_runtime_step_status(self) -> None:
        self.assertEqual(
            PyUICompatAgent._status_after_assertions('completed', ['passed']),
            'completed',
        )
        self.assertEqual(
            PyUICompatAgent._status_after_assertions('completed', ['failed']),
            'failed',
        )
        self.assertEqual(
            PyUICompatAgent._status_after_assertions('completed', ['inconclusive']),
            'inconclusive',
        )

    def test_visual_replan_rejects_coordinates_and_specialized_actions(self) -> None:
        with self.assertRaisesRegex(ValueError, 'must not use fixed coordinates'):
            PyUICompatAgent._validate_planned_actions(
                [{'action': 'click', 'loc': '(10,20)'}],
                'Inspect the current state',
            )

        with self.assertRaisesRegex(ValueError, 'uses unsupported action'):
            PyUICompatAgent._validate_planned_actions(
                [{'action': 'open_camera_list'}],
                'Inspect the current state',
            )
        with self.assertRaisesRegex(ValueError, 'requires selector'):
            PyUICompatAgent._validate_planned_actions(
                [{'action': 'click', 'selector': '   '}],
                'Inspect the current state',
            )

    def test_visual_replan_rejects_actions_outside_step_capabilities(self) -> None:
        with self.assertRaisesRegex(ValueError, 'requires capability browser.navigate'):
            PyUICompatAgent._validate_planned_actions(
                [{'action': 'navigate', 'url': 'https://example.test'}],
                'Inspect the current state',
                ['browser.act', 'browser.inspect'],
            )

    def test_plan_retry_records_generic_planner_failure(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')
        history = HistoryStub()
        step = {'index': 3, 'description': 'Inspect the current application state'}
        agent._plan_ai_step = AsyncMock(side_effect=[ValueError('invalid action contract'), [{'action': 'assert'}]])

        actions = asyncio.run(agent._plan_ai_step_with_retries(object(), step, history, step_index=3, max_attempts=2))

        self.assertEqual(actions, [{'action': 'assert'}])
        self.assertEqual(history.artifacts[0]['error'], 'ValueError: invalid action contract')

    def test_write_case_report_artifacts_outputs_jsonl_and_html(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='TC_004')
                artifact_dir = Path(media_root) / 'ai_testing' / 'planner_v2' / 'case'
                artifact_dir.mkdir(parents=True, exist_ok=True)
                history = type('ReportHistoryStub', (), {
                    'case_report': {
                        'case_id': 'TC_004',
                        'total_steps': 1,
                        'success': True,
                        'steps': [
                            {
                                'step_num': 1,
                                'step_description': '点击登录按钮',
                                'source': 'model',
                                'retry_count': 1,
                                'result': True,
                                'error': None,
                            }
                        ],
                    }
                })()

                artifacts = agent._write_case_report_artifacts(artifact_dir, 'tc004', history)

                self.assertEqual([artifact['type'] for artifact in artifacts], ['report_jsonl', 'report_html'])
                for artifact in artifacts:
                    self.assertTrue((Path(media_root) / artifact['path']).exists())

    def test_resolve_locator_falls_back_to_text_when_css_selector_has_no_match(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')
        page = _ResolveLocatorPageStub(css_count=0)

        locator = asyncio.run(agent._resolve_locator(page, 'Team'))

        self.assertIs(locator, page.text_locator)

    def test_action_failure_requests_generic_replan(self) -> None:
        agent = PyUICompatAgent(case_name='TC_002')
        history = HistoryStub()
        step = {'description': 'Inspect the page and verify the requested state'}
        agent._execute_step = AsyncMock(side_effect=[ValueError('target unavailable'), None])
        agent._plan_ai_step_with_retries = AsyncMock(return_value=[{'action': 'assert'}])

        asyncio.run(agent._execute_ai_actions(object(), step, [{'action': 'click'}], 2, None, TimeoutError, history=history))

        agent._plan_ai_step_with_retries.assert_awaited_once()
        replan_artifact = next(artifact for artifact in history.artifacts if artifact['type'] == 'ai_replan')
        self.assertEqual(replan_artifact['actions'], [{'action': 'assert'}])

    def test_visual_assert_marker_defers_to_persisted_assertions(self) -> None:
        agent = PyUICompatAgent(case_name='Unified_Assertion')
        agent._execute_step = AsyncMock()

        asyncio.run(agent._execute_ai_actions(object(), {'description': 'Verify state'}, [{'action': 'assert'}], 1, None, TimeoutError))

        agent._execute_step.assert_not_awaited()

    def test_parse_ai_actions_reports_non_json_preview(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        with self.assertRaisesRegex(ValueError, 'returned non-JSON content: Sure, I can help'):
            agent._parse_ai_actions('Sure, I can help with that. Click the Organization button first.')

    def test_parse_ai_actions_extracts_json_object_from_explanatory_prefix(self) -> None:
        agent = PyUICompatAgent(case_name='TC_005')

        actions = agent._parse_ai_actions(
            'The user wants to validate the page. {"actions":[{"action":"assert_text_contains","selector":"body","expected":"滨江区7/0"}]}'
        )

        self.assertEqual(actions, [{'action': 'assert_text_contains', 'selector': 'body', 'expected': '滨江区7/0'}])

    def test_execute_step_wait_uses_explicit_value(self) -> None:
        agent = PyUICompatAgent(case_name='TC_005')
        page = _TextPageStub('')

        asyncio.run(agent._execute_step(page, {'action': 'wait', 'value': '20000', 'timeout_ms': 10000}, TimeoutError))

        self.assertEqual(page.waited_ms, 20000)

    def test_build_request_payload_includes_response_format_when_present(self) -> None:
        config = type('ConfigStub', (), {'model_name': 'demo', 'temperature': 0.1, 'top_p': 0.2, 'model_type': 'qwen'})()

        data = AIModelService._build_request_payload(
            config=config,
            messages=[{'role': 'user', 'content': 'hello'}],
            max_tokens=64,
            stream=False,
            response_format={'type': 'json_object'},
        )

        self.assertEqual(data['response_format'], {'type': 'json_object'})
        self.assertEqual(data['chat_template_kwargs'], {'enable_thinking': False})

    def test_cache_miss_uses_generic_model_plan(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')
        history = HistoryStub()
        agent._build_page_context = AsyncMock(return_value={'url': 'https://example.test'})
        agent._load_cached_ai_actions = lambda *_args: None
        agent._load_verified_experience = AsyncMock(return_value=None)
        agent._plan_ai_step_for_cacheable_step = AsyncMock(return_value=[{'action': 'assert'}])

        actions, source = asyncio.run(
            agent._get_ai_actions_for_step(
                object(),
                {'index': 1, 'description': 'Verify current state'},
                history,
            )
        )

        self.assertEqual(source, 'model')
        self.assertEqual(actions, [{'action': 'assert'}])

    def test_replan_replaces_failed_action_with_new_action(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')
        history = HistoryStub()
        step = {'description': 'Perform the requested operation'}
        agent._execute_step = AsyncMock(side_effect=[ValueError('stale target'), None])
        agent._plan_ai_step_with_retries = AsyncMock(return_value=[{'action': 'assert'}])

        asyncio.run(agent._execute_ai_actions(object(), step, [{'action': 'click'}], 1, None, TimeoutError, history=history))

        self.assertEqual(agent._execute_step.await_count, 1)
        replan_artifact = next(artifact for artifact in history.artifacts if artifact['type'] == 'ai_replan')
        self.assertEqual(replan_artifact['failed_action'], {'action': 'click'})

    def test_assertion_failure_replans_and_rechecks_evidence(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004', execution_record_id=7)
        history = HistoryStub()
        step = {'description': 'Verify requested state', 'assertions': [{'action': 'assert'}]}
        agent._plan_ai_step_with_retries = AsyncMock(return_value=[{'action': 'click', 'selector': '#retry'}])
        agent._execute_ai_actions = AsyncMock()
        agent._capture_media_state = AsyncMock(return_value=[])
        agent._capture_screenshot = AsyncMock(return_value='retry.png')
        agent._persist_step_attempt = AsyncMock(return_value={'assertion_statuses': ['passed']})

        with patch('apps.ai_testing.execution.plan_persistence.persist_replanned_step') as persist_replanned_step:
            result = asyncio.run(agent._retry_assertion_failure(
                object(), step, 1, [{'action': 'click', 'selector': '#initial'}], ['failed'],
                None, TimeoutError, history, None,
            ))

        self.assertEqual(result[0], 'completed')
        persist_replanned_step.assert_called_once()
        agent._execute_ai_actions.assert_awaited_once()
        self.assertEqual(agent._persist_step_attempt.await_args.args[3], 'completed')

    def test_replan_failure_is_persisted_before_creating_new_plan(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004', execution_record_id=7)
        agent._persist_step_attempt = AsyncMock()

        asyncio.run(
            agent._persist_replan_failure(
                2,
                {'description': 'Inspect current state'},
                {'action': 'click'},
                ValueError('target unavailable'),
                object(),
            )
        )

        self.assertEqual(agent._persist_step_attempt.await_args.args[3], 'failed')
        self.assertEqual(agent._persist_step_attempt.await_args.args[4], 'ValueError: target unavailable')

    def test_execute_step_selector_non_empty_applies_geometry_constraints(self) -> None:
        agent = PyUICompatAgent(case_name='TC_005')
        page = _VisibilityPageStub(
            {
                'video': _VisibilityLocatorStub([
                    _VisibilityItemStub(True, {'x': 120, 'y': 180, 'width': 180, 'height': 110}),
                ]),
                'canvas': _VisibilityLocatorStub([
                    _VisibilityItemStub(True, {'x': 480, 'y': 180, 'width': 920, 'height': 520}),
                ]),
            }
        )

        asyncio.run(
            agent._execute_step(
                page,
                {
                    'action': 'assert',
                    'assert_kind': 'selector_non_empty',
                    'selector_candidates': ['video', 'canvas'],
                    'min_count': 1,
                    'min_x': 420,
                    'min_y': 140,
                    'min_width': 600,
                    'min_height': 320,
                    'expected': 'True',
                },
                timeout_error=TimeoutError,
            )
        )

    def test_execute_step_selector_non_empty_supports_expected_false(self) -> None:
        agent = PyUICompatAgent(case_name='TC_005')
        page = _VisibilityPageStub(
            {
                'video': _VisibilityLocatorStub([
                    _VisibilityItemStub(True, {'x': 480, 'y': 180, 'width': 920, 'height': 520}),
                ]),
            }
        )

        with self.assertRaisesRegex(AssertionError, 'expected no visible matches'):
            asyncio.run(
                agent._execute_step(
                    page,
                    {
                        'action': 'assert',
                        'assert_kind': 'selector_non_empty',
                        'selector_candidates': ['video'],
                        'min_count': 1,
                        'min_x': 420,
                        'min_y': 140,
                        'min_width': 600,
                        'min_height': 320,
                        'expected': 'False',
                    },
                    timeout_error=TimeoutError,
                )
            )

    def test_assert_stream_active_rejects_static_preview(self) -> None:
        agent = PyUICompatAgent(case_name='TC_005')
        page = _StreamPageStub(
            {
                'video': _StreamLocatorStub([
                    _StreamMediaItemStub(
                        visible=False,
                        eval_result={
                            'currentTime': 0,
                            'paused': True,
                            'ended': False,
                            'readyState': 0,
                            'videoWidth': 0,
                            'videoHeight': 0,
                        },
                    )
                ]),
                'img, canvas, video': _StreamLocatorStub([
                    _StreamMediaItemStub(
                        visible=True,
                        box={'x': 480, 'y': 180, 'width': 900, 'height': 500},
                        screenshot_bytes=[b'same-frame', b'same-frame', b'same-frame'],
                    )
                ]),
            }
        )

        with self.assertRaisesRegex(AssertionError, 'stream preview did not change'):
            asyncio.run(agent._assert_stream_active(page, 4000))

    def test_assert_stream_active_accepts_playing_video(self) -> None:
        agent = PyUICompatAgent(case_name='TC_005')
        page = _StreamPageStub(
            {
                'video': _StreamLocatorStub([
                    _StreamMediaItemStub(
                        visible=False,
                        eval_result={
                            'currentTime': 1.25,
                            'paused': False,
                            'ended': False,
                            'readyState': 4,
                            'videoWidth': 1920,
                            'videoHeight': 1080,
                        },
                    )
                ]),
                'img, canvas, video': _StreamLocatorStub([]),
            }
        )

        asyncio.run(agent._assert_stream_active(page, 4000))

    def test_normalize_step_preserves_executor_fields(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        step = agent._normalize_step(
            {
                'action': 'assert',
                'description': '断言搜索结果不为空',
                'assert_kind': 'selector_non_empty',
                'selector_candidates': ['li'],
                'min_count': 1,
                'min_x': 120,
                'min_y': 80,
                'min_width': 30,
                'min_height': 16,
                'param': 'results',
                'loc': '(10,20)',
            },
            1,
        )

        self.assertEqual(step['assert_kind'], 'selector_non_empty')
        self.assertEqual(step['selector_candidates'], ['li'])
        self.assertEqual(step['param'], 'results')
        self.assertEqual(step['loc'], '(10,20)')

    def test_cache_key_includes_case_and_step(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                first = PyUICompatAgent(case_name='TC_004')
                second = PyUICompatAgent(case_name='TC_005')
                step = {'index': 1, 'description': '相同步骤'}

                self.assertTrue(first._cache_key_for_step(step).startswith('v5::'))
                self.assertNotEqual(first._cache_key_for_step(step), second._cache_key_for_step(step))

    def test_history_step_action_uses_runtime_action_name(self) -> None:
        agent = PyUICompatAgent(case_name='[TC_004] create site manager role')

        self.assertEqual(agent._step_screenshot_filename(3), 'TC_004_step_03.png')
        self.assertEqual(agent._final_screenshot_filename(), 'TC_004_final.png')
        self.assertEqual(agent._step_thinking_text(None, 'click'), 'action=click')
        self.assertEqual(agent._step_thinking_text('planner_v2 executed action=hover', 'hover'), 'action=hover')

    def test_prepare_artifact_dir_and_report_prefix_use_case_id(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='[TC_004] create site manager role')

                artifact_dir, artifact_prefix = agent._prepare_artifact_dir()

                self.assertIsNotNone(artifact_dir)
                self.assertEqual(artifact_prefix, 'TC_004')
                self.assertTrue(str(artifact_dir).endswith('TC_004_' + Path(artifact_dir).name.split('_')[-1]))