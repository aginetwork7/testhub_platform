import asyncio
from datetime import timedelta
import json
from dataclasses import dataclass, field
import inspect
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from apps.ai_testing.execution.browser_observers import collect_browser_observations
from apps.ai_testing.execution.mcp_tools import (
    BrowserMCPToolAdapter,
    MCPInProcessClient,
    MCPInProcessTransport,
    MCPJsonRpcDispatcher,
)
from apps.ai_testing.execution.page_observation import capture_accessibility_snapshot
from apps.ai_testing.runtime.pyui_compat import PyUICompatAgent
from apps.core.llm import OpenAICompatibleClient


@dataclass
class HistoryStub:
    cache_stats: dict = field(default_factory=lambda: {'hit': 0, 'miss': 1, 'model_retries': 0, 'model_attempts': 0})
    planner_trace: dict = field(default_factory=lambda: {'step_retry_map': {}})
    artifacts: list = field(default_factory=list)


class BrowserMCPToolAdapterTests(SimpleTestCase):
    def test_list_tools_scopes_actions_to_capabilities(self) -> None:
        adapter = BrowserMCPToolAdapter(['browser.inspect'], AsyncMock())

        tools = adapter.list_tools()

        action_schema = tools[0]['inputSchema']['properties']['instruction']['properties']['action']
        self.assertEqual(tools[0]['name'], 'browser.act')
        self.assertEqual(action_schema['enum'], ['assert'])

    def test_call_tool_routes_validated_instruction_to_handler(self) -> None:
        handler = AsyncMock(return_value={'clicked': True})
        adapter = BrowserMCPToolAdapter(['browser.act'], handler)

        result = asyncio.run(adapter.call_tool(
            'browser.act',
            {'instruction': {'action': 'click', 'selector': '#submit'}},
        ))

        handler.assert_awaited_once_with({'action': 'click', 'selector': '#submit'})
        self.assertEqual(result['structuredContent'], {'clicked': True})
        self.assertFalse(result['isError'])

    def test_call_tool_rejects_action_outside_capabilities(self) -> None:
        adapter = BrowserMCPToolAdapter(['browser.inspect'], AsyncMock())

        with self.assertRaises(ValueError):
            asyncio.run(adapter.call_tool(
                'browser.act',
                {'instruction': {'action': 'click', 'selector': '#submit'}},
            ))

    def test_call_tool_captures_observation_without_arguments(self) -> None:
        handler = AsyncMock(return_value={'url': 'https://example.test', 'blocking_state': {'is_blocked': False}})
        adapter = BrowserMCPToolAdapter([], observation_handler=handler)

        tools = adapter.list_tools()
        result = asyncio.run(adapter.call_tool('browser.observe', {}))

        self.assertEqual([tool['name'] for tool in tools], ['browser.observe'])
        handler.assert_awaited_once_with()
        self.assertEqual(result['structuredContent']['url'], 'https://example.test')

    def test_resolves_capabilities_from_current_session_step(self) -> None:
        current_capabilities = ['browser.inspect']
        adapter = BrowserMCPToolAdapter(lambda: current_capabilities, AsyncMock())

        inspect_actions = adapter.list_tools()[0]['inputSchema']['properties']['instruction']['properties']['action']['enum']
        current_capabilities = ['browser.act']
        act_actions = adapter.list_tools()[0]['inputSchema']['properties']['instruction']['properties']['action']['enum']

        self.assertEqual(inspect_actions, ['assert'])
        self.assertIn('click', act_actions)


class MCPJsonRpcDispatcherTests(SimpleTestCase):
    def test_dispatches_initialize_and_tool_requests(self) -> None:
        handler = AsyncMock(return_value={'url': 'https://example.test'})
        dispatcher = MCPJsonRpcDispatcher(
            BrowserMCPToolAdapter([], observation_handler=handler),
        )

        initialize_result = asyncio.run(dispatcher.dispatch({
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {'protocolVersion': '2025-06-18'},
        }))
        asyncio.run(dispatcher.dispatch({
            'jsonrpc': '2.0',
            'method': 'notifications/initialized',
        }))
        list_result = asyncio.run(dispatcher.dispatch({
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/list',
        }))
        call_result = asyncio.run(dispatcher.dispatch({
            'jsonrpc': '2.0',
            'id': 3,
            'method': 'tools/call',
            'params': {'name': 'browser.observe', 'arguments': {}},
        }))

        self.assertEqual(initialize_result['result']['protocolVersion'], '2025-06-18')
        self.assertEqual(list_result['result']['tools'][0]['name'], 'browser.observe')
        self.assertEqual(call_result['result']['structuredContent']['url'], 'https://example.test')
        handler.assert_awaited_once_with()

    def test_returns_json_rpc_errors_for_invalid_requests(self) -> None:
        dispatcher = MCPJsonRpcDispatcher(BrowserMCPToolAdapter([]))

        invalid_request = asyncio.run(dispatcher.dispatch({'jsonrpc': '1.0', 'id': 1, 'method': 'tools/list'}))
        unknown_method = asyncio.run(dispatcher.dispatch({'jsonrpc': '2.0', 'id': 2, 'method': 'missing'}))

        self.assertEqual(invalid_request['error']['code'], -32600)
        self.assertEqual(unknown_method['error']['code'], -32601)

    def test_rejects_tool_requests_before_initialization(self) -> None:
        dispatcher = MCPJsonRpcDispatcher(BrowserMCPToolAdapter([]))

        response = asyncio.run(dispatcher.dispatch({
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'tools/list',
        }))

        self.assertEqual(response['error']['code'], -32002)

    def test_in_process_client_initializes_before_calling_tool(self) -> None:
        handler = AsyncMock(return_value={'url': 'https://example.test'})
        client = MCPInProcessClient(MCPInProcessTransport(MCPJsonRpcDispatcher(
            BrowserMCPToolAdapter([], observation_handler=handler),
        )))

        result = asyncio.run(client.call_tool('browser.observe', {}))

        self.assertEqual(result['structuredContent']['url'], 'https://example.test')
        handler.assert_awaited_once_with()


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


class _RoleLocatorPageStub:
    def __init__(self, visibility: list[bool]) -> None:
        self.locator_result = _LocatorVisibilityStub(visibility)
        self.call = None

    def get_by_role(self, role: str, name: str, exact: bool):
        self.call = (role, name, exact)
        return self.locator_result


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


class _DownloadWaitPageStub:
    def __init__(self, agent: PyUICompatAgent) -> None:
        self._agent = agent
        self.wait_count = 0

    async def wait_for_timeout(self, _timeout: int) -> None:
        self.wait_count += 1
        self._agent._recent_download_events.append({'status': 'completed', 'filename': 'new.zip'})


class _CollectionWaitPageStub:
    def __init__(self) -> None:
        self.load_state_call: tuple[str, int] | None = None
        self.waited_ms: int | None = None

    async def wait_for_load_state(self, state: str, timeout: int) -> None:
        self.load_state_call = (state, timeout)
        raise TimeoutError('network did not become idle')

    async def wait_for_timeout(self, timeout: int) -> None:
        self.waited_ms = timeout


class _PlaybackWaitPageStub:
    def __init__(self) -> None:
        self.waited_ms: list[int] = []

    async def wait_for_timeout(self, timeout: int) -> None:
        self.waited_ms.append(timeout)


class _NoHoverLocatorStub:
    async def evaluate_all(self, _script):
        return [{
            'selector': '#download',
            'name': '',
            'described_by': 'download-tooltip',
        }]

    async def hover(self, timeout: int) -> None:
        raise AssertionError(f'unexpected hover with timeout={timeout}')


class _ExistingTooltipPageStub:
    async def evaluate(self, _script, *_args):
        return 'Download'

    def locator(self, _selector: str) -> _NoHoverLocatorStub:
        return _NoHoverLocatorStub()


class _AccessibilitySessionStub:
    def __init__(self) -> None:
        self.detached = False

    async def send(self, method: str) -> dict:
        if method == 'Page.getFrameTree':
            return {'frameTree': {'frame': {'loaderId': 'page-v1'}}}
        return {'nodes': [
            {
                'nodeId': 'root',
                'role': {'value': 'RootWebArea'},
                'name': {'value': 'Dashboard'},
                'childIds': ['button-ax'],
            },
            {
                'nodeId': 'ignored',
                'ignored': True,
                'role': {'value': 'generic'},
            },
            {
                'nodeId': 'button-ax',
                'backendDOMNodeId': 42,
                'role': {'value': 'button'},
                'name': {'value': 'Settings'},
                'description': {'value': 'Open application settings'},
                'properties': [
                    {'name': 'expanded', 'value': {'value': False}},
                    {'name': 'disabled', 'value': {'value': False}},
                ],
            },
        ]}

    async def detach(self) -> None:
        self.detached = True


class _AccessibilityPageStub:
    def __init__(self) -> None:
        self.session = _AccessibilitySessionStub()
        self.context = self

    async def new_cdp_session(self, _page) -> _AccessibilitySessionStub:
        return self.session


