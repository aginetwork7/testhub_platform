import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from apps.ai_testing.execution.browser_observers import (
    BrowserObservationContext,
    _timestamp_seconds,
    capture_visual_frames,
    collect_browser_observations,
    observer_names_for_assertions,
)


class _MediaLocator:
    async def evaluate_all(self, _script):
        return [{'paused': False, 'currentTime': 13, 'readyState': 4}]


class _MediaPage:
    def locator(self, _selector):
        return _MediaLocator()

    async def screenshot(self, **_kwargs):
        return b'visual-frame'


class _MultipleMediaLocator:
    async def evaluate_all(self, _script):
        return [
            {'tag': 'video', 'paused': True, 'currentTime': 0, 'readyState': 0},
            {'tag': 'audio', 'paused': False, 'currentTime': 417.804, 'readyState': 4},
        ]


class _MultipleMediaPage(_MediaPage):
    def locator(self, _selector):
        return _MultipleMediaLocator()


class _CanvasElement:
    def __init__(self, frame: bytes) -> None:
        self._frame = frame

    async def is_visible(self) -> bool:
        return True

    async def bounding_box(self) -> dict[str, float]:
        return {'x': 10, 'y': 20, 'width': 640, 'height': 360}

    async def screenshot(self, **_kwargs) -> bytes:
        return self._frame

    async def get_attribute(self, _name: str) -> None:
        return None


class _CanvasLocator:
    def __init__(self, frames: list[bytes]) -> None:
        self._frames = frames

    async def count(self) -> int:
        return len(self._frames)

    def nth(self, index: int) -> _CanvasElement:
        return _CanvasElement(self._frames[index])


class _CanvasPage(_MediaPage):
    def __init__(self, frames: list[bytes]) -> None:
        self._frames = frames

    def locator(self, selector: str):
        if selector == 'canvas':
            return _CanvasLocator(self._frames)
        return _MediaLocator()


class _FieldLocator:
    async def count(self):
        return 1

    async def is_visible(self):
        return True

    async def text_content(self, **_kwargs):
        return 'Other'

    async def evaluate(self, _script):
        return 'Other'

    @property
    def first(self):
        return self


class _FieldPage:
    def locator(self, _selector):
        return _FieldLocator()


class _SemanticInputLocator(_FieldLocator):
    async def text_content(self, **_kwargs):
        return ''

    async def evaluate(self, _script):
        return 'Magic Search V2'


class _SemanticInputPage:
    def locator(self, _selector):
        return _SemanticInputLocator()


class _AbsentLocator:
    async def count(self):
        return 0


class _AbsentPage:
    def locator(self, _selector):
        return _AbsentLocator()


class _ThemePage:
    script = ''

    async def evaluate(self, _script):
        self.script = _script
        return {'mode': 'dark', 'background_color': 'rgb(20, 20, 20)'}


