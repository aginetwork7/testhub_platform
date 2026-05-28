import asyncio
from dataclasses import dataclass, field
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock

from django.test import SimpleTestCase, override_settings

from apps.ai_testing.runtime.pyui_compat import PyUICompatAgent


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
                self.assertTrue((Path(media_root) / 'ai_testing' / 'cache' / 'action_cache.json').exists())

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

                self.assertTrue(first._cache_key_for_step(step).startswith('v2::'))
                self.assertNotEqual(first._cache_key_for_step(step), second._cache_key_for_step(step))