class _AccessibilityUnsupportedPageStub:
    context = None


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
    def test_media_before_state_uses_authoritative_native_observer(self) -> None:
        agent = PyUICompatAgent(case_name='Native_Media_State')
        page = object()
        state = [{'currentTime': 4, 'playedEnd': 4}]

        with patch(
            'apps.ai_testing.execution.browser_observers.NATIVE_MEDIA_OBSERVER.capture_state',
            new=AsyncMock(return_value=state),
        ) as capture_state:
            result = asyncio.run(agent._capture_media_state(page))

        self.assertEqual(result, state)
        capture_state.assert_awaited_once_with(page)

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
        self.assertIn("element._vei && typeof element._vei === 'object'", source)
        self.assertIn("child._vei && typeof child._vei === 'object'", source)
        self.assertIn('const compactIconControl = directSvg && rect.width >= 16', source)
        self.assertIn("style.cursor === 'pointer' || compactIconControl", source)
        self.assertIn("startsWith('__reactProps')", source)
        self.assertIn('current.parentElement === document.body', source)
        self.assertIn("['fixed', 'sticky'].includes(style.position) || zIndex > 0", source)
        self.assertIn("'[aria-label], [title], [alt], [data-icon], [data-lucide], svg title, svg, use'", source)
        self.assertIn("semanticChild.getAttribute('data-icon')", source)
        self.assertIn("semanticChild.getAttribute('data-lucide')", source)
        self.assertIn("element.querySelector('svg use, use')", source)
        self.assertIn("semanticUse.getAttribute('href')", source)
        self.assertIn('|| semanticReference', source)
        self.assertIn("split(/\\\\s+/).find(token => /icon$/i.test(token))", source)
        self.assertIn('|| semanticClass', source)
        self.assertNotIn("|| semanticChild.getAttribute('class')", source)
        self.assertNotIn('use[xlink', source)
        self.assertIn('new URL(href, document.baseURI).href', source)
        self.assertIn('native_control: nativeControl', source)
        self.assertIn('group_selector: groupSelector', source)
        self.assertIn('grouped.length >= 1 && parentSelector', source)
        self.assertIn('classSiblings.length >= 1 ? classSiblings', source)
        self.assertIn('has_visual_content: hasRenderedVisual', source)
        self.assertIn('blockingLayerRank || namedRank || nativeRank || topLayerRank', source)
        self.assertIn('left.depth - right.depth', source)
        self.assertIn('}).slice(0, 300)', source)
        self.assertIn("element.getAttribute('aria-describedby')", source)
        self.assertIn('document.getElementById(tooltipId)?.innerText', source)
        self.assertIn("element.closest('[aria-disabled=\"true\"], [disabled], [inert]')", source)
        self.assertIn("style.pointerEvents !== 'none'", source)

    def test_observable_discovery_exposes_structural_collection_groups(self) -> None:
        source = inspect.getsource(PyUICompatAgent._build_observable_elements)

        self.assertIn('group_selector: groupSelector', source)
        self.assertIn('group_size: grouped.length', source)
        self.assertIn('group_ordinal: grouped.indexOf(element)', source)
        self.assertIn('sameTagSiblings', source)

    def test_actionable_discovery_propagates_normalized_blocking_state(self) -> None:
        import inspect

        discovery_source = inspect.getsource(PyUICompatAgent._build_actionable_controls)
        observation_source = inspect.getsource(PyUICompatAgent._collect_planner_observation)
        planning_source = inspect.getsource(PyUICompatAgent._plan_ai_step)

        from apps.ai_testing.runtime.pyui_compat.runner import PLANNER_CONTROL_KEYS

        self.assertIn('blocking_layer_id: blockingLayerId', discovery_source)
        self.assertIn('blocking_layer_id', PLANNER_CONTROL_KEYS)
        self.assertIn('self._last_actionable_controls = self._planner_control_baseline(actionable_controls)', observation_source)
        self.assertIn("'blocking_state': build_blocking_state(actionable_controls)", observation_source)
        self.assertIn("mcp_client.call_tool('browser.observe', {})", planning_source)

    def test_actionable_discovery_reads_existing_tooltip_without_hover(self) -> None:
        controls = asyncio.run(
            PyUICompatAgent()._build_actionable_controls(_ExistingTooltipPageStub())
        )

        self.assertEqual(controls, [{'selector': '#download', 'name': 'Download'}])

    def test_runtime_observers_register_download_listener(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._attach_runtime_observers)

        self.assertIn("page.on('download', on_download)", source)
        self.assertIn("'status': 'failed' if failure else 'completed'", source)

    def test_download_observation_uses_assertion_timeout(self) -> None:
        agent = PyUICompatAgent()
        agent._recent_download_events = [{'status': 'completed', 'filename': 'old.zip'}]
        agent._download_event_baseline = len(agent._recent_download_events)
        page = _DownloadWaitPageStub(agent)

        asyncio.run(agent._wait_for_assertion_observation(page, {
            'assertions': [{'assert_kind': 'download_task', 'timeout_ms': 1000}],
        }))

        self.assertEqual(page.wait_count, 1)
        self.assertEqual(
            agent._current_step_download_events(),
            [{'status': 'completed', 'filename': 'new.zip'}],
        )

    def test_collection_observation_waits_for_bounded_network_idle(self) -> None:
        page = _CollectionWaitPageStub()

        asyncio.run(PyUICompatAgent()._wait_for_assertion_observation(page, {
            'timeout_ms': 12000,
            'assertions': [{'assert_kind': 'collection', 'required': True}],
        }))

        self.assertEqual(page.load_state_call, ('networkidle', 10000))
        self.assertIsNone(page.waited_ms)

    def test_playback_observation_waits_for_ready_media_progress(self) -> None:
        page = _PlaybackWaitPageStub()
        media_states = [
            [],
            [{'paused': True, 'readyState': 0, 'currentTime': 0, 'currentSrc': ''}],
            [{'paused': False, 'readyState': 3, 'currentTime': 4, 'currentSrc': 'stream.m3u8'}],
            [{'paused': False, 'readyState': 4, 'currentTime': 5.1, 'currentSrc': 'stream.m3u8'}],
        ]

        with patch(
            'apps.ai_testing.execution.browser_observers.NATIVE_MEDIA_OBSERVER.capture_state',
            new=AsyncMock(side_effect=media_states),
        ) as capture_state:
            asyncio.run(PyUICompatAgent()._wait_for_assertion_observation(page, {
                'timeout_ms': 10000,
                'assertions': [{
                    'assert_kind': 'playback',
                    'expected': {'minimum_advanced_seconds': 1},
                    'required': True,
                }],
            }))

        self.assertEqual(capture_state.await_count, 4)
        self.assertEqual(page.waited_ms, [500, 500, 500])

    def test_stream_observation_waits_for_canvas_frames_to_change(self) -> None:
        page = _PlaybackWaitPageStub()
        agent = PyUICompatAgent()
        blank = {'index': 0, 'content_hash': 'blank', 'visual_signal': False}
        picture_a = {'index': 0, 'content_hash': 'aaa', 'visual_signal': True}
        picture_b = {'index': 0, 'content_hash': 'bbb', 'visual_signal': True}

        with patch(
            'apps.ai_testing.execution.browser_observers.NATIVE_MEDIA_OBSERVER.capture_state',
            new=AsyncMock(return_value=[]),
        ), patch(
            'apps.ai_testing.execution.browser_observers.capture_canvas_frames',
            new=AsyncMock(side_effect=[[blank], [picture_a], [picture_b]]),
        ) as capture_frames:
            asyncio.run(agent._wait_for_assertion_observation(page, {
                'timeout_ms': 5000,
                'assertions': [{
                    'assert_kind': 'stream_state',
                    'expected': {'minimum_advanced_seconds': 2},
                    'required': True,
                }],
            }))

        # Frames are probed every other poll; the blank connecting canvas never becomes the baseline, the
        # first picture does, and the wait ends as soon as a later picture differs from it.
        self.assertEqual(capture_frames.await_count, 3)
        self.assertEqual(page.waited_ms, [500, 500, 500, 500])
        self.assertEqual(agent._observed_canvas_baseline, [picture_a])

    def test_stream_observation_gives_up_after_the_stream_start_budget(self) -> None:
        page = _PlaybackWaitPageStub()
        agent = PyUICompatAgent()
        blank = {'index': 0, 'content_hash': 'blank', 'visual_signal': False}

        with patch('apps.ai_testing.runtime.pyui_compat.runner.STREAM_START_WAIT_MS', 300), patch(
            'apps.ai_testing.execution.browser_observers.NATIVE_MEDIA_OBSERVER.capture_state',
            new=AsyncMock(return_value=[]),
        ), patch(
            'apps.ai_testing.execution.browser_observers.capture_canvas_frames',
            new=AsyncMock(return_value=[blank]),
        ):
            asyncio.run(agent._wait_for_assertion_observation(page, {
                'timeout_ms': 100,
                'assertions': [{'assert_kind': 'stream_state', 'expected': {'minimum_advanced_seconds': 2}, 'required': True}],
            }))

        self.assertTrue(page.waited_ms)
        self.assertEqual(agent._observed_canvas_baseline, [blank])

    def test_canvas_baseline_helpers_prefer_the_first_picture(self) -> None:
        blank = {'index': 0, 'content_hash': 'blank', 'visual_signal': False}
        picture_a = {'index': 0, 'content_hash': 'aaa', 'visual_signal': True}
        picture_b = {'index': 0, 'content_hash': 'bbb', 'visual_signal': True}
        other = {'index': 1, 'content_hash': 'other', 'visual_signal': True}

        self.assertFalse(PyUICompatAgent._canvas_frames_changed([blank], [picture_a]))
        self.assertTrue(PyUICompatAgent._canvas_frames_changed([picture_a], [picture_b]))
        self.assertFalse(PyUICompatAgent._canvas_frames_changed([picture_a], [picture_a, other]))
        self.assertEqual(PyUICompatAgent._first_picture_canvas_frames([blank], [picture_a]), [picture_a])
        self.assertEqual(PyUICompatAgent._first_picture_canvas_frames([picture_a], [picture_b]), [picture_a])
        # Pre-action frames win unless the canvas was blank or absent before the action.
        merged = PyUICompatAgent._merged_canvas_baseline([blank, other], [picture_a, {'index': 1, 'content_hash': 'later', 'visual_signal': True}])
        self.assertEqual(sorted(frame['content_hash'] for frame in merged), ['aaa', 'other'])
        self.assertEqual(PyUICompatAgent._merged_canvas_baseline([], [picture_a]), [picture_a])
        self.assertEqual(PyUICompatAgent._merged_canvas_baseline([picture_a], None), [picture_a])
        source = inspect.getsource(PyUICompatAgent._persist_step_attempt)
        self.assertIn('_merged_canvas_baseline(canvas_frames_before, self._observed_canvas_baseline)', source)

    def test_non_collection_observation_keeps_fast_wait(self) -> None:
        page = _CollectionWaitPageStub()

        asyncio.run(PyUICompatAgent()._wait_for_assertion_observation(page, {
            'assertions': [{'assert_kind': 'element_state', 'required': True}],
        }))

        self.assertIsNone(page.load_state_call)
        self.assertEqual(page.waited_ms, 300)

    def test_observable_discovery_builds_complete_body_path(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._build_observable_elements)

        self.assertIn('current.parentElement === document.body', source)

    def test_accessibility_snapshot_preserves_computed_semantics_and_page_version(self) -> None:
        page = _AccessibilityPageStub()

        snapshot = asyncio.run(capture_accessibility_snapshot(page))

        self.assertEqual(snapshot['page_version'], 'page-v1')
        self.assertEqual(len(snapshot['snapshot_id']), 64)
        self.assertEqual(snapshot['nodes'], [
            {
                'node_id': 'ax:root',
                'backend_dom_node_id': None,
                'role': 'RootWebArea',
                'name': 'Dashboard',
                'description': '',
                'value': '',
                'states': {},
                'child_ids': ['ax:button-ax'],
            },
            {
                'node_id': 'ax:button-ax',
                'backend_dom_node_id': 42,
                'role': 'button',
                'name': 'Settings',
                'description': 'Open application settings',
                'value': '',
                'states': {'expanded': False, 'disabled': False},
                'child_ids': [],
            },
        ])
        self.assertTrue(page.session.detached)

    def test_accessibility_snapshot_fails_closed_when_cdp_is_unavailable(self) -> None:
        snapshot = asyncio.run(capture_accessibility_snapshot(_AccessibilityUnsupportedPageStub()))

        self.assertEqual(snapshot, {'snapshot_id': '', 'page_version': '', 'nodes': []})

    def test_runtime_initializes_sanitized_planner_control_snapshot(self) -> None:
        agent = PyUICompatAgent(case_name='Planner_Control_Evidence')

        self.assertEqual(agent._last_actionable_controls, [])
        self.assertEqual(
            agent._last_accessibility_snapshot,
            {'snapshot_id': '', 'page_version': '', 'nodes': []},
        )

    def test_rebinding_replaces_stale_locator_without_nesting_intent(self) -> None:
        step = {'assertions': [{
            'target': {'locator': '#stale', 'intent': {'intent': 'status menu'}, 'text': 'Investigate'},
        }]}

        rebound = PyUICompatAgent._bind_step_assertions(
            step,
            [{'assertion_index': 1, 'locator': '#current'}],
        )

        self.assertEqual(rebound['assertions'][0]['target'], {
            'locator': '#current',
            'intent': 'status menu',
            'text': 'Investigate',
        })

    def test_assertion_retry_clears_locator_that_vanished_from_dom(self) -> None:
        agent = PyUICompatAgent(case_name='Stale_Binding', execution_record_id=7)
        step = {'assertions': [{
            'assert_kind': 'element_state',
            'operator': 'exists',
            'target': {
                'locator': '#stale',
                'intent': 'camera thumbnail',
                'text': 'Camera thumbnail preview',
                'visual_content': 'image',
            },
        }]}
        page = SimpleNamespace(locator=Mock(return_value=SimpleNamespace(count=AsyncMock(return_value=0))))

        with patch('apps.ai_testing.execution.plan_persistence.persist_unbound_step') as persist_unbound_step:
            asyncio.run(agent._clear_vanished_assertion_bindings(page, step, 1))

        self.assertEqual(step['assertions'][0]['target'], {
            'intent': 'camera thumbnail',
            'text': 'Camera thumbnail preview',
            'visual_content': 'image',
        })
        persist_unbound_step.assert_called_once_with(7, 1, [1])

    def test_assertion_shortfall_describes_only_unverified_contracts(self) -> None:
        step = {'assertions': [
            {'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'intent': 'camera thumbnail'}},
            {'assert_kind': 'field_value', 'operator': 'equals', 'expected': {'value': 'ai@test.com'}, 'target': {'intent': 'email input'}},
        ]}
        detail = PyUICompatAgent._describe_assertion_shortfall(step, ['passed', 'inconclusive'])

        self.assertNotIn('element_state', detail)
        self.assertIn('field_value', detail)
        self.assertIn('ai@test.com', detail)
        self.assertIn('inconclusive', detail)

        self.assertEqual(PyUICompatAgent._describe_assertion_shortfall({'assertions': []}, []), '')
        self.assertEqual(PyUICompatAgent._describe_assertion_shortfall(step, ['passed', 'passed']), '')

    def test_image_assertion_waits_for_rendered_visual_content_before_capture(self) -> None:
        page = SimpleNamespace(
            evaluate=AsyncMock(side_effect=[False, True]),
            wait_for_timeout=AsyncMock(),
        )
        step = {'timeout_ms': 5000, 'assertions': [{
            'assert_kind': 'element_state',
            'operator': 'exists',
            'target': {'intent': 'camera thumbnail', 'visual_content': 'image', 'locator': '#thumb'},
        }]}

        asyncio.run(PyUICompatAgent()._wait_for_assertion_observation(page, step))

        self.assertEqual(page.evaluate.await_count, 2)
        self.assertEqual(page.evaluate.await_args_list[0].args[1], ['#thumb'])
        self.assertEqual(
            [call.args[0] for call in page.wait_for_timeout.await_args_list],
            [500, 300],
        )

    def test_unbound_image_assertion_waits_for_media_introduced_since_baseline(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Visual_Wait')
        agent._rendered_visual_baseline = {'#old'}
        agent._rendered_visual_elements = AsyncMock(side_effect=[
            [{'selector': '#old'}],
            [{'selector': '#old'}, {'selector': '#detail-image'}],
        ])
        page = SimpleNamespace(evaluate=AsyncMock(return_value=True), wait_for_timeout=AsyncMock())
        step = {'timeout_ms': 8000, 'assertions': [{
            'assert_kind': 'element_state',
            'operator': 'exists',
            'target': {'intent': 'alert detail content', 'visual_content': 'image'},
        }]}

        asyncio.run(agent._wait_for_assertion_observation(page, step))

        page.evaluate.assert_not_awaited()
        self.assertEqual(agent._rendered_visual_elements.await_count, 2)
        self.assertEqual([call.args[0] for call in page.wait_for_timeout.await_args_list], [500, 300])

    def test_intent_only_exists_assertion_waits_briefly_only_with_baseline(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Visual_Wait')
        agent._rendered_visual_elements = AsyncMock(return_value=[{'selector': '#panel-canvas'}])
        page = SimpleNamespace(evaluate=AsyncMock(return_value=True), wait_for_timeout=AsyncMock())
        step = {'assertions': [{
            'assert_kind': 'element_state',
            'operator': 'exists',
            'target': {'intent': 'main window video panel in the opened case detail'},
        }]}

        asyncio.run(agent._wait_for_assertion_observation(page, step))
        agent._rendered_visual_elements.assert_not_awaited()
        page.evaluate.assert_not_awaited()

        agent._rendered_visual_baseline = set()
        asyncio.run(agent._wait_for_assertion_observation(page, step))
        self.assertEqual(agent._rendered_visual_elements.await_count, 1)
        page.evaluate.assert_not_awaited()

    def test_target_camera_wait_keeps_looking_for_the_card_until_its_thumbnail_renders(self) -> None:
        agent = PyUICompatAgent(case_name='Target_Card_Wait')
        agent._execution_resources = [{
            'resource_type': 'environment_device', 'resource_id': 'nvr_5003',
            'resource': {'role': 'main_device', 'device_id': 'nvr_5003', 'camera_names': ['5003_D13'], 'site': '萧山区'},
        }]
        agent._rendered_visual_baseline = set()
        card = {'selector': '#card-d13', 'name': '5003_D13', 'rect': {'x': 116, 'y': 586, 'width': 168, 'height': 94}}
        # The site group is collapsed at first; the card appears on a later probe and then its thumbnail renders.
        agent._build_actionable_controls = AsyncMock(side_effect=[[], [], [card], [card], [card]])
        agent._rendered_visual_elements = AsyncMock(side_effect=[
            [{'selector': '#other-thumb', 'rect': {'x': 292, 'y': 382, 'width': 168, 'height': 94}}],
            [{'selector': '#other-thumb', 'rect': {'x': 292, 'y': 382, 'width': 168, 'height': 94}}],
            [{'selector': '#other-thumb', 'rect': {'x': 292, 'y': 382, 'width': 168, 'height': 94}}],
            [{'selector': '#d13-thumb', 'rect': {'x': 120, 'y': 590, 'width': 160, 'height': 80}}],
        ])
        page = SimpleNamespace(evaluate=AsyncMock(return_value=True), wait_for_timeout=AsyncMock())
        step = {'description': 'Locate camera 5003_D13 among the cameras list and verify its thumbnail image displays normally.', 'assertions': [{
            'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True},
            'target': {'intent': 'thumbnail image on the camera icon for camera 5003_D13', 'visual_content': 'image'},
        }]}

        asyncio.run(agent._wait_for_rendered_visual_content(page, step, step['assertions']))

        # Another camera's thumbnail never counted as settled; the wait ended once a visual sat inside the target card.
        self.assertGreaterEqual(agent._build_actionable_controls.await_count, 2)
        self.assertEqual(agent._rendered_visual_elements.await_count, 4)
        page.evaluate.assert_not_awaited()
        self.assertTrue(page.wait_for_timeout.await_count >= 3)

    def test_binding_pass_waits_for_unrendered_image_assertions_first(self) -> None:
        source = inspect.getsource(PyUICompatAgent._bind_required_assertions_after_action)
        self.assertIn("assertion['target'].get('visual_content') == 'image'", source)
        self.assertIn('await self._wait_for_rendered_visual_content(page, step, image_unresolved)', source)
        self.assertLess(source.index('_wait_for_rendered_visual_content'), source.index('binders = ('))

    def test_rendered_image_detection_does_not_require_a_finished_refresh(self) -> None:
        """A thumbnail that refreshes its src every few seconds reports complete=false most of the time while still
        showing its previous picture; a decoded picture (naturalWidth > 1) is rendered content."""
        import re

        from apps.ai_testing.execution import browser_observers
        from apps.ai_testing.runtime.pyui_compat import runner

        for module in (runner, browser_observers):
            source = inspect.getsource(module)
            self.assertIsNone(re.search(r'\w+\.complete && \w+\.naturalWidth > 1', source), module.__name__)
        self.assertIn('return !element.complete && !(element.naturalWidth > 1);', runner.VISUAL_CONTENT_SETTLED_JS)
        self.assertIn('element.naturalWidth > 1 && element.naturalHeight > 1', runner.RENDERED_VISUAL_ELEMENTS_JS)

    def test_non_image_assertions_skip_visual_settle_probe(self) -> None:
        page = SimpleNamespace(evaluate=AsyncMock(return_value=True), wait_for_timeout=AsyncMock())
        step = {'assertions': [{
            'assert_kind': 'element_state',
            'operator': 'exists',
            'target': {'intent': 'status menu', 'locator': '#menu'},
        }]}

        asyncio.run(PyUICompatAgent()._wait_for_assertion_observation(page, step))

        page.evaluate.assert_not_awaited()
        page.wait_for_timeout.assert_awaited_once_with(300)

    def test_observable_discovery_includes_textless_rendered_visual_elements(self) -> None:
        source = inspect.getsource(PyUICompatAgent._build_observable_elements)

        self.assertIn('const ownVisual', source)
        self.assertIn('(text || ownVisual)', source)
        self.assertIn('has_visual_content: hasVisualContent', source)
        self.assertIn('left.offscreen - right.offscreen || left.order - right.order', source)
        self.assertIn("element['visual_signal'] = None", source)
        self.assertNotIn('.screenshot(', source)

    def test_actionable_discovery_flags_dialog_layers_for_popup_binding(self) -> None:
        discovery_source = inspect.getsource(PyUICompatAgent._build_actionable_controls)
        observation_source = inspect.getsource(PyUICompatAgent._collect_planner_observation)

        from apps.ai_testing.runtime.pyui_compat.runner import PLANNER_CONTROL_KEYS

        self.assertIn('dialog_layer: Boolean(dialog)', discovery_source)
        self.assertIn('dialog_layer', PLANNER_CONTROL_KEYS)
        self.assertIn('has_visual_content', PLANNER_CONTROL_KEYS)
        self.assertIn('_planner_control_baseline(actionable_controls)', observation_source)

    def test_rendered_visual_binding_prefers_fresh_top_layer_media(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Visual_Binding')
        assertion = {
            'assert_kind': 'element_state',
            'operator': 'exists',
            'expected': {'value': True},
            'target': {'intent': 'alert detail content', 'visual_content': 'image'},
        }
        step = {'assertions': [assertion]}
        agent._rendered_visual_baseline = {'body > div:nth-of-type(2) > img:nth-of-type(1)'}
        agent._rendered_visual_elements = AsyncMock(return_value=[
            {'selector': 'body > div:nth-of-type(2) > img:nth-of-type(1)', 'area': 90000, 'top_layer': False},
            {'selector': 'body > div:nth-of-type(8) > img:nth-of-type(1)', 'area': 240000, 'top_layer': True},
            {'selector': 'body > div:nth-of-type(8) > img:nth-of-type(2)', 'area': 4000, 'top_layer': True},
            {'selector': 'body > div:nth-of-type(3) > img:nth-of-type(1)', 'area': 500000, 'top_layer': False},
        ])

        bindings = asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), step, [assertion], {'action': 'click', 'selector': '#thumb'},
        ))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': 'body > div:nth-of-type(8) > img:nth-of-type(1)'}])

    def test_rendered_visual_binding_requires_baseline_and_image_assertion(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Visual_Binding')
        image_assertion = {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'visual_content': 'image'}}
        text_assertion = {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'text': 'Team'}}
        agent._rendered_visual_elements = AsyncMock(return_value=[{'selector': '#new', 'area': 1, 'top_layer': False}])

        self.assertEqual(asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), {'assertions': [image_assertion]}, [image_assertion], {'action': 'click'},
        )), [])
        agent._rendered_visual_baseline = set()
        self.assertEqual(asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), {'assertions': [text_assertion]}, [text_assertion], {'action': 'click'},
        )), [])
        agent._rendered_visual_elements = AsyncMock(return_value=[])
        self.assertEqual(asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), {'assertions': [image_assertion]}, [image_assertion], {'action': 'click'},
        )), [])

    def test_rendered_visual_binding_declines_ambiguous_in_page_media(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Visual_Binding')
        assertion = {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'visual_content': 'image'}}
        agent._rendered_visual_baseline = set()
        agent._rendered_visual_elements = AsyncMock(return_value=[
            {'selector': '#a', 'area': 100, 'top_layer': False},
            {'selector': '#b', 'area': 200, 'top_layer': False},
        ])

        self.assertEqual(asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), {'assertions': [assertion]}, [assertion], {'action': 'click'},
        )), [])

        agent._rendered_visual_elements = AsyncMock(return_value=[{'selector': '#only', 'area': 100, 'top_layer': False}])
        self.assertEqual(asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), {'assertions': [assertion]}, [assertion], {'action': 'click'},
        )), [{'assertion_index': 1, 'locator': '#only'}])

    def test_invisible_image_binding_is_cleared_before_rebinding(self) -> None:
        agent = PyUICompatAgent(case_name='Stale_Image_Binding', execution_record_id=9)
        step = {'assertions': [{
            'assert_kind': 'element_state',
            'operator': 'exists',
            'target': {'locator': 'body > div:nth-of-type(8) > div:nth-of-type(1)', 'intent': 'alert detail', 'visual_content': 'image'},
        }]}
        page = SimpleNamespace(locator=Mock(return_value=SimpleNamespace(
            count=AsyncMock(return_value=1),
            first=SimpleNamespace(is_visible=AsyncMock(return_value=False)),
        )))

        with patch('apps.ai_testing.execution.plan_persistence.persist_unbound_step') as persist_unbound_step:
            asyncio.run(agent._clear_vanished_assertion_bindings(page, step, 3))

        self.assertNotIn('locator', step['assertions'][0]['target'])
        persist_unbound_step.assert_called_once_with(9, 3, [1])

    def test_rendered_visual_binding_covers_intent_only_detail_panel_assertions(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Visual_Binding')
        assertion = {
            'assert_kind': 'element_state',
            'operator': 'exists',
            'expected': {'value': True},
            'target': {'intent': 'main window video panel in the opened case detail'},
        }
        step = {'assertions': [assertion]}
        agent._rendered_visual_baseline = {'body > div:nth-of-type(1) > img:nth-of-type(1)'}
        agent._rendered_visual_elements = AsyncMock(return_value=[
            {'selector': 'body > div:nth-of-type(1) > img:nth-of-type(1)', 'area': 11000, 'viewport_ratio': 0.007, 'top_layer': False},
            {'selector': 'body > div:nth-of-type(1) > img:nth-of-type(2)', 'area': 11000, 'viewport_ratio': 0.007, 'top_layer': False},
            {'selector': 'body > div:nth-of-type(1) > canvas:nth-of-type(1)', 'area': 867000, 'viewport_ratio': 0.55, 'top_layer': False},
        ])

        bindings = asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), step, [assertion], {'action': 'click', 'selector': '#case-thumb'},
        ))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': 'body > div:nth-of-type(1) > canvas:nth-of-type(1)'}])

        agent._rendered_visual_elements = AsyncMock(return_value=[
            {'selector': 'body > div:nth-of-type(9) > img:nth-of-type(1)', 'area': 11000, 'viewport_ratio': 0.007, 'top_layer': True},
        ])
        self.assertEqual(asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), step, [assertion], {'action': 'click'},
        )), [])

        text_assertion = {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'status', 'text': 'Investigate'}}
        agent._rendered_visual_elements = AsyncMock(return_value=[
            {'selector': 'body > div:nth-of-type(1) > canvas:nth-of-type(1)', 'area': 867000, 'viewport_ratio': 0.55, 'top_layer': False},
        ])
        self.assertEqual(asyncio.run(agent._rendered_visual_binding_from_completed_action(
            object(), {'assertions': [text_assertion]}, [text_assertion], {'action': 'click'},
        )), [])

    def test_rendered_visual_baseline_is_captured_for_intent_only_exists_assertions(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Visual_Binding')
        agent._rendered_visual_elements = AsyncMock(return_value=[{'selector': '#surface', 'area': 1}])

        self.assertEqual(asyncio.run(agent._capture_rendered_visual_baseline(object(), {'assertions': [
            {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'detail video panel'}},
        ]})), {'#surface'})
        self.assertIsNone(asyncio.run(agent._capture_rendered_visual_baseline(object(), {'assertions': [
            {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'status', 'text': 'Investigate'}},
        ]})))

    def test_selected_value_binder_picks_display_control_not_options_or_cards(self) -> None:
        agent = PyUICompatAgent(case_name='Selected_Value_Binding')
        assertion = {'assert_kind': 'field_value', 'operator': 'starts_with', 'expected': {'value': 'Site Manager'}, 'target': {'intent': 'role dropdown'}}
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'selector': '[title="Site Manager (Can manage sites)"]', 'tag': 'div', 'role': '', 'name': 'Site Manager (Can manage sites)', 'top_layer': False, 'group_size': 1, 'rect': {'x': 600, 'y': 700, 'width': 240, 'height': 32}},
            {'selector': 'body > div:nth-of-type(9) > div:nth-of-type(2)', 'tag': 'div', 'role': 'option', 'name': 'Site Manager (Can manage sites)', 'top_layer': True, 'group_size': 5, 'rect': {'x': 600, 'y': 760, 'width': 240, 'height': 32}},
            {'selector': '#card-3', 'tag': 'div', 'role': '', 'name': 'M\n\nms site manager\n\nSite Manager', 'top_layer': False, 'group_size': 4, 'rect': {'x': 120, 'y': 435, 'width': 335, 'height': 105}},
        ])
        agent._build_observable_elements = AsyncMock(return_value=[
            {'selector': 'body > div:nth-of-type(1) > span:nth-of-type(3)', 'tag': 'span', 'text': 'Site Manager (Can manage sites)', 'rect': {'x': 600, 'y': 700, 'width': 240, 'height': 32}},
        ])

        bindings = asyncio.run(agent._selected_value_binding_from_completed_click(
            object(), {'assertions': [assertion]}, [assertion], {'action': 'click', 'selector': '[title="Site Manager (Can manage sites)"]'},
        ))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '[title="Site Manager (Can manage sites)"]'}])

        agent._build_observable_elements = AsyncMock(return_value=[])
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'selector': '#a', 'tag': 'div', 'name': 'Site Manager A', 'top_layer': False, 'group_size': 1},
            {'selector': '#b', 'tag': 'div', 'name': 'Site Manager B', 'top_layer': False, 'group_size': 1},
        ])
        self.assertEqual(asyncio.run(agent._selected_value_binding_from_completed_click(
            object(), {'assertions': [assertion]}, [assertion], {'action': 'click'},
        )), [])

    def test_ai_action_execution_captures_rendered_visual_baseline(self) -> None:
        source = inspect.getsource(PyUICompatAgent._execute_ai_actions)
        binding_source = inspect.getsource(PyUICompatAgent._bind_required_assertions_after_action)

        self.assertIn('self._rendered_visual_baseline = await self._capture_rendered_visual_baseline(page, step)', source)
        self.assertIn('_rendered_visual_binding_from_completed_action', binding_source)

    def test_fill_match_tolerates_phone_masks_but_not_digit_changes(self) -> None:
        self.assertTrue(PyUICompatAgent._fill_matches('+1 6465180948', '+1 (646) 518-0948'))
        self.assertFalse(PyUICompatAgent._fill_matches('+1 6465180948', '+1 (164) 651-8094'))
        self.assertTrue(PyUICompatAgent._fill_matches('ai@test.com', 'ai@test.com'))
        self.assertTrue(PyUICompatAgent._fill_matches('black hair', 'Black  hair'))
        self.assertFalse(PyUICompatAgent._fill_matches('black hair', 'black'))
        self.assertTrue(PyUICompatAgent._fill_matches('', 'anything'))

    def test_fill_repair_retypes_without_the_prefix_the_field_keeps(self) -> None:
        agent = PyUICompatAgent(case_name='Fill_Repair')
        typed = []
        values = iter(['+1 (164) 651-8094', '+1', '+1 (646) 518-0948'])
        locator = SimpleNamespace(
            input_value=AsyncMock(side_effect=lambda **kwargs: next(values)),
            click=AsyncMock(),
            press=AsyncMock(),
            press_sequentially=AsyncMock(side_effect=lambda text, **kwargs: typed.append(text)),
        )

        asyncio.run(agent._repair_fill_if_mismatched(locator, '+1 6465180948', 10000))

        self.assertEqual(typed, ['6465180948'])
        self.assertEqual([call.args[0] for call in locator.press.await_args_list], ['Control+A', 'Backspace'])

    def test_fill_repair_is_skipped_when_the_value_landed(self) -> None:
        agent = PyUICompatAgent(case_name='Fill_Repair')
        locator = SimpleNamespace(
            input_value=AsyncMock(return_value='ai@test.com'),
            click=AsyncMock(),
            press=AsyncMock(),
            press_sequentially=AsyncMock(),
        )

        asyncio.run(agent._repair_fill_if_mismatched(locator, 'ai@test.com', 10000))

        locator.press_sequentially.assert_not_awaited()
        locator.click.assert_not_awaited()

    def test_assertion_shortfall_includes_observed_values(self) -> None:
        step = {'assertions': [
            {'assert_kind': 'field_value', 'operator': 'phone_digits_equals', 'expected': {'value': '16465180948'}, 'target': {'intent': 'phone input'}},
        ]}
        detail = PyUICompatAgent._describe_assertion_shortfall(
            step, ['failed'], actuals=[{'value': '+1 (164) 651-8094', 'reason': 'Assertion did not match evidence.'}],
        )

        self.assertIn('observed=', detail)
        self.assertIn('+1 (164) 651-8094', detail)
        self.assertNotIn('did not match', detail)

    def test_stale_binding_revalidation_covers_all_bound_dom_assertions(self) -> None:
        agent = PyUICompatAgent(case_name='Stale_Bindings', execution_record_id=11)
        step = {'assertions': [
            {'assert_kind': 'field_value', 'operator': 'starts_with', 'expected': {'value': 'Site Manager'}, 'target': {'locator': '#gone-input', 'intent': 'role'}},
            {'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'locator': '#gone-rows', 'intent': 'rows'}},
            {'assert_kind': 'absence', 'operator': 'not_exists', 'expected': {'value': True}, 'target': {'locator': '#gone-toast', 'intent': 'toast'}},
            {'assert_kind': 'popup', 'operator': 'exists', 'expected': {'value': True}, 'target': {'locator': '#hidden-dialog', 'intent': 'dialog'}},
            {'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'locator': '#still-here', 'intent': 'panel'}},
        ]}
        handles = {
            '#gone-input': SimpleNamespace(count=AsyncMock(return_value=0)),
            '#gone-rows': SimpleNamespace(count=AsyncMock(return_value=0)),
            '#gone-toast': SimpleNamespace(count=AsyncMock(return_value=0)),
            '#hidden-dialog': SimpleNamespace(count=AsyncMock(return_value=1), first=SimpleNamespace(is_visible=AsyncMock(return_value=False))),
            '#still-here': SimpleNamespace(count=AsyncMock(return_value=1), first=SimpleNamespace(is_visible=AsyncMock(return_value=True))),
        }
        page = SimpleNamespace(locator=lambda selector: handles[selector])

        with patch('apps.ai_testing.execution.plan_persistence.persist_unbound_step') as persist_unbound_step:
            asyncio.run(agent._clear_vanished_assertion_bindings(page, step, 4))

        persist_unbound_step.assert_called_once_with(11, 4, [1, 2, 4])
        self.assertNotIn('locator', step['assertions'][0]['target'])
        self.assertNotIn('locator', step['assertions'][1]['target'])
        self.assertEqual(step['assertions'][2]['target']['locator'], '#gone-toast')
        self.assertNotIn('locator', step['assertions'][3]['target'])
        self.assertEqual(step['assertions'][4]['target']['locator'], '#still-here')

    def test_planner_retries_keep_trying_identical_plan_rejections_up_to_the_limit(self) -> None:
        from apps.ai_testing.global_planner import GlobalPlanError
        from apps.ai_testing.runtime.pyui_compat.runner import PlannerRetryExhaustedError

        agent = PyUICompatAgent(case_name='Repeated_Rejection')
        agent._plan_ai_step = AsyncMock(side_effect=GlobalPlanError('Planner Vision returned assert without complete locator bindings.'))
        history = HistoryStub()

        with patch('apps.ai_testing.runtime.pyui_compat.runner.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(PlannerRetryExhaustedError):
                asyncio.run(agent._plan_ai_step_with_retries(object(), {'description': 'Open the detail'}, history, step_index=3))

        self.assertEqual(agent._plan_ai_step.await_count, 4)

    def test_transient_model_errors_back_off_without_consuming_plan_attempts(self) -> None:
        class LLMClientError(Exception):
            pass

        agent = PyUICompatAgent(case_name='Transient_Model')
        agent._plan_ai_step = AsyncMock(side_effect=[
            LLMClientError('Google Gemini API返回错误 503: high demand'),
            LLMClientError('Google Gemini API返回错误 503: high demand'),
            [{'action': 'click', 'selector': '#ok'}],
        ])
        history = HistoryStub()
        sleeps = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        with patch('apps.ai_testing.runtime.pyui_compat.runner.asyncio.sleep', new=fake_sleep):
            actions = asyncio.run(agent._plan_ai_step_with_retries(object(), {'description': 'Open'}, history, step_index=2, max_attempts=1))

        self.assertEqual(actions, [{'action': 'click', 'selector': '#ok'}])
        self.assertEqual(sleeps, [2.0, 4.0])
        self.assertEqual(history.cache_stats['model_transient_retries'], 2)
        self.assertEqual([a['status'] for a in history.artifacts], ['transient_error', 'transient_error'])
        self.assertEqual(agent._plan_ai_step.await_args_list[-1].args[1]['description'], 'Open')

    def test_transient_retry_window_covers_a_multi_minute_provider_spike(self) -> None:
        from apps.ai_testing.runtime.pyui_compat import runner as runner_module

        total_wait = sum(min(runner_module.TRANSIENT_MODEL_BACKOFF_CAP_SECONDS, 2.0 ** n) for n in range(1, runner_module.TRANSIENT_MODEL_RETRIES + 1))
        self.assertGreaterEqual(total_wait, 600)
        self.assertLess(total_wait, 900)
        source = inspect.getsource(PyUICompatAgent._plan_ai_step_with_retries)
        self.assertIn('max_transient_retries=TRANSIENT_MODEL_RETRIES', source)
        self.assertIn('self._step_deadline += delay', source)

    def test_transient_error_classification(self) -> None:
        class LLMClientError(Exception):
            pass

        from apps.ai_testing.global_planner import GlobalPlanError

        self.assertTrue(PyUICompatAgent._is_transient_llm_error(LLMClientError('Google Gemini API返回错误 503: ...')))
        self.assertTrue(PyUICompatAgent._is_transient_llm_error(LLMClientError('API返回错误 429: rate limit')))
        self.assertTrue(PyUICompatAgent._is_transient_llm_error(asyncio.TimeoutError()))
        self.assertFalse(PyUICompatAgent._is_transient_llm_error(LLMClientError('API返回错误 400: bad request')))
        self.assertFalse(PyUICompatAgent._is_transient_llm_error(GlobalPlanError('Planner Vision returned assert without complete locator bindings.')))
        self.assertFalse(PyUICompatAgent._is_transient_llm_error(ValueError('Browser action scroll requires capability browser.act.')))

    def test_fresh_content_binder_targets_the_largest_new_content_block(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Content')
        assertion = {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'site list or cameras area after opening Cameras'}}
        step = {'assertions': [assertion]}
        agent._observable_baseline = {'#nav', '#header'}
        agent._build_observable_elements = AsyncMock(return_value=[
            {'selector': '#nav', 'text': 'Cameras', 'rect': {'x': 0, 'y': 0, 'width': 80, 'height': 800}},
            {'selector': '#root > div:nth-of-type(2)', 'text': 'Sites 萧山区 5003_D03', 'rect': {'x': 100, 'y': 60, 'width': 400, 'height': 700}},
            {'selector': '#root > div:nth-of-type(2) > span:nth-of-type(1)', 'text': '萧山区', 'rect': {'x': 120, 'y': 80, 'width': 100, 'height': 20}},
            {'selector': '#root > div:nth-of-type(3)', 'text': '', 'rect': {'x': 520, 'y': 60, 'width': 1200, 'height': 800}},
        ])

        bindings = asyncio.run(agent._fresh_content_binding_from_completed_action(object(), step, [assertion], {'action': 'click', 'selector': '#nav'}))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '#root > div:nth-of-type(2)'}])

        agent._build_observable_elements = AsyncMock(return_value=[{'selector': '#only-new', 'text': 'x', 'rect': {'x': 0, 'y': 0, 'width': 500, 'height': 500}}])
        self.assertEqual(asyncio.run(agent._fresh_content_binding_from_completed_action(object(), step, [assertion], {'action': 'click'})), [])
        image_assertion = {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'thumb', 'visual_content': 'image'}}
        self.assertEqual(asyncio.run(agent._fresh_content_binding_from_completed_action(object(), {'assertions': [image_assertion]}, [image_assertion], {'action': 'click'})), [])

    def test_planner_retries_continue_when_rejections_differ(self) -> None:
        from apps.ai_testing.global_planner import GlobalPlanError
        from apps.ai_testing.runtime.pyui_compat.runner import PlannerRetryExhaustedError

        agent = PyUICompatAgent(case_name='Different_Rejections')
        agent._plan_ai_step = AsyncMock(side_effect=[GlobalPlanError('first'), GlobalPlanError('second'), GlobalPlanError('third'), GlobalPlanError('fourth')])
        history = HistoryStub()

        with patch('apps.ai_testing.runtime.pyui_compat.runner.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(PlannerRetryExhaustedError):
                asyncio.run(agent._plan_ai_step_with_retries(object(), {'description': 'Open the detail'}, history, step_index=3))

        self.assertEqual(agent._plan_ai_step.await_count, 4)

    def test_assertion_retry_stops_when_step_time_budget_is_exhausted(self) -> None:
        import time as _time

        agent = PyUICompatAgent(case_name='Budget', execution_record_id=7)
        agent._step_deadline = _time.monotonic() - 1
        agent._clear_vanished_assertion_bindings = AsyncMock()
        agent._latest_assertion_actuals = Mock(return_value=[])
        agent._persisted_step_action_history = Mock(return_value=[])
        agent._plan_ai_step_with_retries = AsyncMock()
        step = {'description': 'Click the thumbnail', 'assertions': [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'detail'}}]}

        agent._recover_by_rebinding = AsyncMock(return_value=None)
        result = asyncio.run(agent._retry_assertion_failure(
            SimpleNamespace(wait_for_timeout=AsyncMock()), step, 3, [{'action': 'click', 'selector': '#thumb'}], ['inconclusive'], None, TimeoutError, HistoryStub(), None,
        ))

        self.assertEqual(result[0], 'inconclusive')
        self.assertIn('time budget', result[1])
        agent._recover_by_rebinding.assert_not_awaited()
        agent._plan_ai_step_with_retries.assert_not_awaited()

    def test_step_time_budget_reads_environment_runtime_settings(self) -> None:
        agent = PyUICompatAgent(case_name='Budget')
        self.assertEqual(agent._step_time_budget_seconds(), 600)
        agent.environment_configuration = SimpleNamespace(runtime_settings={'ai_testing_browser': {'step_time_budget_seconds': 30}})
        self.assertEqual(agent._step_time_budget_seconds(), 60)
        agent.environment_configuration = SimpleNamespace(runtime_settings={'ai_testing_browser': {'step_time_budget_seconds': 900}})
        self.assertEqual(agent._step_time_budget_seconds(), 900)

    def test_playback_steps_capture_frames_right_before_the_action(self) -> None:
        source = inspect.getsource(PyUICompatAgent._execute_ai_actions)
        retry_source = inspect.getsource(PyUICompatAgent._retry_assertion_failure)

        self.assertIn('self._pre_action_visual_frames = await capture_visual_frames(page', source)
        self.assertIn('self._pre_action_visual_frames or visual_frames_before', retry_source)

    def test_structural_selectors_prefer_unique_anchors(self) -> None:
        from apps.ai_testing.runtime.pyui_compat.runner import RENDERED_VISUAL_ELEMENTS_JS

        for source in (
            inspect.getsource(PyUICompatAgent._build_actionable_controls),
            inspect.getsource(PyUICompatAgent._build_observable_elements),
            RENDERED_VISUAL_ELEMENTS_JS,
        ):
            self.assertIn('const uniqueAnchor = (node) =>', source)
            self.assertIn('[data-testid=${JSON.stringify(testId)}]', source)
            self.assertIn('if (node.parentElement === document.body)', source)

    def test_structural_text_masks_digit_runs_for_fingerprint_stability(self) -> None:
        self.assertEqual(
            PyUICompatAgent._structural_text('Today,  11:36 AM\n5003_D03 Person (3)'),
            'Today, #:# AM #_D# Person (#)',
        )

    def test_page_fingerprint_follows_the_dom_skeleton_not_the_text(self) -> None:
        def page_with(skeleton, title='Alpha Vision (3)'):
            locator = SimpleNamespace(count=AsyncMock(return_value=0))
            return SimpleNamespace(
                url='https://app.example.com/dashboard/alerts/basic?page=2',
                title=AsyncMock(return_value=title),
                locator=Mock(return_value=locator),
                evaluate=AsyncMock(return_value=skeleton),
            )

        agent = PyUICompatAgent(case_name='Fingerprint')
        base = 'body(div#root(nav(a*),main(div[role=list](div*))))'
        first = asyncio.run(agent._build_page_context(page_with(base)))
        same_shape_other_data = asyncio.run(agent._build_page_context(page_with(base, title='Alpha Vision (12)')))
        dialog_open = asyncio.run(agent._build_page_context(page_with(base[:-1] + ',div[role=dialog](button*))')))
        without_skeleton = asyncio.run(agent._build_page_context(page_with('')))

        self.assertEqual(first['fingerprint'], same_shape_other_data['fingerprint'])
        self.assertNotEqual(first['fingerprint'], dialog_open['fingerprint'])
        self.assertEqual(first['url'], 'https://app.example.com/dashboard/alerts/basic')
        self.assertEqual(without_skeleton['fingerprint'], '')
        self.assertEqual(first['skeleton_size'], len(base))

    def test_page_skeleton_script_collapses_repeats_and_ignores_text(self) -> None:
        from apps.ai_testing.runtime.pyui_compat.runner import PAGE_SKELETON_JS

        self.assertIn("seen.has(key)", PAGE_SKELETON_JS)
        self.assertIn("checkVisibility", PAGE_SKELETON_JS)
        self.assertIn("'aria-expanded'", PAGE_SKELETON_JS)
        self.assertNotIn('innerText', PAGE_SKELETON_JS)
        self.assertNotIn('textContent', PAGE_SKELETON_JS)

    def test_reused_actions_are_checked_against_the_live_page_before_running(self) -> None:
        agent = PyUICompatAgent(case_name='Reuse_Check')
        agent._build_actionable_controls = AsyncMock(return_value=[{'selector': '#save', 'blocking_layer': False}])

        def page_with(count, visible=True):
            first = SimpleNamespace(is_visible=AsyncMock(return_value=visible))
            locator = SimpleNamespace(count=AsyncMock(return_value=count), first=first)
            return SimpleNamespace(locator=Mock(return_value=locator), get_by_role=Mock(return_value=SimpleNamespace(count=AsyncMock(return_value=count))))

        actions = [{'action': 'click', 'selector': '#save'}]
        self.assertEqual(asyncio.run(agent._reused_actions_applicable(page_with(1), actions)), '')
        self.assertIn('not on page', asyncio.run(agent._reused_actions_applicable(page_with(0), actions)))
        self.assertIn('hidden', asyncio.run(agent._reused_actions_applicable(page_with(1, visible=False), actions)))
        self.assertEqual(asyncio.run(agent._reused_actions_applicable(None, actions)), '')
        self.assertEqual(asyncio.run(agent._reused_actions_applicable(page_with(0), [{'action': 'assert'}])), '')
        self.assertIn('role target', asyncio.run(agent._reused_actions_applicable(page_with(0), [{'action': 'click', 'role': 'button', 'accessible_name': 'Save'}])))

        # An open dialog blocks a reused target outside it.
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'selector': '#dialog-ok', 'blocking_layer': True, 'blocking_layer_id': 'body > div.modal', 'dialog_layer': True, 'z_index': 1000},
            {'selector': '#save', 'blocking_layer': False},
        ])
        self.assertIn('blocking dialog', asyncio.run(agent._reused_actions_applicable(page_with(1), actions)))
        self.assertEqual(asyncio.run(agent._reused_actions_applicable(page_with(1), [{'action': 'click', 'selector': '#dialog-ok'}])), '')

    def test_reused_actions_check_refreshes_planner_baselines(self) -> None:
        agent = PyUICompatAgent(case_name='Reuse_Baseline')
        controls = [{'selector': '#save', 'name': 'Save', 'rect': {'x': 1, 'y': 2, 'width': 30, 'height': 20}, 'blocking_layer': False, 'ignored_key': 'x'}]
        agent._build_actionable_controls = AsyncMock(return_value=controls)
        first = SimpleNamespace(is_visible=AsyncMock(return_value=True))
        page = SimpleNamespace(locator=Mock(return_value=SimpleNamespace(count=AsyncMock(return_value=1), first=first)))

        with patch('apps.ai_testing.execution.page_observation.capture_accessibility_snapshot', new=AsyncMock(return_value={'snapshot_id': 's1', 'nodes': []})):
            reason = asyncio.run(agent._reused_actions_applicable(page, [{'action': 'click', 'selector': '#save'}]))

        self.assertEqual(reason, '')
        self.assertEqual(agent._last_actionable_controls[0]['selector'], '#save')
        self.assertNotIn('ignored_key', agent._last_actionable_controls[0])
        self.assertEqual(agent._last_accessibility_snapshot.get('snapshot_id'), 's1')

    def test_selected_value_binder_accepts_an_unchanged_display_after_the_dialog_closed(self) -> None:
        agent = PyUICompatAgent(case_name='Committed_Value')
        assertion = {'assert_kind': 'field_value', 'operator': 'starts_with', 'expected': {'value': 'Investigate'}, 'target': {'intent': 'To Do dropdown committed selected value'}}
        display = {'selector': '#status-dropdown', 'tag': 'div', 'role': 'combobox', 'name': 'Investigate', 'top_layer': False, 'group_size': 1, 'rect': {'x': 520, 'y': 819, 'width': 104, 'height': 30}}
        agent._build_actionable_controls = AsyncMock(return_value=[display, {'selector': '#home', 'name': 'Home', 'rect': {'x': 10, 'y': 10, 'width': 40, 'height': 40}}])
        agent._build_observable_elements = AsyncMock(return_value=[])
        # The dropdown already displayed the pending value while the confirmation dialog was open.
        agent._pre_action_control_names = {((520, 819, 104, 30), 'Investigate'), ((10, 10, 40, 40), 'Home')}
        page = SimpleNamespace(wait_for_timeout=AsyncMock())
        click = {'action': 'click', 'selector': '#dialog-confirm'}

        agent._pre_action_blocking_layer = True
        self.assertEqual(
            asyncio.run(agent._selected_value_binding_from_completed_click(page, {'assertions': [assertion]}, [assertion], click)),
            [{'assertion_index': 1, 'locator': '#status-dropdown'}],
        )
        # Without a dialog having closed, an unchanged display is still not evidence of this click's effect.
        agent._pre_action_blocking_layer = False
        self.assertEqual(asyncio.run(agent._selected_value_binding_from_completed_click(page, {'assertions': [assertion]}, [assertion], click)), [])

    def test_assert_only_outcomes_are_never_stored_for_reuse(self) -> None:
        self.assertEqual(PyUICompatAgent._safe_experience_actions([{'action': 'assert', 'assert_kind': 'element_state'}]), [])
        self.assertEqual(PyUICompatAgent._safe_experience_actions([{'action': 'wait'}, {'action': 'assert'}]), [])
        self.assertEqual(
            PyUICompatAgent._safe_experience_actions([{'action': 'click', 'selector': '#deactivate'}, {'action': 'assert'}]),
            [{'action': 'click', 'selector': '#deactivate'}, {'action': 'assert'}],
        )
        self.assertFalse(PyUICompatAgent._reusable_action_sequence([{'action': 'assert'}]))
        self.assertTrue(PyUICompatAgent._reusable_action_sequence([{'action': 'fill', 'selector': '#q', 'value': 'x'}]))
        for name in ('_find_cached_actions_sync', '_find_experience_actions'):
            self.assertIn('_reusable_action_sequence', inspect.getsource(getattr(PyUICompatAgent, name)), name)

    def test_stale_cached_actions_are_skipped_and_dropped(self) -> None:
        agent = PyUICompatAgent(case_name='Stale_Cache')
        step = {'index': 2, 'description': 'Open the panel'}
        history = HistoryStub()
        agent._build_page_context = AsyncMock(return_value={'url': 'https://example.test/x', 'fingerprint': 'fp'})
        agent._load_cached_ai_actions = AsyncMock(return_value=[{'action': 'click', 'selector': '#gone'}])
        agent._reused_actions_applicable = AsyncMock(return_value='selector not on page: #gone')
        agent._delete_cached_ai_actions = AsyncMock()
        agent._load_verified_experience = AsyncMock(return_value=None)
        agent._plan_ai_step_for_cacheable_step = AsyncMock(return_value=[{'action': 'click', 'selector': '#fresh'}])

        actions, source = asyncio.run(agent._get_ai_actions_for_step(page=SimpleNamespace(), step=step, history=history))

        self.assertEqual((actions, source), ([{'action': 'click', 'selector': '#fresh'}], 'model'))
        self.assertEqual(history.cache_stats['stale_skip'], 1)
        self.assertEqual(history.cache_stats['hit'], 0)
        agent._delete_cached_ai_actions.assert_awaited_once()

    def test_experience_reuse_is_part_of_the_cache_opt_in(self) -> None:
        agent = PyUICompatAgent(case_name='No_Cache', use_cache=False)
        step = {'index': 2, 'description': 'Open the panel'}
        agent._build_page_context = AsyncMock(return_value={'url': 'https://example.test/x', 'fingerprint': 'fp'})
        agent._load_cached_ai_actions = AsyncMock(return_value=[{'action': 'click', 'selector': '#cached'}])
        agent._load_verified_experience = AsyncMock(return_value=[{'action': 'click', 'selector': '#experience'}])
        agent._plan_ai_step_for_cacheable_step = AsyncMock(return_value=[{'action': 'click', 'selector': '#fresh'}])

        actions, source = asyncio.run(agent._get_ai_actions_for_step(page=None, step=step, history=HistoryStub()))

        self.assertEqual((actions, source), ([{'action': 'click', 'selector': '#fresh'}], 'model'))
        agent._load_cached_ai_actions.assert_not_awaited()
        agent._load_verified_experience.assert_not_awaited()

    def test_force_replan_bypasses_only_the_plan_cache(self) -> None:
        source = inspect.getsource(PyUICompatAgent.run_full_process)
        self.assertIn('use_cache=self.use_cache and not self.force_replan', source)
        self.assertIn("'plan_cache_hit': 1 if plan_source == 'cache' else 0", source)
        self.assertTrue(PyUICompatAgent(case_name='x', force_replan=True).force_replan)
        self.assertFalse(PyUICompatAgent(case_name='x').force_replan)

    def test_experience_reuse_policy_defaults_to_auto_verified(self) -> None:
        agent = PyUICompatAgent(case_name='Policy')
        self.assertEqual(agent._experience_reuse_policy(), 'auto_verified')
        agent.environment_configuration = SimpleNamespace(runtime_settings={'ai_testing_browser': {'experience_reuse_policy': 'confirmed_only'}})
        self.assertEqual(agent._experience_reuse_policy(), 'confirmed_only')
        agent.environment_configuration = SimpleNamespace(runtime_settings={'ai_testing_browser': {'experience_reuse_policy': 'anything'}})
        self.assertEqual(agent._experience_reuse_policy(), 'auto_verified')
        self.assertEqual(agent._action_cache_ttl().days, 30)
        agent.environment_configuration = SimpleNamespace(runtime_settings={'ai_testing_browser': {'action_cache_ttl_days': 7, 'action_cache_variants_per_step': 3}})
        self.assertEqual(agent._action_cache_ttl().days, 7)
        self.assertEqual(agent._action_cache_variant_limit(), 3)

    def test_observable_dedupe_removes_nodes_already_listed_as_controls(self) -> None:
        controls = [{'selector': '[title="Site Manager"]', 'name': 'Site Manager', 'rect': {'x': 10, 'y': 20, 'width': 100, 'height': 30}}]
        observables = [
            {'selector': 'body > div:nth-of-type(1) > span:nth-of-type(1)', 'text': 'Site Manager', 'rect': {'x': 10, 'y': 20, 'width': 100, 'height': 30}},
            {'selector': 'body > div:nth-of-type(1) > span:nth-of-type(2)', 'text': 'Org Admin', 'rect': {'x': 10, 'y': 60, 'width': 100, 'height': 30}},
            {'selector': 'body > div:nth-of-type(2) > li:nth-of-type(1)', 'text': 'Site Manager', 'group_selector': 'body > div:nth-of-type(2) > li', 'rect': {'x': 10, 'y': 20, 'width': 100, 'height': 30}},
        ]

        deduped = PyUICompatAgent._dedupe_observable_elements(controls, observables)

        self.assertEqual([item['selector'] for item in deduped], [
            'body > div:nth-of-type(1) > span:nth-of-type(2)',
            'body > div:nth-of-type(2) > li:nth-of-type(1)',
        ])

    def test_audit_payload_records_a_value_digest_without_plaintext(self) -> None:
        first = PyUICompatAgent._audit_action_payload({'action': 'fill', 'selector': '#email', 'value': 'ai@test.com'}, {})
        same = PyUICompatAgent._audit_action_payload({'action': 'fill', 'selector': '#email', 'value': 'ai@test.com'}, {})
        other = PyUICompatAgent._audit_action_payload({'action': 'fill', 'selector': '#email', 'value': 'bo@test.com'}, {})
        empty = PyUICompatAgent._audit_action_payload({'action': 'click', 'selector': '#go'}, {})

        self.assertNotIn('value', first)
        self.assertTrue(first['value_present'])
        self.assertTrue(first['value_digest'].startswith('sha256:'))
        self.assertTrue(first['value_digest'].endswith('/len=11'))
        self.assertNotIn('ai@test.com', first['value_digest'])
        self.assertEqual(first['value_digest'], same['value_digest'])
        self.assertNotEqual(first['value_digest'], other['value_digest'])
        self.assertEqual(empty['value_digest'], '')

    def test_fill_repair_records_a_runtime_event_that_drains_into_artifacts(self) -> None:
        agent = PyUICompatAgent(case_name='Fill_Repair_Event')
        values = iter(['+1 (164) 651-8094', '+1', '+1 (646) 518-0948'])
        locator = SimpleNamespace(
            input_value=AsyncMock(side_effect=lambda **kwargs: next(values)),
            click=AsyncMock(), press=AsyncMock(), press_sequentially=AsyncMock(),
        )

        asyncio.run(agent._repair_fill_if_mismatched(locator, '+1 6465180948', 10000))

        self.assertEqual(len(agent._runtime_events), 1)
        self.assertEqual(agent._runtime_events[0]['result'], 'repaired')
        history = HistoryStub()
        agent._drain_runtime_events(history, 7)
        self.assertEqual(agent._runtime_events, [])
        self.assertEqual(history.artifacts[0]['type'], 'fill_repair')
        self.assertEqual(history.artifacts[0]['step'], 7)

    def test_deterministic_binding_is_recorded_as_an_artifact(self) -> None:
        agent = PyUICompatAgent(case_name='Binding_Artifact')
        agent._field_value_bindings_from_completed_action = AsyncMock(return_value=[{'assertion_index': 1, 'locator': '#email'}])
        agent._apply_assertion_bindings = AsyncMock()
        history = HistoryStub()
        step = {'assertions': [{'assert_kind': 'field_value', 'operator': 'equals', 'expected': {'value': 'ai@test.com'}, 'target': {'intent': 'email input'}}]}

        bound = asyncio.run(agent._bind_required_assertions_after_action(
            object(), step, 4, [{'action': 'fill', 'value': 'ai@test.com'}], None, history,
        ))

        self.assertTrue(bound)
        self.assertEqual(history.artifacts, [{
            'type': 'deterministic_binding', 'step': 4, 'binder': 'field_value',
            'bindings': [{'assertion_index': 1, 'locator': '#email'}],
        }])

    def test_assertion_retry_recovers_by_rebinding_before_replanning(self) -> None:
        agent = PyUICompatAgent(case_name='Rebind_Recovery', execution_record_id=7)
        step = {'description': 'Open the form', 'assertions': [{
            'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'target': {'intent': 'create user form'},
        }]}

        async def bind(page, s, index, actions, callback, history):
            s['assertions'][0]['target']['locator'] = '#form'
            return True

        agent._clear_vanished_assertion_bindings = AsyncMock()
        agent._wait_for_assertion_observation = AsyncMock()
        agent._bind_required_assertions_after_action = AsyncMock(side_effect=bind)
        agent._capture_screenshot = AsyncMock(return_value='recovered.png')
        agent._persist_step_attempt = AsyncMock(return_value={'assertion_statuses': ['passed']})
        agent._plan_ai_step_with_retries = AsyncMock()
        history = HistoryStub()

        result = asyncio.run(agent._retry_assertion_failure(
            SimpleNamespace(), step, 3, [{'action': 'click', 'selector': '#plus'}], ['inconclusive'], None, TimeoutError, history, None,
        ))

        self.assertEqual(result[0], 'completed')
        self.assertEqual(result[5], 'recovered.png')
        agent._plan_ai_step_with_retries.assert_not_awaited()
        self.assertEqual(history.artifacts[-1]['type'], 'rebind_recovery')

    def test_recovery_repeats_a_click_that_changed_nothing_then_tries_its_inner_activator(self) -> None:
        agent = PyUICompatAgent(case_name='Swallowed_Click', execution_record_id=7)
        agent._observable_baseline = {'#row-1', '#row-2'}
        agent._build_observable_elements = AsyncMock(return_value=[{'selector': '#row-1'}, {'selector': '#row-2'}])
        agent._rendered_visual_baseline = None
        agent._execute_step = AsyncMock()
        agent._wait_for_assertion_observation = AsyncMock()
        agent._bind_required_assertions_after_action = AsyncMock(return_value=False)
        inner = SimpleNamespace(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=True), click=AsyncMock())
        page = SimpleNamespace(wait_for_timeout=AsyncMock(), locator=Mock(return_value=SimpleNamespace(first=inner)))
        history = HistoryStub()
        step = {'assertions': [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'detail status control'}}]}
        click = {'action': 'click', 'selector': '#row-1'}

        self.assertIsNone(asyncio.run(agent._recover_by_rebinding(page, step, 3, [click], None, history, None)))

        agent._execute_step.assert_awaited_once()
        inner.click.assert_awaited_once()
        self.assertIn('#row-1 img', page.locator.call_args.args[0])
        self.assertEqual(history.artifacts[-1]['type'], 'swallowed_action_retry')
        self.assertEqual(history.artifacts[-1]['methods'], ['same_target', 'inner_activator'])
        self.assertIn('no visible change', agent._last_action_effect_note)

        asyncio.run(agent._recover_by_rebinding(page, step, 3, [click], None, history, None))
        agent._execute_step.assert_awaited_once()

    def test_action_effect_detection_uses_pre_action_baselines(self) -> None:
        agent = PyUICompatAgent(case_name='Effect')
        self.assertIsNone(asyncio.run(agent._action_had_visible_effect(SimpleNamespace())))

        agent._observable_baseline = {'#a'}
        agent._build_observable_elements = AsyncMock(return_value=[{'selector': '#a'}, {'selector': '#b'}])
        self.assertTrue(asyncio.run(agent._action_had_visible_effect(SimpleNamespace())))

        agent._build_observable_elements = AsyncMock(return_value=[{'selector': '#a'}])
        agent._rendered_visual_baseline = {'#img'}
        agent._rendered_visual_elements = AsyncMock(return_value=[{'selector': '#img'}])
        self.assertFalse(asyncio.run(agent._action_had_visible_effect(SimpleNamespace())))

    def test_rebind_recovery_is_skipped_for_media_contracts_and_unbound_assertions(self) -> None:
        agent = PyUICompatAgent(case_name='Rebind_Recovery', execution_record_id=7)
        agent._wait_for_assertion_observation = AsyncMock()
        agent._bind_required_assertions_after_action = AsyncMock(return_value=False)
        agent._persist_step_attempt = AsyncMock()

        playback_step = {'assertions': [{'assert_kind': 'playback', 'operator': 'greater_than', 'expected': {'minimum_advanced_seconds': 10}, 'target': {'intent': 'player'}}]}
        self.assertIsNone(asyncio.run(agent._recover_by_rebinding(SimpleNamespace(), playback_step, 1, [{'action': 'click'}], None, HistoryStub(), None)))

        unbound_step = {'assertions': [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'form'}}]}
        self.assertIsNone(asyncio.run(agent._recover_by_rebinding(SimpleNamespace(), unbound_step, 1, [{'action': 'click'}], None, HistoryStub(), None)))
        agent._persist_step_attempt.assert_not_awaited()

    def test_collection_binder_picks_the_largest_fresh_repeated_group(self) -> None:
        agent = PyUICompatAgent(case_name='Collection_Binder')
        assertion = {'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'case list items shown on the Case page'}}
        step = {'assertions': [assertion]}
        agent._observable_baseline = {'#nav-home', '#nav-cases'}
        agent._build_observable_elements = AsyncMock(return_value=[
            {'selector': '#root > div:nth-of-type(2) > div:nth-of-type(1)', 'group_selector': '#root > div:nth-of-type(2) > div.case-row', 'group_size': 5, 'text': '13952 Investigate', 'rect': {'x': 100, 'y': 100, 'width': 380, 'height': 120}},
            {'selector': '#root > div:nth-of-type(2) > div:nth-of-type(2)', 'group_selector': '#root > div:nth-of-type(2) > div.case-row', 'group_size': 5, 'text': '13951 Close', 'rect': {'x': 100, 'y': 220, 'width': 380, 'height': 120}},
            {'selector': '#root > div:nth-of-type(3) > span:nth-of-type(1)', 'group_selector': '#root > div:nth-of-type(3) > span.tag', 'group_size': 2, 'text': 'Filter', 'rect': {'x': 600, 'y': 20, 'width': 60, 'height': 20}},
        ])
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'selector': '#nav-cases', 'group_selector': 'body > nav > a.item', 'group_size': 6, 'name': 'Cases', 'rect': {'x': 24, 'y': 226, 'width': 46, 'height': 46}},
        ])

        bindings = asyncio.run(agent._collection_binding_from_completed_action(object(), step, [assertion], {'action': 'click', 'selector': '#nav-cases'}))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '#root > div:nth-of-type(2) > div.case-row'}])

        agent._observable_baseline = None
        self.assertEqual(asyncio.run(agent._collection_binding_from_completed_action(object(), step, [assertion], {'action': 'click'})), [])

    def test_inherited_collection_binder_reuses_verified_group_after_read_only_action(self) -> None:
        agent = PyUICompatAgent(case_name='Inherited_Collection_Binder')
        camera_group = '#root > div:nth-of-type(4) > div.cursor-grab'
        assertion = {'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'online camera entries in the site camera list'}}
        step = {'assertions': [assertion]}
        agent._binding_verified_predecessors = [
            {'step_num': 2, 'assertions': [{'assert_kind': 'collection', 'operator': 'greater_than', 'target': {'intent': 'site search result rows matching the target site', 'locator': '#sites > div.site-item'}}]},
            {'step_num': 3, 'assertions': [{'assert_kind': 'collection', 'operator': 'greater_than', 'target': {'intent': 'camera items listed for the selected site', 'locator': camera_group}}]},
        ]
        agent._build_observable_elements = AsyncMock(return_value=[
            {'selector': '#root > div:nth-of-type(4) > div:nth-of-type(1)', 'group_selector': camera_group, 'group_size': 6, 'text': 'Camera 13'},
            {'selector': '#sites > div:nth-of-type(1)', 'group_selector': '#sites > div.site-item', 'group_size': 1, 'text': 'Site A'},
        ])
        agent._build_actionable_controls = AsyncMock(return_value=[])

        bindings = asyncio.run(agent._inherited_collection_binding_from_read_only_action(object(), step, [assertion], {'action': 'wait', 'seconds': 20}))
        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': camera_group}])

        # A click introduces its own content; the fresh-group binder owns that case.
        self.assertEqual(asyncio.run(agent._inherited_collection_binding_from_read_only_action(object(), step, [assertion], {'action': 'click', 'selector': '#tab'})), [])
        # Without a verified predecessor collection there is nothing to inherit.
        agent._binding_verified_predecessors = []
        self.assertEqual(asyncio.run(agent._inherited_collection_binding_from_read_only_action(object(), step, [assertion], {'action': 'wait'})), [])

    def test_observable_baseline_is_captured_for_unbound_collection_assertions(self) -> None:
        agent = PyUICompatAgent(case_name='Collection_Baseline')
        agent._build_observable_elements = AsyncMock(return_value=[{'selector': '#a'}])
        step = {'assertions': [{'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'rows'}}]}

        self.assertEqual(asyncio.run(agent._capture_observable_baseline(object(), step)), {'#a'})
        bound_step = {'assertions': [{'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'target': {'intent': 'rows', 'locator': '#rows > li'}}]}
        self.assertIsNone(asyncio.run(agent._capture_observable_baseline(object(), bound_step)))

    def test_click_recovers_drifted_selector_from_observed_geometry(self) -> None:
        agent = PyUICompatAgent(case_name='Geometry_Recovery')
        agent._last_actionable_controls = [{'selector': 'body > div:nth-of-type(2) > button:nth-of-type(16)', 'rect': {'x': 800, 'y': 860, 'width': 40, 'height': 30}}]
        agent._resolve_locator = AsyncMock(return_value=None)
        page = SimpleNamespace(
            mouse=SimpleNamespace(move=AsyncMock(), click=AsyncMock()),
            wait_for_timeout=AsyncMock(),
            evaluate=AsyncMock(return_value={'tag': 'button', 'x': 820.0, 'y': 875.0, 'name': ''}),
        )

        target = asyncio.run(agent._recover_control_by_observed_geometry(page, 'body > div:nth-of-type(2) > button:nth-of-type(16)'))

        self.assertIsNotNone(target)
        page.mouse.move.assert_awaited_once_with(820.0, 875.0)
        asyncio.run(target.click(timeout=1000))
        page.mouse.click.assert_awaited_once_with(820.0, 875.0)
        self.assertEqual(agent._runtime_events[-1]['method'], 'element_at_observed_position')

        self.assertIsNone(asyncio.run(agent._recover_control_by_observed_geometry(page, '#never-observed')))

    def test_click_recovery_prefers_hover_revealed_selector(self) -> None:
        agent = PyUICompatAgent(case_name='Geometry_Recovery')
        agent._last_actionable_controls = [{'selector': '#toolbar-close', 'rect': {'x': 10, 'y': 10, 'width': 20, 'height': 20}}]
        revealed = SimpleNamespace(click=AsyncMock())
        agent._resolve_locator = AsyncMock(return_value=revealed)
        page = SimpleNamespace(mouse=SimpleNamespace(move=AsyncMock(), click=AsyncMock()), wait_for_timeout=AsyncMock(), evaluate=AsyncMock())

        target = asyncio.run(agent._recover_control_by_observed_geometry(page, '#toolbar-close'))

        self.assertIs(target, revealed)
        page.evaluate.assert_not_awaited()
        self.assertEqual(agent._runtime_events[-1]['method'], 'hover_reveal')

    def test_assertion_retry_accumulates_prior_action_history(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._retry_assertion_failure)

        self.assertIn('_persisted_step_action_history', source)
        self.assertIn("'_prior_actions': prior_actions[-16:]", source)
        self.assertIn("'_verified_predecessors'", source)

    def test_visual_planning_collects_page_scroll_metrics(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._collect_planner_observation)

        self.assertIn('scroll_height', source)
        self.assertIn('scroll_containers', source)
        self.assertIn('element.scrollHeight > element.clientHeight + 1', source)
        self.assertIn('item.client_height * 0.8 >= 2', source)
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
            assertion_statuses=['inconclusive'],
        )

        self.assertTrue(should_retry)

    def test_verifying_model_step_retries_failed_assertion(self) -> None:
        should_retry = PyUICompatAgent._should_retry_assertions(
            {'verification_required': True},
            action_completed=True,
            assertions_verified=False,
            action_source='model',
            assertion_statuses=['failed'],
        )

        self.assertTrue(should_retry)

    def test_verifying_reused_step_retries_unverified_assertions(self) -> None:
        for action_source in ('cache', 'experience'):
            with self.subTest(action_source=action_source):
                should_retry = PyUICompatAgent._should_retry_assertions(
                    {'verification_required': True},
                    action_completed=True,
                    assertions_verified=False,
                    action_source=action_source,
                    assertion_statuses=['inconclusive'],
                )

                self.assertTrue(should_retry)

    def test_invalidating_reused_actions_uses_the_matching_store(self) -> None:
        agent = PyUICompatAgent(case_name='Invalid_Reused_Action')
        step = {'description': 'Perform the requested operation'}
        agent._delete_cached_ai_actions = AsyncMock()
        agent._invalidate_verified_experience = AsyncMock()

        asyncio.run(agent._invalidate_reused_actions(step, 'cache'))

        agent._delete_cached_ai_actions.assert_awaited_once_with(step)
        agent._invalidate_verified_experience.assert_not_awaited()

        agent._delete_cached_ai_actions.reset_mock()
        asyncio.run(agent._invalidate_reused_actions(step, 'experience'))

        agent._delete_cached_ai_actions.assert_not_awaited()
        agent._invalidate_verified_experience.assert_awaited_once_with(step)

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

    def test_resolve_locator_skips_hidden_matches(self) -> None:
        agent = PyUICompatAgent(case_name='Locator_Visibility')
        page = _VisibleResolveLocatorPageStub()

        locator = asyncio.run(agent._resolve_locator(page, 'text=Cameras'))

        self.assertIs(locator, page.css_locator.nth(1))

    def test_resolve_step_locator_prefers_unique_accessible_role_and_name(self) -> None:
        page = _RoleLocatorPageStub([False, True])

        locator = asyncio.run(PyUICompatAgent()._resolve_step_locator(page, {
            'role': 'button',
            'accessible_name': 'Settings',
            'selector': '#fallback',
        }))

        self.assertIs(locator, page.locator_result.nth(1))
        self.assertEqual(page.call, ('button', 'Settings', True))

    def test_resolve_step_locator_rejects_ambiguous_accessible_match(self) -> None:
        page = _RoleLocatorPageStub([True, True])

        with self.assertRaisesRegex(ValueError, 'matched 2 visible elements'):
            asyncio.run(PyUICompatAgent()._resolve_step_locator(page, {
                'role': 'button',
                'accessible_name': 'Save',
            }))

    def test_planned_action_accepts_accessible_locator_without_css(self) -> None:
        PyUICompatAgent._validate_planned_actions(
            [{'action': 'click', 'role': 'button', 'accessible_name': 'Settings'}],
            allowed_capabilities=['browser.act'],
        )

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

        step = agent._normalize_step({
            'executor': 'browser',
            'description': 'Verify state',
            'assertions': assertions,
            'correlates_resource': 'alert_event',
        }, 1)

        self.assertEqual(step['assertions'], assertions)
        self.assertEqual(step['correlates_resource'], 'alert_event')

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
        create_plan = AsyncMock(return_value=[
            {
                'executor': 'device_cli',
                'description': '连接设备',
                'device_id': 'ainvr_5000',
            },
        ])
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
            new=create_plan,
        ):
            history = asyncio.run(
                agent.run_full_process(
                    '连接设备并验证可用性',
                    case_mode='freeform',
                    task_steps=[{
                        'description': "在搜索框中输入 'black hair'",
                        'selector': '#legacy-search',
                    }],
                )
            )

        planning_goal = create_plan.await_args.args[0]
        self.assertIn('连接设备并验证可用性', planning_goal)
        self.assertIn("在搜索框中输入 'black hair'", planning_goal)
        self.assertNotIn('#legacy-search', planning_goal)
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

    def test_cache_key_and_experience_contract_survive_assertion_binding(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004', ai_project_id=1, execution_user_id=1)
        step = {
            'index': 4,
            'description': 'Open the camera list',
            'assertions': [{
                'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0},
                'target': {'intent': 'camera items listed for the selected site'},
            }],
        }
        context = {'fingerprint': 'page-a', 'application_version': ''}
        lookup_key = agent._cache_key_for_step(step, context)
        lookup_hash = agent._assertion_contract_hash(step)

        bound = PyUICompatAgent._bind_step_assertions(step, [{'assertion_index': 1, 'locator': '#root > div:nth-of-type(4) > div.cursor-grab'}])
        self.assertEqual(bound['assertions'][0]['target']['locator'], '#root > div:nth-of-type(4) > div.cursor-grab')

        self.assertEqual(agent._cache_key_for_step(bound, context), lookup_key)
        self.assertEqual(agent._assertion_contract_hash(bound), lookup_hash)
        # A genuinely different contract still yields a different key.
        other = {**step, 'assertions': [{**step['assertions'][0], 'operator': 'equals'}]}
        self.assertNotEqual(agent._cache_key_for_step(other, context), lookup_key)

    def test_store_uses_the_key_remembered_at_lookup_time(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004', ai_project_id=1, execution_user_id=1)
        step = {'index': 2, 'description': 'Open the panel', 'assertions': []}
        context = {'fingerprint': 'page-a'}
        agent._cache_key_by_step[agent._step_context_key(step)] = 'v6::remembered'
        self.assertEqual(agent._resolved_cache_key(step, context), 'v6::remembered')
        agent._cache_key_by_step.clear()
        self.assertEqual(agent._resolved_cache_key(step, context), agent._cache_key_for_step(step, context))

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

    def test_request_payload_includes_response_format_when_present(self) -> None:
        config = type('ConfigStub', (), {'model_name': 'demo', 'temperature': 0.1, 'top_p': 0.2, 'model_type': 'qwen'})()

        data = OpenAICompatibleClient.build_request_payload(
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
        history.steps = [{
            'step_num': 1,
            'step_description': 'Locate the requested item',
            'action': 'assert',
            'executor': 'browser',
            'assertions': [{
                'assert_kind': 'element_state',
                'target': {'intent': 'requested item', 'locator': '#item-7 img'},
            }],
            'result': True,
        }]
        agent._build_page_context = AsyncMock(return_value={'url': 'https://example.test'})
        agent._load_cached_ai_actions = AsyncMock(return_value=None)
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
        planning_step = agent._plan_ai_step_for_cacheable_step.await_args.args[1]
        self.assertEqual(
            planning_step['_verified_predecessors'][0]['assertions'][0]['target']['locator'],
            '#item-7 img',
        )

    def test_replan_replaces_failed_action_with_new_action(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')
        history = HistoryStub()
        step = {
            'description': 'Perform the requested operation',
            'allowed_capabilities': ['browser.act'],
        }
        agent._execute_step = AsyncMock(side_effect=[ValueError('stale target'), None])
        agent._plan_ai_step_with_retries = AsyncMock(return_value=[{'action': 'assert'}])

        asyncio.run(agent._execute_ai_actions(object(), step, [{'action': 'click'}], 1, None, TimeoutError, history=history))

        self.assertEqual(agent._execute_step.await_count, 1)
        replan_artifact = next(artifact for artifact in history.artifacts if artifact['type'] == 'ai_replan')
        self.assertEqual(replan_artifact['failed_action'], {'action': 'click'})

    def test_assertion_failure_replans_and_rechecks_evidence(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004', execution_record_id=7)
        history = HistoryStub()
        history.steps = [{
            'step_num': 1,
            'step_description': 'Open the record',
            'action': 'click',
            'executor': 'browser',
            'assertions': [{
                'assert_kind': 'element_state',
                'target': {'intent': 'selected record', 'locator': '#record-7'},
            }],
            'result': True,
        }]
        step = {'description': 'Verify requested state', 'assertions': [{'action': 'assert'}]}
        agent._plan_ai_step_with_retries = AsyncMock(return_value=[{'action': 'click', 'selector': '#retry'}])
        agent._persisted_step_action_history = Mock(return_value=[])
        agent._execute_ai_actions = AsyncMock()
        agent._capture_media_state = AsyncMock(return_value=[])
        agent._capture_screenshot = AsyncMock(return_value='retry.png')
        agent._persist_step_attempt = AsyncMock(return_value={'assertion_statuses': ['passed']})
        page = SimpleNamespace(wait_for_timeout=AsyncMock())

        with patch('apps.ai_testing.execution.plan_persistence.persist_replanned_step') as persist_replanned_step:
            result = asyncio.run(agent._retry_assertion_failure(
                page, step, 1, [{'action': 'click', 'selector': '#initial'}], ['failed'],
                None, TimeoutError, history, None,
            ))

        self.assertEqual(result[0], 'completed')
        persist_replanned_step.assert_called_once()
        agent._execute_ai_actions.assert_awaited_once()
        self.assertEqual(agent._persist_step_attempt.await_args.args[3], 'completed')
        replanning_step = agent._plan_ai_step_with_retries.await_args.args[1]
        self.assertEqual(replanning_step['description'].splitlines()[0], 'Verify requested state')
        self.assertEqual(replanning_step['_verified_predecessors'], [{
            'step_num': 1,
            'description': 'Open the record',
            'action': 'click',
            'executor': 'browser',
            'assertions': [{
                'assert_kind': 'element_state',
                'target': {'intent': 'selected record', 'locator': '#record-7'},
            }],
        }])

    def test_initial_ai_action_persists_assertion_bindings(self) -> None:
        agent = PyUICompatAgent(case_name='Initial_Binding', execution_record_id=7)
        step = {
            'assertions': [{
                'assert_kind': 'element_state',
                'target': {'intent': 'home page content'},
            }],
        }
        actions = [{
            'action': 'assert',
            'assertion_bindings': [{'assertion_index': 1, 'locator': '#home'}],
        }]

        with patch('apps.ai_testing.execution.plan_persistence.persist_bound_step') as persist_bound_step:
            asyncio.run(agent._apply_assertion_bindings(1, step, actions))

        persist_bound_step.assert_called_once_with(
            7,
            1,
            [{'assertion_index': 1, 'locator': '#home'}],
        )
        self.assertEqual(step['assertions'][0]['target']['locator'], '#home')

    def test_post_action_binding_uses_assert_only_planning(self) -> None:
        agent = PyUICompatAgent(case_name='Post_Action_Binding', execution_record_id=7)
        history = HistoryStub()
        step = {
            'description': 'Open the requested menu',
            'allowed_capabilities': ['browser.act', 'browser.inspect'],
            'assertions': [{
                'assert_kind': 'element_state',
                'required': True,
                'target': {'intent': 'requested menu option'},
            }],
        }
        agent._plan_ai_step_with_retries = AsyncMock(return_value=[{
            'action': 'assert',
            'assertion_bindings': [{'assertion_index': 1, 'locator': '#menu-option'}],
        }])

        with patch('apps.ai_testing.execution.plan_persistence.persist_bound_step') as persist_bound_step:
            bound = asyncio.run(agent._bind_required_assertions_after_action(
                object(), step, 1, [{'action': 'click', 'selector': '#menu'}], None, history,
            ))

        binding_step = agent._plan_ai_step_with_retries.await_args.args[1]
        self.assertTrue(bound)
        self.assertEqual(binding_step['allowed_capabilities'], ['browser.inspect'])
        self.assertEqual(binding_step['_prior_actions'][0]['action'], 'click')
        self.assertEqual(binding_step['_prior_actions'][0]['selector'], '#menu')
        self.assertEqual(binding_step['_prior_actions'][0]['status'], 'completed')
        self.assertEqual(step['assertions'][0]['target']['locator'], '#menu-option')
        persist_bound_step.assert_called_once()

    def test_post_action_binding_uses_unique_completed_field_value(self) -> None:
        agent = PyUICompatAgent(case_name='Field_Value_Binding', execution_record_id=7)
        history = HistoryStub()
        step = {
            'description': 'Fill the requested search value',
            'assertions': [{
                'assert_kind': 'field_value',
                'operator': 'equals',
                'expected': {'value': 'black hair'},
                'required': True,
                'target': {'intent': 'search input'},
            }],
        }
        agent._build_observable_elements = AsyncMock(return_value=[
            {'tag': 'input', 'text': 'black hair', 'selector': '#search'},
            {'tag': 'button', 'text': 'black hair', 'selector': '#label'},
        ])
        agent._plan_ai_step_with_retries = AsyncMock()

        with patch('apps.ai_testing.execution.plan_persistence.persist_bound_step') as persist_bound_step:
            bound = asyncio.run(agent._bind_required_assertions_after_action(
                object(), step, 1, [{'action': 'fill', 'selector': '#search', 'value': 'black hair'}], None, history,
            ))

        self.assertTrue(bound)
        self.assertEqual(step['assertions'][0]['target']['locator'], '#search')
        agent._plan_ai_step_with_retries.assert_not_awaited()
        persist_bound_step.assert_called_once_with(
            7,
            1,
            [{'assertion_index': 1, 'locator': '#search'}],
        )

    def test_post_click_binding_uses_unique_named_top_layer_element(self) -> None:
        agent = PyUICompatAgent(case_name='Element_State_Binding', execution_record_id=7)
        history = HistoryStub()
        step = {
            'description': 'Open the requested menu',
            'assertions': [{
                'assert_kind': 'element_state',
                'operator': 'exists',
                'expected': {'value': True},
                'required': True,
                'target': {'intent': 'requested item option in the open dropdown'},
            }],
        }
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': 'requested item details', 'selector': 'body > div > div', 'top_layer': True},
            {'name': 'requested item details', 'selector': '[title="requested item details"]', 'top_layer': True},
            {'name': 'requested item details', 'selector': '#background-item', 'top_layer': False},
        ])
        agent._plan_ai_step_with_retries = AsyncMock()

        with patch('apps.ai_testing.execution.plan_persistence.persist_bound_step') as persist_bound_step:
            bound = asyncio.run(agent._bind_required_assertions_after_action(
                object(), step, 1, [{'action': 'click', 'selector': '#menu'}], None, history,
            ))

        self.assertTrue(bound)
        self.assertEqual(step['assertions'][0]['target']['locator'], 'body > div > div')
        agent._plan_ai_step_with_retries.assert_not_awaited()
        persist_bound_step.assert_called_once()

    def test_post_click_binding_falls_back_for_ambiguous_named_elements(self) -> None:
        agent = PyUICompatAgent(case_name='Ambiguous_Element_Binding')
        step = {
            'assertions': [{
                'assert_kind': 'element_state',
                'operator': 'exists',
                'expected': {'value': True},
                'required': True,
                'target': {'intent': 'requested item option'},
            }],
        }
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': 'requested item primary', 'selector': '#primary', 'top_layer': True},
            {'name': 'requested item secondary', 'selector': '#secondary', 'top_layer': True},
        ])

        bindings = asyncio.run(agent._visible_element_binding_from_completed_click(
            object(), step, step['assertions'], {'action': 'click'},
        ))

        self.assertEqual(bindings, [])

    def test_post_click_binding_uses_multilingual_target_text(self) -> None:
        agent = PyUICompatAgent(case_name='Multilingual_Element_Binding')
        assertion = {
            'assert_kind': 'element_state',
            'operator': 'exists',
            'expected': {'value': True},
            'required': True,
            'target': {'intent': '目标角色选项', 'text': '站点管理员'},
        }
        step = {'assertions': [assertion]}
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': '站点管理员（可管理指定站点）', 'selector': '#site-manager', 'top_layer': True},
            {'name': '组织管理员（可管理所有站点）', 'selector': '#org-admin', 'top_layer': True},
        ])

        bindings = asyncio.run(agent._visible_element_binding_from_completed_click(
            object(), step, [assertion], {'action': 'click'},
        ))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '#site-manager'}])

    def test_intent_value_binding_binds_the_anchored_control_showing_the_named_text(self) -> None:
        agent = PyUICompatAgent(case_name='Intent_Value_Binding')
        assertion = {
            'assert_kind': 'element_state',
            'operator': 'exists',
            'expected': {'value': True},
            'required': True,
            'target': {'intent': 'monitoring view status control showing To Do'},
        }
        step = {'assertions': [assertion]}
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': '2296 To Do', 'selector': '#root > div:nth-of-type(1) > button:nth-of-type(1)'},
            {'name': 'To Do', 'selector': '[title="To Do"]'},
        ])
        agent._build_observable_elements = AsyncMock(return_value=[
            {'text': 'To Do', 'selector': '#root > div:nth-of-type(2) > div:nth-of-type(1) > p:nth-of-type(1)'},
            {'text': 'To Do', 'selector': '#root > div:nth-of-type(2) > div:nth-of-type(2) > p:nth-of-type(1)'},
        ])

        bindings = asyncio.run(agent._intent_value_binding_from_completed_action(
            object(), step, [assertion], {'action': 'click', 'selector': '#row-1'},
        ))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '[title="To Do"]'}])
        self.assertEqual(agent._runtime_events[-1]['type'], 'intent_value_binding')

    def test_intent_value_binding_binds_the_committed_value_display_after_choosing_an_option(self) -> None:
        agent = PyUICompatAgent(case_name='Intent_Value_Contains')
        assertion = {
            'assert_kind': 'element_state', 'operator': 'contains', 'expected': {'value': 'Close'}, 'required': True,
            'target': {'intent': 'status control displaying the selected value'},
        }
        step = {'assertions': [assertion]}
        close_rect = {'x': 1700, 'y': 20, 'width': 24, 'height': 24}
        # Planning-time snapshot: the status control still showed "To Do" and a "close" icon button already existed.
        agent._last_actionable_controls = [
            {'selector': '[title="To Do"]', 'name': 'To Do', 'rect': {'x': 520, 'y': 819, 'width': 104, 'height': 30}},
            {'selector': '[aria-label="close"]', 'name': 'close', 'rect': close_rect},
        ]
        # The open menu's "Close" option shared the display's attribute selector but sat elsewhere.
        agent._pre_action_control_names = {
            ((520, 819, 104, 30), 'To Do'), ((1700, 20, 24, 24), 'close'), ((530, 640, 100, 30), 'Close'),
        }
        option = {'name': 'Close', 'selector': '[title="Close"]', 'role': 'option', 'top_layer': True, 'group_size': 3, 'rect': {'x': 530, 'y': 640, 'width': 100, 'height': 30}}
        close_button = {'name': 'close', 'selector': '[aria-label="close"]', 'tag': 'button', 'role': 'button', 'rect': close_rect}
        close_button_observable = {'text': 'close', 'selector': '#root > div:nth-of-type(1) > button:nth-of-type(3)', 'tag': 'button', 'rect': close_rect}
        display = {'name': 'Close', 'selector': '[title="Close"]', 'tag': 'span', 'role': '', 'top_layer': False, 'group_size': 1, 'rect': {'x': 520, 'y': 819, 'width': 104, 'height': 30}}
        page = SimpleNamespace(wait_for_timeout=AsyncMock())

        agent._build_actionable_controls = AsyncMock(return_value=[option, close_button, display])
        agent._build_observable_elements = AsyncMock(return_value=[close_button_observable])
        bindings = asyncio.run(agent._intent_value_binding_from_completed_action(
            page, step, [assertion], {'action': 'click', 'selector': option['selector']},
        ))
        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '[title="Close"]'}])

        # Display not refreshed yet: only pre-existing "close" elements match, so the binder polls and declines.
        agent._build_actionable_controls = AsyncMock(return_value=[close_button, {'name': 'To Do', 'selector': '[title="To Do"]', 'tag': 'span'}])
        agent._build_observable_elements = AsyncMock(return_value=[close_button_observable])
        self.assertEqual(asyncio.run(agent._intent_value_binding_from_completed_action(
            page, step, [assertion], {'action': 'click', 'selector': option['selector']},
        )), [])
        self.assertEqual(page.wait_for_timeout.await_count, 6)

        # A new element whose text only matches case-insensitively is not the committed value either.
        agent._build_actionable_controls = AsyncMock(return_value=[{'name': 'close', 'selector': '#new-close', 'tag': 'span', 'rect': {'x': 1, 'y': 1, 'width': 10, 'height': 10}}])
        agent._build_observable_elements = AsyncMock(return_value=[])
        self.assertEqual(asyncio.run(agent._intent_value_binding_from_completed_action(
            page, step, [assertion], {'action': 'click'},
        )), [])

        numeric = {**assertion, 'operator': 'equals', 'expected': {'value': 3}}
        self.assertEqual(asyncio.run(agent._intent_value_binding_from_completed_action(
            page, {'assertions': [numeric]}, [numeric], {'action': 'click'},
        )), [])

    def test_intent_value_binding_declines_without_a_named_value_or_with_ambiguity(self) -> None:
        agent = PyUICompatAgent(case_name='Intent_Value_Binding_Declines')
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': 'To Do', 'selector': '[title="To Do"]'},
            {'name': 'To Do', 'selector': '#status-chip'},
        ])
        agent._build_observable_elements = AsyncMock(return_value=[])
        make = lambda intent, **extra: {
            'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'required': True,
            'target': {'intent': intent, **extra},
        }

        vague = make('monitoring detail panel')
        self.assertEqual(asyncio.run(agent._intent_value_binding_from_completed_action(
            object(), {'assertions': [vague]}, [vague], {'action': 'click'},
        )), [])
        ambiguous = make('status control showing To Do')
        self.assertEqual(asyncio.run(agent._intent_value_binding_from_completed_action(
            object(), {'assertions': [ambiguous]}, [ambiguous], {'action': 'click'},
        )), [])
        image = make('thumbnail showing To Do', visual_content='image')
        self.assertEqual(asyncio.run(agent._intent_value_binding_from_completed_action(
            object(), {'assertions': [image]}, [image], {'action': 'click'},
        )), [])
        self.assertEqual(asyncio.run(agent._intent_value_binding_from_completed_action(
            object(), {'assertions': [ambiguous]}, [ambiguous], {'action': 'assert'},
        )), [])

    def test_vanished_media_binder_binds_the_player_the_close_action_removed(self) -> None:
        agent = PyUICompatAgent(case_name='Vanished_Media')
        assertion = {
            'assert_kind': 'element_state', 'operator': 'not_exists', 'expected': {'value': True}, 'required': True,
            'target': {'intent': 'live video stream player for the opened camera'},
        }
        step = {'assertions': [assertion]}
        self.assertEqual(agent._vanishing_media_assertions(step), [assertion])
        agent._rendered_visual_elements = AsyncMock(side_effect=[
            [{'selector': '#canvas_streaming_2630', 'area': 640000}, {'selector': '#root > div:nth-of-type(1) > img:nth-of-type(1)', 'area': 9000}],
            [{'selector': '#root > div:nth-of-type(1) > img:nth-of-type(1)', 'area': 9000}],
        ])
        page = SimpleNamespace(wait_for_timeout=AsyncMock())

        baseline = asyncio.run(agent._capture_rendered_visual_baseline(page, step))
        self.assertEqual(baseline, {'#canvas_streaming_2630', '#root > div:nth-of-type(1) > img:nth-of-type(1)'})

        bindings = asyncio.run(agent._vanished_media_binding_from_completed_action(
            page, step, [assertion], {'action': 'click', 'selector': '#toolbar > button:nth-of-type(14)'},
        ))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '#canvas_streaming_2630'}])

    def test_vanished_media_binder_declines_when_nothing_disappeared_or_intent_is_not_media(self) -> None:
        agent = PyUICompatAgent(case_name='Vanished_Media_Declines')
        media = {
            'assert_kind': 'element_state', 'operator': 'not_exists', 'expected': {'value': True}, 'required': True,
            'target': {'intent': 'live video stream player'},
        }
        agent._rendered_visual_baseline_elements = {'#canvas_streaming_1': {'selector': '#canvas_streaming_1', 'area': 640000}}
        agent._rendered_visual_elements = AsyncMock(return_value=[{'selector': '#canvas_streaming_1', 'area': 640000}])
        page = SimpleNamespace(wait_for_timeout=AsyncMock())

        self.assertEqual(asyncio.run(agent._vanished_media_binding_from_completed_action(
            page, {'assertions': [media]}, [media], {'action': 'click'},
        )), [])
        self.assertEqual(agent._runtime_events[-1]['binder'], 'vanished_media')
        self.assertEqual(page.wait_for_timeout.await_count, 8)

        text_only = {**media, 'target': {'intent': 'success banner'}}
        self.assertEqual(agent._vanishing_media_assertions({'assertions': [text_only]}), [])
        self.assertEqual(asyncio.run(agent._vanished_media_binding_from_completed_action(
            page, {'assertions': [text_only]}, [text_only], {'action': 'click'},
        )), [])

    def test_fresh_content_binder_binds_a_mismatching_dialog_but_records_a_warning(self) -> None:
        agent = PyUICompatAgent(case_name='Fresh_Content_Popup_Warning')
        popup = {
            'assert_kind': 'popup', 'operator': 'exists', 'expected': {'value': True}, 'required': True,
            'target': {'intent': 'reason selection dialog opened after choosing Investigate'},
        }
        step = {'assertions': [popup]}
        agent._observable_baseline = {'#old'}
        agent._build_observable_elements = AsyncMock(return_value=[
            {'selector': 'body > div:nth-of-type(3)', 'text': 'Arson Brawling BreakIn Other Cancel Confirm', 'rect': {'x': 0, 'y': 0, 'width': 900, 'height': 600}},
            {'selector': 'body > div:nth-of-type(3) > button:nth-of-type(1)', 'text': 'Arson', 'rect': {'x': 0, 'y': 0, 'width': 120, 'height': 30}},
            {'selector': 'body > div:nth-of-type(3) > button:nth-of-type(2)', 'text': 'Confirm', 'rect': {'x': 0, 'y': 0, 'width': 80, 'height': 30}},
        ])

        bindings = asyncio.run(agent._fresh_content_binding_from_completed_action(object(), step, [popup], {'action': 'click'}))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': 'body > div:nth-of-type(3)'}])
        self.assertEqual(agent._runtime_events[-1]['type'], 'popup_intent_warning')

    def test_action_effect_detection_sees_a_text_change_at_the_same_position(self) -> None:
        agent = PyUICompatAgent(case_name='Text_Change_Effect')
        agent._pre_action_control_names = {((520, 819, 104, 30), 'To Do'), ((10, 10, 40, 40), 'Home')}
        agent._observable_baseline = {'#a'}
        agent._build_observable_elements = AsyncMock(return_value=[{'selector': '#a'}])
        page = SimpleNamespace(url='')

        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': 'Close', 'rect': {'x': 520, 'y': 819, 'width': 104, 'height': 30}},
            {'name': 'Home', 'rect': {'x': 10, 'y': 10, 'width': 40, 'height': 40}},
        ])
        self.assertTrue(asyncio.run(agent._action_had_visible_effect(page)))

        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': 'To Do', 'rect': {'x': 520, 'y': 819, 'width': 104, 'height': 30}},
            {'name': 'Home', 'rect': {'x': 10, 'y': 10, 'width': 40, 'height': 40}},
        ])
        self.assertFalse(asyncio.run(agent._action_had_visible_effect(page)))

    def test_action_effect_detection_counts_a_row_of_revealed_controls(self) -> None:
        agent = PyUICompatAgent(case_name='Revealed_Controls_Effect')
        agent._pre_action_control_names = {((120, 160, 40, 40), 'Toggle collapse'), ((10, 10, 40, 40), 'Home')}
        agent._observable_baseline = None
        agent._rendered_visual_baseline = {'#map-img'}
        agent._rendered_visual_elements = AsyncMock(return_value=[{'selector': '#map-img'}])
        page = SimpleNamespace(url='')

        # The collapsed panel opened: the toggle is unchanged but a filter bar of new controls appeared below it.
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': 'Toggle collapse', 'rect': {'x': 120, 'y': 160, 'width': 40, 'height': 40}},
            {'name': 'Home', 'rect': {'x': 10, 'y': 10, 'width': 40, 'height': 40}},
            {'name': 'All time', 'rect': {'x': 330, 'y': 230, 'width': 60, 'height': 30}},
            {'name': '72 hours', 'rect': {'x': 400, 'y': 230, 'width': 60, 'height': 30}},
            {'name': 'Today', 'rect': {'x': 480, 'y': 230, 'width': 60, 'height': 30}},
        ])
        self.assertTrue(asyncio.run(agent._action_had_visible_effect(page)))

        # One stray control (a tooltip) is not evidence of an effect.
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': 'Toggle collapse', 'rect': {'x': 120, 'y': 160, 'width': 40, 'height': 40}},
            {'name': 'Home', 'rect': {'x': 10, 'y': 10, 'width': 40, 'height': 40}},
            {'name': 'Collapse results', 'rect': {'x': 130, 'y': 210, 'width': 100, 'height': 20}},
        ])
        self.assertFalse(asyncio.run(agent._action_had_visible_effect(page)))

    def test_toggle_controls_are_recognised_as_self_inverse(self) -> None:
        controls = [
            {'selector': '#panel-switch', 'role': 'switch', 'name': ''},
            {'selector': '#results-btn', 'role': 'button', 'name': 'Show results'},
            {'selector': '#chevron', 'role': 'button', 'name': 'Collapse panel'},
        ]
        self.assertTrue(PyUICompatAgent._control_toggles_state({'action': 'click', 'selector': '[aria-label="Toggle collapse"]'}, controls))
        self.assertTrue(PyUICompatAgent._control_toggles_state({'action': 'click', 'selector': '#panel-switch'}, controls))
        self.assertTrue(PyUICompatAgent._control_toggles_state({'action': 'click', 'selector': '#chevron'}, controls))
        self.assertTrue(PyUICompatAgent._control_toggles_state({'action': 'click', 'role': 'button', 'accessible_name': 'Expand sidebar'}, controls))
        self.assertFalse(PyUICompatAgent._control_toggles_state({'action': 'click', 'selector': '#results-btn'}, controls))
        self.assertFalse(PyUICompatAgent._control_toggles_state({'action': 'click', 'selector': '#row-1 img'}, None))

    def test_recovery_never_repeats_a_click_on_a_toggle_control(self) -> None:
        agent = PyUICompatAgent(case_name='Toggle_Not_Repeated', execution_record_id=7)
        agent._observable_baseline = {'#row-1'}
        agent._build_observable_elements = AsyncMock(return_value=[{'selector': '#row-1'}])
        agent._rendered_visual_baseline = None
        agent._execute_step = AsyncMock()
        agent._wait_for_assertion_observation = AsyncMock()
        agent._bind_required_assertions_after_action = AsyncMock(return_value=False)
        agent._last_actionable_controls = [{'selector': '[aria-label="Toggle collapse"]', 'role': 'button', 'name': 'Toggle collapse', 'rect': {'x': 1, 'y': 1, 'width': 2, 'height': 2}}]
        page = SimpleNamespace(wait_for_timeout=AsyncMock(), locator=Mock())
        history = HistoryStub()
        step = {'assertions': [{'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'preview image', 'visual_content': 'image'}}]}

        self.assertIsNone(asyncio.run(agent._recover_by_rebinding(page, step, 4, [{'action': 'click', 'selector': '[aria-label="Toggle collapse"]'}], None, history, None)))

        agent._execute_step.assert_not_awaited()
        self.assertFalse(any(artifact.get('type') == 'swallowed_action_retry' for artifact in history.artifacts))

    def test_replan_and_recovery_screenshots_keep_earlier_attempts(self) -> None:
        agent = PyUICompatAgent(case_name='Shot_Names')
        base = agent._step_screenshot_filename(4)
        self.assertTrue(base.endswith('_step_04.png'))
        self.assertEqual(agent._step_screenshot_filename(4, suffix='_r2'), base.replace('_step_04.png', '_step_04_r2.png'))
        source = inspect.getsource(PyUICompatAgent._retry_assertion_failure) + inspect.getsource(PyUICompatAgent._recover_by_rebinding)
        self.assertIn("suffix=f'_r{attempt}'", source)
        self.assertIn("suffix='_rebind'", source)

    def test_action_effect_detection_treats_a_url_change_as_visible(self) -> None:
        agent = PyUICompatAgent(case_name='Url_Change_Effect')
        agent._pre_action_url = 'https://app.example.com/dashboard/home'
        agent._observable_baseline = None
        agent._rendered_visual_baseline = None

        self.assertTrue(asyncio.run(agent._action_had_visible_effect(SimpleNamespace(url='https://app.example.com/dashboard/streaming'))))
        self.assertIsNone(asyncio.run(agent._action_had_visible_effect(SimpleNamespace(url='https://app.example.com/dashboard/home'))))

    def test_observation_skips_tooltip_probing_while_a_hover_menu_is_open(self) -> None:
        source = inspect.getsource(PyUICompatAgent._collect_planner_observation)

        self.assertIn("== 'hover'", source)
        self.assertIn('if not hover_state:', source)
        self.assertIn('_enrich_icon_control_names(page, actionable_controls)', source)

    def test_icon_toolbar_buttons_are_named_from_hover_tooltips_and_cached(self) -> None:
        agent = PyUICompatAgent(case_name='Tooltip_Names')
        parent = '#root > div:nth-of-type(1) > div:nth-of-type(3) > div:nth-of-type(1)'

        def button(position, x):
            return {'tag': 'button', 'role': 'button', 'name': '', 'selector': f'{parent} > button:nth-of-type({position})', 'rect': {'x': x, 'y': 740, 'width': 60, 'height': 60}}

        controls = [button(1, 546), button(2, 622), button(12, 1458), button(13, 1534), {'tag': 'a', 'name': 'Alerts', 'selector': '[href="/alerts"]', 'rect': {'x': 0, 'y': 0, 'width': 40, 'height': 40}}]
        probes = iter([
            {'described': '', 'texts': []},
            {'described': 'Pause', 'texts': ['Pause']},
            {'described': '', 'texts': ['Pause', '10s Backward']},
            {'described': 'Download', 'texts': ['Download']},
            {'described': 'Create Case', 'texts': ['Download', 'Create Case']},
        ])
        page = SimpleNamespace(
            url='https://app.example.com/dashboard/playback/2630',
            mouse=SimpleNamespace(move=AsyncMock()),
            wait_for_timeout=AsyncMock(),
            evaluate=AsyncMock(side_effect=lambda *args: next(probes)),
        )

        asyncio.run(agent._enrich_icon_control_names(page, controls))

        self.assertEqual([control['name'] for control in controls[:4]], ['Pause', '10s Backward', 'Download', 'Create Case'])
        self.assertEqual(controls[2]['name_source'], 'tooltip')
        self.assertEqual(controls[4]['name'], 'Alerts')
        self.assertEqual(page.mouse.move.await_count, 5)

        page.evaluate = AsyncMock(side_effect=AssertionError('cached names must not be probed again'))
        again = [button(1, 546), button(2, 622), button(12, 1458), button(13, 1534)]
        asyncio.run(agent._enrich_icon_control_names(page, again))
        self.assertEqual(again[2]['name'], 'Download')

    def test_tooltip_probe_is_skipped_behind_a_blocking_layer_or_without_a_toolbar(self) -> None:
        agent = PyUICompatAgent(case_name='Tooltip_Skip')
        page = SimpleNamespace(
            url='https://app.example.com/x',
            mouse=SimpleNamespace(move=AsyncMock()),
            wait_for_timeout=AsyncMock(),
            evaluate=AsyncMock(return_value={'described': '', 'texts': []}),
        )
        parent = '#root > div:nth-of-type(2)'
        toolbar = [
            {'tag': 'button', 'name': '', 'selector': f'{parent} > button:nth-of-type({position})', 'rect': {'x': 100 * position, 'y': 10, 'width': 60, 'height': 60}}
            for position in range(1, 4)
        ]
        dialog_button = {'tag': 'button', 'name': 'OK', 'selector': 'body > div:nth-of-type(3) > button:nth-of-type(1)', 'blocking_layer': True, 'rect': {'x': 0, 'y': 0, 'width': 60, 'height': 30}}

        asyncio.run(agent._enrich_icon_control_names(page, [*toolbar, dialog_button]))
        page.evaluate.assert_not_awaited()

        asyncio.run(agent._enrich_icon_control_names(page, toolbar[:2]))
        page.evaluate.assert_not_awaited()

    def test_environment_devices_are_seeded_as_execution_resources_once(self) -> None:
        configuration = SimpleNamespace(runtime_settings={'api': {'edge': {'main_device': {'device_id': 'nvr_5003', 'cameras': [{'camera_name': '5003_D13'}]}}}})
        agent = PyUICompatAgent(case_name='Device_Resources', environment_configuration=configuration)

        agent._seed_environment_resources()
        agent._seed_environment_resources()

        self.assertEqual(len(agent._execution_resources), 1)
        self.assertEqual(agent._execution_resources[0]['resource']['camera_names'], ['5003_D13'])

    def test_click_target_moved_detects_a_value_selector_that_now_points_elsewhere(self) -> None:
        agent = PyUICompatAgent(case_name='Click_Target_Moved')
        agent._last_click_box = {'x': 530, 'y': 640, 'width': 100, 'height': 30}

        def page_with_box(box, count=1):
            locator = SimpleNamespace(count=AsyncMock(return_value=count), bounding_box=AsyncMock(return_value=box))
            return SimpleNamespace(locator=Mock(return_value=SimpleNamespace(first=locator)))

        self.assertTrue(asyncio.run(agent._click_target_moved(page_with_box({'x': 520, 'y': 819, 'width': 104, 'height': 30}), {'action': 'click', 'selector': '[title="Close"]'})))
        self.assertTrue(asyncio.run(agent._click_target_moved(page_with_box(None, count=0), {'action': 'click', 'selector': '[title="Close"]'})))
        self.assertFalse(asyncio.run(agent._click_target_moved(page_with_box({'x': 530, 'y': 640, 'width': 100, 'height': 30}), {'action': 'click', 'selector': '[title="Close"]'})))
        agent._last_click_box = None
        self.assertFalse(asyncio.run(agent._click_target_moved(page_with_box({'x': 1, 'y': 1, 'width': 1, 'height': 1}), {'action': 'click', 'selector': '[title="Close"]'})))

    def test_selected_value_binder_waits_for_the_display_and_ignores_unchanged_controls(self) -> None:
        agent = PyUICompatAgent(case_name='Selected_Value_Poll')
        assertion = {'assert_kind': 'field_value', 'operator': 'starts_with', 'expected': {'value': 'Close'}, 'required': True, 'target': {'intent': 'Investigate dropdown selected value'}}
        step = {'assertions': [assertion]}
        close_button = {'name': 'Close case', 'selector': '[aria-label="Close case"]', 'tag': 'button', 'role': 'button', 'rect': {'x': 1600, 'y': 20, 'width': 90, 'height': 30}}
        agent._pre_action_control_names = {((1600, 20, 90, 30), 'Close case'), ((700, 120, 120, 32), 'Investigate')}
        stale = {'name': 'Investigate', 'selector': '[title="Investigate"]', 'tag': 'span', 'rect': {'x': 700, 'y': 120, 'width': 120, 'height': 32}}
        fresh = {'name': 'Close', 'selector': '[title="Close"]', 'tag': 'span', 'rect': {'x': 700, 'y': 120, 'width': 90, 'height': 32}}
        agent._build_actionable_controls = AsyncMock(side_effect=[[close_button, stale], [close_button, fresh]])
        agent._build_observable_elements = AsyncMock(return_value=[])
        page = SimpleNamespace(wait_for_timeout=AsyncMock())

        bindings = asyncio.run(agent._selected_value_binding_from_completed_click(page, step, [assertion], {'action': 'click', 'selector': '[title="Close"]'}))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '[title="Close"]'}])
        self.assertEqual(page.wait_for_timeout.await_count, 1)

    def test_image_wait_holds_until_the_target_camera_thumbnail_renders(self) -> None:
        agent = PyUICompatAgent(case_name='Target_Thumbnail_Wait')
        agent._execution_resources = [{'resource_type': 'environment_device', 'resource': {'role': 'main_device', 'camera_names': ['5003_D13']}}]
        agent._rendered_visual_baseline = {'#old'}
        card = {'name': '5003_D13', 'rect': {'x': 116, 'y': 586, 'width': 168, 'height': 94}}
        other = {'name': '5003_D03', 'rect': {'x': 116, 'y': 382, 'width': 168, 'height': 94}}
        agent._build_actionable_controls = AsyncMock(return_value=[other, card])
        agent._rendered_visual_elements = AsyncMock(side_effect=[
            [{'selector': '#d03-img', 'rect': {'x': 118, 'y': 384, 'width': 164, 'height': 90}}],
            [{'selector': '#d03-img', 'rect': {'x': 118, 'y': 384, 'width': 164, 'height': 90}}, {'selector': '#d13-img', 'rect': {'x': 118, 'y': 588, 'width': 164, 'height': 90}}],
        ])
        step = {'description': 'Locate the camera for the default test device', 'assertions': [
            {'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'required': True, 'target': {'intent': 'thumbnail image on the target camera', 'text': 'camera', 'visual_content': 'image'}},
        ]}
        page = SimpleNamespace(wait_for_timeout=AsyncMock(), evaluate=AsyncMock(return_value=False))

        asyncio.run(agent._wait_for_rendered_visual_content(page, step, step['assertions']))

        self.assertEqual(page.wait_for_timeout.await_count, 1)
        self.assertIn('IMAGE_RENDER_WAIT_MS', inspect.getsource(PyUICompatAgent._wait_for_rendered_visual_content))

    def test_media_binder_prefers_the_target_camera_thumbnail_and_never_a_neighbour(self) -> None:
        agent = PyUICompatAgent(case_name='Target_Thumbnail_Binding')
        agent._execution_resources = [{'resource_type': 'environment_device', 'resource': {'role': 'main_device', 'camera_names': ['5003_D13']}}]
        agent._rendered_visual_baseline = set()
        card = {'name': '5003_D13', 'rect': {'x': 116, 'y': 586, 'width': 168, 'height': 94}}
        other = {'name': '5003_D03', 'rect': {'x': 116, 'y': 382, 'width': 168, 'height': 94}}
        agent._build_actionable_controls = AsyncMock(return_value=[other, card])
        assertion = {'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'required': True, 'target': {'intent': 'thumbnail image on the target camera icon', 'text': 'camera', 'visual_content': 'image'}}
        step = {'description': 'Locate the camera for the default test device', 'assertions': [assertion]}
        d03 = {'selector': '#d03-img', 'area': 14760, 'rect': {'x': 118, 'y': 384, 'width': 164, 'height': 90}}
        d13 = {'selector': '#d13-img', 'area': 14760, 'rect': {'x': 118, 'y': 588, 'width': 164, 'height': 90}}

        agent._rendered_visual_elements = AsyncMock(return_value=[d03, d13])
        self.assertEqual(
            asyncio.run(agent._rendered_visual_binding_from_completed_action(object(), step, [assertion], {'action': 'click'})),
            [{'assertion_index': 1, 'locator': '#d13-img'}],
        )
        agent._rendered_visual_elements = AsyncMock(return_value=[d03])
        self.assertEqual(asyncio.run(agent._rendered_visual_binding_from_completed_action(object(), step, [assertion], {'action': 'click'})), [])
        self.assertEqual(agent._runtime_events[-1].get('target_camera_pending'), 1)

    def test_visible_element_binder_accepts_a_serialised_true_expectation(self) -> None:
        agent = PyUICompatAgent(case_name='String_True_Binding')
        assertion = {
            'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': 'true'}, 'required': True,
            'target': {'intent': 'Magic Search V2 option in the Magic dropdown list', 'text': 'Magic Search V2'},
        }
        agent._build_actionable_controls = AsyncMock(return_value=[
            {'name': 'Magic Search V2', 'selector': 'body > div:nth-of-type(2) > div:nth-of-type(1) > ul:nth-of-type(1) > li:nth-of-type(1)', 'top_layer': True},
            {'name': 'Magic Search V2', 'selector': 'body > div:nth-of-type(2) > div:nth-of-type(1) > ul:nth-of-type(1) > li:nth-of-type(1) > span:nth-of-type(1)', 'top_layer': True},
        ])

        bindings = asyncio.run(agent._visible_element_binding_from_completed_click(
            object(), {'assertions': [assertion]}, [assertion], {'action': 'click', 'selector': '[aria-label="Switch search mode"]'},
        ))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': 'body > div:nth-of-type(2) > div:nth-of-type(1) > ul:nth-of-type(1) > li:nth-of-type(1)'}])

    def test_rebind_recovery_re_evaluates_after_binders_replace_the_step_assertions(self) -> None:
        agent = PyUICompatAgent(case_name='Rebind_Recovery', execution_record_id=9)
        step = {'description': 'Click the site', 'assertions': [
            {'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'required': True, 'target': {'intent': 'camera items'}},
        ]}
        agent._action_had_visible_effect = AsyncMock(return_value=True)
        agent._wait_for_assertion_observation = AsyncMock()

        async def bind(page, current_step, step_index, actions, step_callback, history):
            bound = {**current_step['assertions'][0], 'target': {'intent': 'camera items', 'locator': '#cards > div'}}
            current_step.clear()
            current_step.update({'description': 'Click the site', 'assertions': [bound]})
            return True

        agent._bind_required_assertions_after_action = bind
        agent._capture_screenshot = AsyncMock(return_value='shot.png')
        agent._persist_step_attempt = AsyncMock(return_value={'assertion_statuses': ['passed']})
        history = HistoryStub()

        result = asyncio.run(agent._recover_by_rebinding(SimpleNamespace(wait_for_timeout=AsyncMock()), step, 3, [{'action': 'click', 'selector': '#btnSite'}], None, history, None))

        self.assertEqual(result[0], 'completed')
        self.assertEqual(history.artifacts[-1]['type'], 'rebind_recovery')

    def test_verify_only_image_steps_wait_for_the_thumbnail_before_planning(self) -> None:
        source = inspect.getsource(PyUICompatAgent._plan_ai_step)
        self.assertIn('image_assertions = self._image_assertions(step)', source)
        self.assertIn('_wait_for_rendered_visual_content(page, step, image_assertions)', source)

    def test_image_wait_settles_on_existing_media_inside_the_target_card(self) -> None:
        agent = PyUICompatAgent(case_name='Target_Card_Existing_Media')
        agent._execution_resources = [{'resource_type': 'environment_device', 'resource': {'role': 'main_device', 'camera_names': ['5003_D13']}}]
        agent._rendered_visual_baseline = None
        agent._build_actionable_controls = AsyncMock(return_value=[{'name': '5003_D13', 'rect': {'x': 116, 'y': 586, 'width': 168, 'height': 94}}])
        agent._rendered_visual_elements = AsyncMock(return_value=[{'selector': '#d13-img', 'rect': {'x': 118, 'y': 588, 'width': 164, 'height': 90}}])
        step = {'description': 'Locate camera 5003_D13 among the results', 'assertions': [
            {'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'required': True, 'target': {'intent': 'thumbnail on camera 5003_D13', 'text': '5003_D13', 'visual_content': 'image'}},
        ]}
        page = SimpleNamespace(wait_for_timeout=AsyncMock(), evaluate=AsyncMock(return_value=False))

        asyncio.run(agent._wait_for_rendered_visual_content(page, step, step['assertions']))

        page.wait_for_timeout.assert_not_awaited()
        page.evaluate.assert_not_awaited()

    def test_binders_run_per_assertion_and_merge_bindings_for_multi_assertion_steps(self) -> None:
        agent = PyUICompatAgent(case_name='Multi_Assertion_Binding', execution_record_id=None)
        collection = {'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0}, 'required': True, 'target': {'intent': 'camera list result items'}}
        image = {'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'required': True, 'target': {'text': '5003_D13', 'intent': 'thumbnail on camera 5003_D13', 'visual_content': 'image'}}
        step = {'description': 'Type the site name, then locate camera 5003_D13', 'assertions': [collection, image]}

        async def collection_binder(page, current_step, unresolved, action):
            return [{'assertion_index': 1, 'locator': '#cards > div'}] if unresolved == [collection] else []

        async def visual_binder(page, current_step, unresolved, action):
            return [{'assertion_index': 2, 'locator': '#cards > div:nth-of-type(5) > img'}] if unresolved == [image] else []

        async def decline(page, current_step, unresolved, action):
            return []

        for name in ('_field_value_bindings_from_completed_action', '_selected_value_binding_from_completed_click', '_visible_element_binding_from_completed_click', '_intent_value_binding_from_completed_action', '_vanished_media_binding_from_completed_action', '_fresh_content_binding_from_completed_action'):
            setattr(agent, name, decline)
        agent._collection_binding_from_completed_action = collection_binder
        agent._rendered_visual_binding_from_completed_action = visual_binder
        history = HistoryStub()

        bound = asyncio.run(agent._bind_required_assertions_after_action(object(), step, 2, [{'action': 'click', 'selector': '#btnSite'}], None, history))

        self.assertTrue(bound)
        self.assertEqual([a['target']['locator'] for a in step['assertions']], ['#cards > div', '#cards > div:nth-of-type(5) > img'])
        self.assertEqual([a['binder'] for a in history.artifacts if a['type'] == 'deterministic_binding'], ['collection', 'rendered_visual'])

    def test_binders_accept_read_only_recovery_actions_such_as_scroll(self) -> None:
        agent = PyUICompatAgent(case_name='Scroll_Then_Bind')
        assertion = {
            'assert_kind': 'element_state', 'operator': 'exists', 'expected': {'value': True}, 'required': True,
            'target': {'intent': 'monitoring view status control showing To Do'},
        }
        step = {'assertions': [assertion]}
        agent._build_actionable_controls = AsyncMock(return_value=[{'name': 'To Do', 'selector': '[title="To Do"]', 'tag': 'span'}])
        agent._build_observable_elements = AsyncMock(return_value=[])

        bindings = asyncio.run(agent._intent_value_binding_from_completed_action(object(), step, [assertion], {'action': 'scroll', 'selector': '#list'}))

        self.assertEqual(bindings, [{'assertion_index': 1, 'locator': '[title="To Do"]'}])

    def test_normalize_step_preserves_structured_transition(self) -> None:
        agent = PyUICompatAgent(case_name='Structured_Transition')
        transition = {'kind': 'select_option', 'value': 'requested option'}

        step = agent._normalize_step({'action': 'click', 'transition': transition}, 1)

        self.assertEqual(step['transition'], transition)

    def test_assertion_replan_uses_persisted_scroll_evidence(self) -> None:
        agent = PyUICompatAgent(case_name='Planner_Scroll_Evidence', execution_record_id=7)
        history = HistoryStub()
        step = {'description': 'Reveal and open the requested item', 'assertions': [{'action': 'assert'}]}
        agent._plan_ai_step_with_retries = AsyncMock(side_effect=[
            [{'action': 'scroll', 'selector': '#list'}],
            [{'action': 'assert'}],
        ])
        agent._execute_ai_actions = AsyncMock()
        agent._capture_media_state = AsyncMock(return_value=[])
        agent._capture_screenshot = AsyncMock(return_value='retry.png')
        persisted_scroll = {
            'action': 'scroll',
            'selector': '#list',
            'scroll_state': {
                'before': {'scroll_top': 0, 'remaining': 24},
                'after': {'scroll_top': 1, 'remaining': 23},
            },
        }
        agent._persisted_step_action_history = Mock(side_effect=[[], [persisted_scroll]])
        agent._persist_step_attempt = AsyncMock(side_effect=[
            {'assertion_statuses': ['inconclusive']},
            {'assertion_statuses': ['passed'], 'action': {'action': 'assert'}},
        ])
        page = SimpleNamespace(wait_for_timeout=AsyncMock())

        with patch('apps.ai_testing.execution.plan_persistence.persist_replanned_step'):
            result = asyncio.run(agent._retry_assertion_failure(
                page, step, 1, [{'action': 'click', 'selector': '#initial'}], ['inconclusive'],
                None, TimeoutError, history, None,
            ))

        second_replanning_step = agent._plan_ai_step_with_retries.await_args_list[1].args[1]
        self.assertEqual(result[0], 'completed')
        self.assertEqual(
            second_replanning_step['_prior_actions'][-1]['scroll_state']['after']['scroll_top'],
            1,
        )

    def test_plan_ai_step_exposes_replanning_context_during_mcp_observation(self) -> None:
        agent = PyUICompatAgent(case_name='Replanning_Observation')
        replanning_step = {
            'description': 'Choose a different control',
            'allowed_capabilities': ['browser.inspect'],
            '_prior_actions': [{'action': 'click', 'selector': '#failed'}],
        }
        observed_steps = []

        async def observe(_name, _arguments):
            observed_steps.append(agent._active_planning_step)
            return {'structuredContent': {'actionable_controls': []}}

        agent._mcp_client = SimpleNamespace(call_tool=AsyncMock(side_effect=observe))
        with patch(
            'apps.ai_testing.global_planner.VisualStepReplanner.create_actions',
            new=AsyncMock(return_value=[{'action': 'assert'}]),
        ):
            asyncio.run(agent._plan_ai_step(object(), replanning_step))

        self.assertIs(observed_steps[0], replanning_step)
        self.assertIsNone(agent._active_planning_step)

    def test_verified_predecessor_context_keeps_bound_target_evidence(self) -> None:
        agent = PyUICompatAgent(case_name='Planner_Target_Continuity')
        history = HistoryStub()
        history.steps = [
            {
                'step_num': 1,
                'step_description': 'Locate the requested item',
                'action': 'assert',
                'executor': 'browser',
                'assertions': [{
                    'assert_kind': 'element_state',
                    'target': {'intent': 'requested item', 'locator': '#item-7 img'},
                }],
                'result': True,
            },
            {
                'step_num': 2,
                'step_description': 'Unverified step',
                'assertions': [{'target': {'locator': '#other'}}],
                'result': False,
            },
        ]

        context = agent._verified_predecessor_context(history)

        self.assertEqual(context, [{
            'step_num': 1,
            'description': 'Locate the requested item',
            'action': 'assert',
            'executor': 'browser',
            'assertions': [{
                'assert_kind': 'element_state',
                'target': {'intent': 'requested item', 'locator': '#item-7 img'},
            }],
        }])

    def test_assertion_replan_contract_exhaustion_remains_inconclusive(self) -> None:
        from apps.ai_testing.runtime.pyui_compat.runner import PlannerRetryExhaustedError

        agent = PyUICompatAgent(case_name='Planner_Recovery', execution_record_id=7)
        history = HistoryStub()
        step = {'description': 'Verify requested state', 'assertions': [{'action': 'assert'}]}
        agent._plan_ai_step_with_retries = AsyncMock(side_effect=PlannerRetryExhaustedError('no distinct action'))
        agent._persisted_step_action_history = Mock(return_value=[])
        agent._execute_ai_actions = AsyncMock()

        result = asyncio.run(agent._retry_assertion_failure(
            object(), step, 1, [{'action': 'scroll', 'selector': '#list'}], ['inconclusive'],
            None, TimeoutError, history, None,
        ))

        self.assertEqual(result[0], 'inconclusive')
        self.assertIn('PlannerRetryExhaustedError: no distinct action', result[1])
        agent._execute_ai_actions.assert_not_awaited()

    def test_assertion_replan_does_not_hide_runtime_failure(self) -> None:
        agent = PyUICompatAgent(case_name='Planner_Recovery', execution_record_id=7)
        agent._plan_ai_step_with_retries = AsyncMock(side_effect=RuntimeError('provider unavailable'))
        agent._persisted_step_action_history = Mock(return_value=[])

        with self.assertRaisesRegex(RuntimeError, 'provider unavailable'):
            asyncio.run(agent._retry_assertion_failure(
                object(), {'description': 'Verify state', 'assertions': [{'action': 'assert'}]},
                1, [{'action': 'assert'}], ['inconclusive'], None, TimeoutError, HistoryStub(), None,
            ))

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

                self.assertTrue(first._cache_key_for_step(step).startswith('v6::'))
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


class ActionCacheDatabaseTests(TestCase):
    """The step action cache lives in the database with a sliding TTL and a per-step variant cap.

    The synchronous helpers are exercised directly: the async wrappers hop to asgiref's worker thread, whose
    connection sits outside the test transaction.
    """

    def setUp(self):
        self.agent = PyUICompatAgent(case_name='TC_004', ai_project_id=None, execution_user_id=1)
        self.step = {'index': 1, 'description': '点击登录按钮'}
        self.context = {'url': 'https://example.test/login', 'fingerprint': 'fp-login', 'application_version': ''}
        self.actions = [{'action': 'click', 'selector': 'text=Login'}]

    def _store(self, step, actions, context):
        self.agent._upsert_cached_actions_sync(step, self.agent._safe_experience_actions(actions), context)

    def _load(self, step, context):
        return self.agent._find_cached_actions_sync(self.agent._cache_key_for_step(step, context))

    def test_store_and_load_roundtrip_updates_hits_and_slides_expiry(self):
        from apps.ai_testing.models import AIActionCacheEntry

        self._store(self.step, self.actions, self.context)
        entry = AIActionCacheEntry.objects.get()
        self.assertTrue(entry.cache_key.startswith('v6::TC_004::step1::'))
        self.assertEqual(entry.actions, self.actions)
        first_expiry = entry.expires_at

        self.assertEqual(self._load(self.step, self.context), self.actions)
        entry.refresh_from_db()
        self.assertEqual(entry.hit_count, 1)
        self.assertIsNotNone(entry.last_hit_at)
        self.assertGreaterEqual(entry.expires_at, first_expiry)

    def test_async_wrappers_refuse_to_store_or_load_without_a_page_fingerprint(self):
        # No database is touched on this path, so the async wrappers are safe to call here.
        self.agent._upsert_cached_actions_sync = Mock()
        self.agent._find_cached_actions_sync = Mock()
        asyncio.run(self.agent._store_cached_ai_actions(self.step, self.actions, {'url': 'https://example.test', 'fingerprint': ''}))
        self.assertIsNone(asyncio.run(self.agent._load_cached_ai_actions(self.step, {'fingerprint': ''})))
        self.agent._upsert_cached_actions_sync.assert_not_called()
        self.agent._find_cached_actions_sync.assert_not_called()

    def test_expired_entries_are_misses_and_are_purged_on_write(self):
        from django.utils import timezone

        from apps.ai_testing.models import AIActionCacheEntry

        self._store(self.step, self.actions, self.context)
        AIActionCacheEntry.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertIsNone(self._load(self.step, self.context))

        other = {'index': 2, 'description': '输入邮箱'}
        self._store(other, [{'action': 'fill', 'selector': '#email', 'value': 'a@b.c'}], self.context)
        self.assertEqual(list(AIActionCacheEntry.objects.values_list('step_index', flat=True)), [2])

    def test_each_step_keeps_only_its_newest_page_state_variants(self):
        from apps.ai_testing.models import AIActionCacheEntry

        self.agent.environment_configuration = SimpleNamespace(runtime_settings={'ai_testing_browser': {'action_cache_variants_per_step': 2}})
        for index in range(4):
            self._store(self.step, self.actions, {**self.context, 'fingerprint': f'fp-{index}'})
        self.assertEqual(AIActionCacheEntry.objects.count(), 2)
        self.assertIsNone(self._load(self.step, {**self.context, 'fingerprint': 'fp-0'}))
        self.assertEqual(self._load(self.step, {**self.context, 'fingerprint': 'fp-3'}), self.actions)

    def test_delete_removes_the_entry(self):
        from apps.ai_testing.models import AIActionCacheEntry

        self._store(self.step, self.actions, self.context)
        self.assertEqual(self.agent._delete_cached_actions_sync(self.agent._cache_key_for_step(self.step, self.context)), 1)
        self.assertEqual(AIActionCacheEntry.objects.count(), 0)

    def test_get_ai_actions_prefers_cache_then_skips_it_when_disabled(self):
        history = HistoryStub()
        self._store(self.step, self.actions, self.context)
        self.agent._build_page_context = AsyncMock(return_value=self.context)
        # Read the stored entry on the test thread first; Django forbids ORM calls from inside the event loop.
        self.agent._load_cached_ai_actions = AsyncMock(return_value=self._load(self.step, self.context))
        self.agent._plan_ai_step_for_cacheable_step = AsyncMock(return_value=[{'action': 'click'}])

        actions, source = asyncio.run(self.agent._get_ai_actions_for_step(page=None, step=self.step, history=history))
        self.assertEqual((actions, source), (self.actions, 'cache'))
        self.assertEqual(history.cache_stats['hit'], 1)
        self.agent._plan_ai_step_for_cacheable_step.assert_not_awaited()

        disabled = PyUICompatAgent(case_name='TC_004', execution_user_id=1, use_cache=False)
        disabled._build_page_context = AsyncMock(return_value=self.context)
        disabled._load_cached_ai_actions = AsyncMock(side_effect=AssertionError('cache must not be consulted'))
        disabled._plan_ai_step_for_cacheable_step = AsyncMock(return_value=[{'action': 'click'}])
        actions, source = asyncio.run(disabled._get_ai_actions_for_step(page=None, step=self.step, history=HistoryStub()))
        self.assertEqual((actions, source), ([{'action': 'click'}], 'model'))

    def test_manage_action_cache_command_reports_and_clears(self):
        from io import StringIO

        from django.core.management import call_command

        from apps.ai_testing.models import AIActionCacheEntry

        self._store(self.step, self.actions, self.context)
        out = StringIO()
        call_command('manage_action_cache', stats=True, stdout=out)
        self.assertIn('entries=1 expired=0', out.getvalue())
        self.assertIn('TC_004: entries=1', out.getvalue())
        out = StringIO()
        call_command('manage_action_cache', clear=True, case='TC_004', stdout=out)
        self.assertIn('cleared entries: 1', out.getvalue())
        self.assertEqual(AIActionCacheEntry.objects.count(), 0)
