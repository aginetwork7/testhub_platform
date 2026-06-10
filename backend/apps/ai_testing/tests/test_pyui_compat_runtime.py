import asyncio
from dataclasses import dataclass, field
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock

from django.conf import settings
from django.test import SimpleTestCase, override_settings

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


class _TextLocatorStub:
    def __init__(self, text: str):
        self._text = text
        self.first = self

    async def text_content(self, timeout: int = 0) -> str:
        return self._text


class _TextPageStub:
    def __init__(self, text: str):
        self._locator = _TextLocatorStub(text)
        self.waited_ms = None

    def locator(self, _selector: str) -> _TextLocatorStub:
        return self._locator

    async def wait_for_timeout(self, timeout: int) -> None:
        self.waited_ms = timeout


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

    def test_plan_ai_step_does_not_write_cache_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='TC_004', use_cache=False)
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

    def test_fallback_actions_for_team_option(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        actions = agent._fallback_actions_for_step({'description': '点击组织管理子选项中的Team选项'})

        self.assertEqual(
            actions,
            [
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
            ],
        )

    def test_fallback_actions_for_team_option_assertion(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        actions = agent._fallback_actions_for_step({'description': '断言组织管理子选项中包含"Team"选项'})

        self.assertEqual(
            actions,
            [
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
            ],
        )

    def test_fallback_actions_for_add_user_button(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        actions = agent._fallback_actions_for_step({'description': '点击页面上方的蓝色加号, 创建新的角色'})

        self.assertEqual(
            actions,
            [
                {
                    'action': 'click',
                    'selector': 'button[aria-label="Add New User"]',
                    'reason': 'fallback click add-user button on organization page',
                }
            ],
        )

    def test_fallback_actions_for_organization_hover(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        actions = agent._fallback_actions_for_step({'description': '鼠标悬停在组织管理按钮上,该按钮是三个人图标'})

        self.assertEqual(
            actions,
            [
                {
                    'action': 'hover',
                    'selector': 'text=Organization',
                    'reason': 'fallback deterministic organization sidebar hover',
                }
            ],
        )

    def test_fallback_actions_for_site_manager_role_flow(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        self.assertEqual(
            agent._fallback_actions_for_step({'description': '点击页面下方的角色下拉框, 当前值为Org Admin'}),
            [
                {
                    'action': 'click',
                    'selector': 'text=Org Admin (Can manage and view all sites)',
                    'reason': 'fallback deterministic role dropdown open',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '断言下拉框列表中包含"Site Manager"选项'}),
            [
                {
                    'action': 'assert_text_contains',
                    'selector': 'body',
                    'expected': 'Site Manager (Can manage and view specified sites)',
                    'reason': 'fallback deterministic role option assertion',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '从下拉框中选择并点击Site Manager选项'}),
            [
                {
                    'action': 'click',
                    'selector': 'text=Site Manager (Can manage and view specified sites)',
                    'reason': 'fallback deterministic role option click',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '断言下拉框列表中当前值为Site Manager'}),
            [
                {
                    'action': 'assert_text_contains',
                    'selector': 'body',
                    'expected': 'Site Manager (Can manage and view specified sites)',
                    'reason': 'fallback deterministic selected role assertion',
                }
            ],
        )

    def test_fallback_actions_for_magic_search_option_flow(self) -> None:
        agent = PyUICompatAgent(case_name='TC_002')

        self.assertEqual(
            agent._fallback_actions_for_step({'description': '点击搜索框中的放大镜图标，展开高级搜索面板'}),
            [
                {
                    'action': 'click',
                    'selector': 'div.colorBorder.rounded-xl.flex.bg-white > button.ant-dropdown-trigger',
                    'reason': 'fallback deterministic advanced-search leading magnifier click',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': "断言高级搜索面板已展开，且列表中包含'Magic Search V2'选项"}),
            [
                {
                    'action': 'assert',
                    'assert_kind': 'text_visible',
                    'param': 'Magic Search V2',
                    'reason': 'fallback deterministic advanced-search option assertion',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': "点击高级搜索列表中的'Magic Search V2'选项"}),
            [
                {
                    'action': 'click',
                    'selector': 'Magic Search V2',
                    'reason': 'fallback deterministic advanced-search option click',
                }
            ],
        )

        self.assertEqual(
            agent._fallback_actions_for_step({'description': "断言搜索框中placeholder已填充为'Magic Search V2'"}),
            [
                {
                    'action': 'assert',
                    'assert_kind': 'placeholder_equals',
                    'selector': "input[placeholder*='Magic Search' i]",
                    'param': 'Magic Search V2',
                    'expected': 'True',
                    'reason': 'fallback deterministic Magic Search V2 placeholder assertion',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '点击第一条结果的预览缩略图'}),
            [
                {
                    'action': 'click',
                    'selector': "div[id^='alert_'].cursor-pointer > div.relative.rounded-lg",
                    'param': 'first preview',
                    'reason': 'fallback deterministic first result preview thumbnail click',
                }
            ],
        )

    def test_fallback_actions_for_alert_status_dropdown_flow(self) -> None:
        agent = PyUICompatAgent(case_name='TC_003')

        self.assertEqual(
            agent._fallback_actions_for_step({'description': "点击监控画面下方的'To Do'下拉框, 先展开状态选项列表"}),
            [
                {
                    'action': 'click',
                    'selector': '.alert-select-root .ant-select-selector',
                    'reason': 'fallback deterministic alert-status dropdown open',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': "在已展开的状态选项列表中点击'Close'标签（点击列表项本身，不要再次点击'To Do'下拉框按钮）"}),
            [
                {
                    'action': 'change_alert_status',
                    'selector': '.alert-select-root',
                    'value': 'Close',
                    'reason': 'fallback deterministic alert-status option change',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '点击显示列表中的第一个结果'}),
            [
                {
                    'action': 'click',
                    'loc': '(180,245)',
                    'param': 'first alert result',
                    'reason': 'fallback deterministic first alert result click',
                }
            ],
        )

    def test_resolve_alert_status_target_prefers_runtime_options(self) -> None:
        agent = PyUICompatAgent(case_name='TC_003')

        self.assertEqual(
            agent._resolve_alert_status_target('Close', 'To Do', ['To Do', 'False Alarm']),
            'False Alarm',
        )
        self.assertEqual(
            agent._resolve_alert_status_target('False Alarm', 'To Do', ['To Do', 'False Alarm']),
            'False Alarm',
        )

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

    def test_execute_step_assert_text_contains_ignores_whitespace_gaps(self) -> None:
        agent = PyUICompatAgent(case_name='TC_005')
        page = _TextPageStub('滨江区7/0 萧山区8/0')
        step = {
            'action': 'assert_text_contains',
            'selector': 'body',
            'expected': '滨江区 7 / 0',
            'timeout_ms': 1000,
        }

        asyncio.run(agent._execute_step(page, step, TimeoutError))

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

    def test_fallback_actions_for_icon_shape_steps(self) -> None:
        agent = PyUICompatAgent(case_name='TC_003')

        self.assertEqual(
            agent._fallback_actions_for_step({'description': "点击'Alerts'功能按钮, 该按钮是一个铃铛形状"}),
            [{'action': 'click', 'loc': '(48,196)', 'param': ':left:top:25:25'}],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': "点击'Cameras'按钮, 该按钮是一个摄像头的形状"}),
            [
                {
                    'action': 'click',
                    'loc': '(48,142)',
                    'param': ':left:top:25:25',
                    'reason': 'fallback open cameras sidebar entry',
                },
                {
                    'action': 'click',
                    'selector': 'text=Cameras',
                    'param': 'Cameras',
                    'reason': 'fallback click cameras submenu item',
                },
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': "点击'Dark Mode'功能按钮, 该按钮位于左侧导航栏最上方, 形状为包含三角形和菱形的对称几何形状"}),
            [{'action': 'click', 'loc': '(48,32)', 'param': ':left:top:25:25'}],
        )

    def test_fallback_actions_for_popup_assertion(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        actions = agent._fallback_actions_for_step({'description': '断言页面出现提示弹窗，且包含“User created successfully!”'})

        self.assertEqual(
            actions,
            [
                {
                    'action': 'assert_popup_contains',
                    'expected': 'User created successfully!',
                    'reason': 'fallback deterministic popup assertion',
                }
            ],
        )

    def test_plan_ai_step_prefers_popup_fallback_before_model(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        actions = asyncio.run(
            agent._plan_ai_step(
                page=None,
                step={'description': '断言页面出现提示弹窗，且包含“User created successfully!”'},
            )
        )

        self.assertEqual(actions[0]['action'], 'assert_popup_contains')
        self.assertEqual(actions[0]['expected'], 'User created successfully!')

    def test_popup_success_compatible_with_recent_create_mutation(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')
        agent._recent_network_events = [
            {
                'ts': time.time(),
                'method': 'POST',
                'url': 'https://test-api-2.agi7.ai/agi7/api/org/users',
                'status': 200,
                'ok': True,
            }
        ]

        self.assertTrue(agent._popup_success_compatible_with_recent_mutation('User created successfully!'))

    def test_popup_success_compatible_with_recent_delete_mutation(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')
        agent._recent_network_events = [
            {
                'ts': time.time(),
                'method': 'PATCH',
                'url': 'https://test-api-2.agi7.ai/agi7/api/org/users/2366/deactivate',
                'status': 200,
                'ok': True,
            }
        ]

        self.assertTrue(agent._popup_success_compatible_with_recent_mutation('User deleted successfully!'))

    def test_fallback_actions_for_negative_user_list_assertion(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        actions = agent._fallback_actions_for_step({'description': '断言页面中左侧展示的用户列表中不包含ai@test.com用户'})

        self.assertEqual(
            actions,
            [
                {
                    'action': 'assert',
                    'assert_kind': 'text_visible',
                    'param': 'ai@test.com',
                    'expected': 'False',
                    'reason': 'fallback deterministic negative list assertion',
                }
            ],
        )

    def test_fallback_actions_for_positive_user_list_assertion(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        actions = agent._fallback_actions_for_step({'description': '断言搜索结果中包含ai@test.com用户'})

        self.assertEqual(
            actions,
            [
                {
                    'action': 'assert',
                    'assert_kind': 'text_visible',
                    'param': 'ai@test.com',
                    'expected': 'True',
                    'reason': 'fallback deterministic positive list assertion',
                }
            ],
        )

    def test_fallback_actions_for_create_user_form_fields(self) -> None:
        agent = PyUICompatAgent(case_name='TC_004')

        self.assertEqual(
            agent._fallback_actions_for_step({'description': 'First Name输入框填写AI'}),
            [
                {
                    'action': 'fill',
                    'selector': "input[type='text'][placeholder='First Name']",
                    'value': 'AI',
                    'reason': 'fallback deterministic first-name fill',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': 'Last Name输入框填写Test'}),
            [
                {
                    'action': 'fill',
                    'selector': "input[type='text'][placeholder='Last Name']",
                    'value': 'Test',
                    'reason': 'fallback deterministic last-name fill',
                }
            ],
        )

    def test_fallback_actions_override_bad_cached_ai_plan(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                agent = PyUICompatAgent(case_name='TC_004')
                step = {'index': 8, 'description': 'First Name输入框填写AI'}
                asyncio.run(agent._store_cached_ai_actions(step, [{'action': 'fill', 'selector': 'text=First Name', 'value': 'AI'}]))

                history = PyUICompatHistory(cache_stats={'hit': 0, 'miss': 1})
                actions, source = asyncio.run(agent._get_ai_actions_for_step(page=None, step=step, history=history))

                self.assertEqual(source, 'fallback')
                self.assertEqual(actions[0]['selector'], "input[type='text'][placeholder='First Name']")

    def test_fallback_actions_for_tc005_camera_preview_flow(self) -> None:
        agent = PyUICompatAgent(case_name='TC_005')

        self.assertEqual(
            agent._fallback_actions_for_step({'description': '断言当前页面展示出站点列表, 每个站点名称后都展示在线和离线的摄像头数量'}),
            [
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
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '点击搜索结果中目标站点名称'}),
            [
                {
                    'action': 'click',
                    'selector': '#btnSite',
                    'param': 'first site result',
                    'reason': 'fallback deterministic site result click',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': "从站点列表中找到第一个站点作为目标站点, 在placeholder为'Search site name...'的搜索框中输入目标站点名称"}),
            [
                {
                    'action': 'search_site_with_cameras',
                    'selector': "input[placeholder*='Search site name' i], input[placeholder*='Search' i]",
                    'reason': 'fallback search the first site that has available cameras',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '断言目标站点名称下方展示出该站点的摄像头列表'}),
            [
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
                    'min_x': 180,
                    'min_y': 120,
                    'min_width': 40,
                    'min_height': 20,
                    'param': 'camera_list',
                    'expected': 'True',
                    'reason': 'fallback deterministic camera list assertion',
                },
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '从摄像头列表中找到第一个在线的摄像头, 点击该摄像头的预览图'}),
            [
                {
                    'action': 'click',
                    'selector': "div[class*='grid'] > div, div[class*='grid'] > button, [class*='camera'] [class*='preview'], [class*='camera'] [class*='thumbnail'], [class*='camera-item'] img, [class*='camera-item'] video, [class*='camera-item'] canvas",
                    'param': 'first camera preview',
                    'reason': 'fallback deterministic first camera preview click',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '断言当前页面展示出该摄像头的实时视频流'}),
            [
                {
                    'action': 'assert',
                    'assert_kind': 'stream_active',
                    'param': 'stream_view',
                    'expected': 'True',
                    'reason': 'fallback deterministic active stream assertion',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '点击页面正下方的视频流关闭按钮, 该按钮为带盖垃圾桶形状'}),
            [
                {
                    'action': 'click',
                    'loc': '(1154,834)',
                    'param': 'stream close button',
                    'reason': 'fallback deterministic stream close button click',
                }
            ],
        )
        self.assertEqual(
            agent._fallback_actions_for_step({'description': '断言实时视频流页面关闭'}),
            [
                {
                    'action': 'assert',
                    'assert_kind': 'selector_non_empty',
                    'selector_candidates': [
                        'video',
                        'canvas',
                        "[class*='stream']",
                        "[class*='player']",
                        "[class*='live']",
                    ],
                    'min_count': 1,
                    'min_x': 420,
                    'min_y': 140,
                    'min_width': 600,
                    'min_height': 320,
                    'param': 'stream_view',
                    'expected': 'False',
                    'reason': 'fallback deterministic stream view closed assertion',
                }
            ],
        )

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

                self.assertTrue(first._cache_key_for_step(step).startswith('v3::'))
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