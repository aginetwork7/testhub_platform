"""识别「动作有效果，但不是预期的效果」。"""

import asyncio

from django.test import SimpleTestCase

from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatAgent


def _agent(rendered):
    agent = PyUICompatAgent.__new__(PyUICompatAgent)

    async def _elements(_page):
        return rendered
    agent._rendered_visual_elements = _elements
    return agent


def _step(assert_kind='stream_state', required=True):
    return {'assertions': [{
        'assert_kind': assert_kind, 'operator': 'equals',
        'expected': {'minimum_advanced_seconds': 2},
        'target': {'intent': 'live video stream for camera 5003_D13'}, 'required': required,
    }]}


class ExpectedMediaSurfaceTests(SimpleTestCase):
    @staticmethod
    def _missing(agent, step):
        return asyncio.run(agent._expected_media_surface_missing(None, step))

    def test_a_stream_step_with_no_video_or_canvas_is_flagged(self) -> None:
        # 记录 174：点击没打开直播视图，页面上只剩摄像头列表的 <img> 缩略图。
        agent = _agent([{'tag': 'img', 'selector': 'img.thumb'} for _ in range(30)])
        self.assertTrue(self._missing(agent, _step()))

    def test_an_open_player_is_left_alone(self) -> None:
        # 播放器已存在但卡住时不能重复点击——那可能把断言要看的东西关掉。
        agent = _agent([{'tag': 'video', 'selector': '#player'}])
        self.assertFalse(self._missing(agent, _step()))

    def test_a_canvas_counts_as_a_surface(self) -> None:
        agent = _agent([{'tag': 'canvas', 'selector': '#canvas_streaming_1'}])
        self.assertFalse(self._missing(agent, _step()))

    def test_playback_assertions_are_covered_too(self) -> None:
        agent = _agent([{'tag': 'img'}])
        self.assertTrue(self._missing(agent, _step(assert_kind='playback')))

    def test_a_step_that_expects_no_surface_is_never_flagged(self) -> None:
        agent = _agent([])
        for kind in ('element_state', 'text', 'collection', 'field_value'):
            with self.subTest(kind=kind):
                self.assertFalse(self._missing(agent, _step(assert_kind=kind)))

    def test_an_optional_assertion_does_not_trigger_it(self) -> None:
        agent = _agent([{'tag': 'img'}])
        self.assertFalse(self._missing(agent, _step(required=False)))

    def test_a_step_with_no_assertions_is_never_flagged(self) -> None:
        self.assertFalse(self._missing(_agent([]), {'assertions': []}))


class RetryGateTests(SimpleTestCase):
    def test_a_missing_surface_bypasses_the_visible_effect_check(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._retry_swallowed_action)
        # 「有变化」不等于「做到了该做的事」：缺少预期媒体面时，不能因为页面重绘了就放行。
        self.assertIn('missing_surface = await self._expected_media_surface_missing', source)
        self.assertIn('if not missing_surface:', source)
        gate = source[source.index('missing_surface ='):]
        self.assertIn('_action_had_visible_effect', gate)

    def test_the_log_says_which_condition_triggered_the_retry(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._retry_swallowed_action)
        self.assertIn('the step expects a playing media surface and there is none', source)