class BrowserObserverTests(unittest.TestCase):
    def test_timestamp_parser_accepts_valid_time_and_rejects_invalid_time(self) -> None:
        self.assertEqual(_timestamp_seconds('12:02:21'), 43341)
        self.assertEqual(_timestamp_seconds('2026-09-10 11:36:05'), 41765)
        self.assertEqual(_timestamp_seconds('1:02:03 PM'), 46923)
        self.assertEqual(_timestamp_seconds('12:00:00 AM'), 0)
        self.assertIsNone(_timestamp_seconds('12:99:21'))
        self.assertIsNone(_timestamp_seconds('11:36'))
        self.assertIsNone(_timestamp_seconds('not-a-time'))

    def test_visual_timestamp_progress_never_wraps_a_backwards_reading(self) -> None:
        from apps.ai_testing.execution.browser_observers import visual_timestamp_progress

        backwards = visual_timestamp_progress({'before_time': '11:07:53', 'after_time': '11:00:30', 'confidence': 0.9})
        forward = visual_timestamp_progress({'before_time': '11:00:30', 'after_time': '11:00:41', 'confidence': 0.9})
        midnight = visual_timestamp_progress({'before_time': '23:59:55', 'after_time': '00:00:07', 'confidence': 0.9})

        self.assertEqual(backwards['advanced_seconds'], -443)
        self.assertEqual(forward['advanced_seconds'], 11)
        self.assertEqual(midnight['advanced_seconds'], 12)
        self.assertIsNone(visual_timestamp_progress({'before_time': '11:00', 'after_time': '11:00:41', 'confidence': 0.9}))
        self.assertIsNone(visual_timestamp_progress({'before_time': '11:00:30', 'after_time': '11:00:41', 'confidence': 1.5}))
        self.assertIsNone(visual_timestamp_progress('not a payload'))

    def test_native_media_observer_reports_zero_progress_without_comparable_media(self) -> None:
        from apps.ai_testing.execution.browser_observers import BrowserObservationContext, NativeMediaObserver

        class _EmptyMediaPage:
            def locator(self, selector):
                async def evaluate_all(script):
                    return []
                return SimpleNamespace(evaluate_all=evaluate_all)

        artifacts = asyncio.run(NativeMediaObserver().collect(
            _EmptyMediaPage(),
            [{'assert_kind': 'stream_state'}],
            BrowserObservationContext(native_media_before=[]),
        ))

        self.assertIn({'type': 'playback_time_progress', 'advanced_seconds': 0.0}, artifacts)

    def test_playback_visual_frame_prefers_largest_visible_player_surface(self) -> None:
        from apps.ai_testing.execution.browser_observers import capture_largest_media_frame

        class _Surface:
            def __init__(self, visible, box, frame):
                self._visible, self._box, self._frame = visible, box, frame

            async def is_visible(self):
                return self._visible

            async def bounding_box(self):
                return self._box

            async def screenshot(self, **kwargs):
                return self._frame

        surfaces = [
            _Surface(True, {'width': 100, 'height': 60}, b'tiny'),
            _Surface(False, {'width': 1900, 'height': 900}, b'hidden'),
            _Surface(True, {'width': 1242, 'height': 698}, b'player'),
            _Surface(True, {'width': 320, 'height': 180}, b'thumb'),
        ]

        class _Locator:
            async def count(self):
                return len(surfaces)

            def nth(self, index):
                return surfaces[index]

        page = SimpleNamespace(locator=lambda selector: _Locator())

        self.assertEqual(asyncio.run(capture_largest_media_frame(page)), b'player')
        self.assertIsNone(asyncio.run(capture_largest_media_frame(SimpleNamespace())))

    def test_native_media_observer_is_selected_for_playback_assertion(self) -> None:
        names = observer_names_for_assertions([{'assert_kind': 'playback'}])

        self.assertEqual(names, ('native_media', 'visual_frame'))

    def test_native_media_observer_records_progress_and_playing_transition(self) -> None:
        artifacts = asyncio.run(collect_browser_observations(
            _MediaPage(), [{'assert_kind': 'playback'}],
            BrowserObservationContext(native_media_before=[{'paused': True, 'currentTime': 10, 'readyState': 1}]),
        ))

        self.assertIn({'type': 'media_event', 'name': 'playing'}, artifacts)
        self.assertIn({'type': 'playback_time_progress', 'advanced_seconds': 3.0}, artifacts)

    def test_native_media_observer_uses_largest_progress_across_media_elements(self) -> None:
        artifacts = asyncio.run(collect_browser_observations(
            _MultipleMediaPage(),
            [{'assert_kind': 'playback'}],
            BrowserObservationContext(native_media_before=[
                {'tag': 'video', 'paused': True, 'currentTime': 0, 'readyState': 0},
                {'tag': 'audio', 'paused': False, 'currentTime': 380.706, 'readyState': 4},
            ]),
        ))

        progress = next(
            artifact['advanced_seconds']
            for artifact in artifacts
            if artifact['type'] == 'playback_time_progress'
        )
        self.assertAlmostEqual(progress, 37.098)

    def test_stream_observer_records_visible_canvas_frames(self) -> None:
        artifacts = asyncio.run(collect_browser_observations(
            _CanvasPage([b'live-frame']),
            [{'assert_kind': 'stream_state'}],
            BrowserObservationContext(canvas_frames_before=({'index': 0, 'content_hash': 'before'},)),
        ))

        self.assertIn({'type': 'canvas_frame_before', 'index': 0, 'content_hash': 'before'}, artifacts)
        self.assertIn('canvas_frame_after', {artifact['type'] for artifact in artifacts})

    def test_visual_frame_capture_returns_content_hash_only_for_visual_assertions(self) -> None:
        frames = asyncio.run(capture_visual_frames(_MediaPage(), [{'assert_kind': 'visual_change'}]))

        self.assertEqual(len(frames), 1)
        self.assertEqual(len(frames[0]['content_hash']), 64)
        self.assertTrue(frames[0]['image_url'].startswith('data:image/png;base64,'))

    def test_playback_observer_records_visual_timestamp_progress(self) -> None:
        assertion = {
            'assert_kind': 'playback',
            'expected': {'minimum_advanced_seconds': 10},
        }
        context = BrowserObservationContext(
            native_media_before=[{'paused': False, 'currentTime': 13}],
            visual_frames_before=({
                'content_hash': 'before',
                'image_url': 'data:image/png;base64,before',
            },),
        )

        with patch(
            'apps.ai_testing.execution.browser_observers.compare_playback_timestamps',
            new=AsyncMock(return_value={
                'before_time': '12:00:00',
                'after_time': '12:00:10',
                'advanced_seconds': 10,
                'confidence': 0.95,
            }),
        ):
            artifacts = asyncio.run(collect_browser_observations(_MediaPage(), [assertion], context))

        self.assertIn('playback_visual_progress', {artifact['type'] for artifact in artifacts})
        before_artifact = next(artifact for artifact in artifacts if artifact['type'] == 'visual_frame_before')
        self.assertNotIn('image_url', before_artifact)

    def test_download_observer_uses_completed_download_event(self) -> None:
        artifacts = asyncio.run(collect_browser_observations(
            _MediaPage(), [{'assert_kind': 'download_task'}],
            BrowserObservationContext(download_events=({'status': 'completed', 'filename': 'report.zip'},)),
        ))

        self.assertEqual(artifacts, [{'type': 'download_task_state', 'status': 'completed', 'filename': 'report.zip'}])

    def test_dom_observer_collects_bound_field_value(self) -> None:
        artifacts = asyncio.run(collect_browser_observations(
            _FieldPage(),
            [{'assert_kind': 'field_value', 'target': {'locator': '[data-field="category"]'}}],
            BrowserObservationContext(),
        ))

        self.assertEqual(artifacts, [{
            'type': 'structured_value',
            'locator': '[data-field="category"]',
            'value': 'Other',
        }])

    def test_dom_observer_collects_semantic_text_for_input_element_state(self) -> None:
        artifacts = asyncio.run(collect_browser_observations(
            _SemanticInputPage(),
            [{'assert_kind': 'element_state', 'target': {'locator': '#search-mode'}}],
            BrowserObservationContext(),
        ))

        self.assertEqual(artifacts, [{
            'type': 'element_state',
            'locator': '#search-mode',
            'count': 1,
            'visible': True,
            'text': 'Magic Search V2',
        }])

    def test_dom_observer_collects_bound_absence(self) -> None:
        artifacts = asyncio.run(collect_browser_observations(
            _AbsentPage(),
            [{
                'assert_kind': 'absence',
                'target': {'locator': '#closed-player'},
            }],
            BrowserObservationContext(),
        ))

        self.assertEqual(artifacts, [{
            'type': 'absence_check',
            'locator': '#closed-player',
            'exists': False,
        }])

    def test_dom_observer_collects_theme_state_without_locator(self) -> None:
        page = _ThemePage()

        artifacts = asyncio.run(collect_browser_observations(
            page,
            [{'assert_kind': 'theme', 'target': {'page': 'current'}}],
            BrowserObservationContext(),
        ))

        self.assertEqual(artifacts, [{
            'type': 'theme_state',
            'mode': 'dark',
            'background_color': 'rgb(20, 20, 20)',
        }])
        self.assertIn('alpha <= 0.05', page.script)
        self.assertIn('document.elementFromPoint', page.script)