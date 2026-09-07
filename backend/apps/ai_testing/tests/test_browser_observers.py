import asyncio
import unittest

from apps.ai_testing.execution.browser_observers import (
    BrowserObservationContext,
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
    def test_native_media_observer_is_selected_for_playback_assertion(self) -> None:
        names = observer_names_for_assertions([{'assert_kind': 'playback'}])

        self.assertEqual(names, ('native_media',))

    def test_native_media_observer_records_progress_and_playing_transition(self) -> None:
        artifacts = asyncio.run(collect_browser_observations(
            _MediaPage(), [{'assert_kind': 'playback'}],
            BrowserObservationContext(native_media_before=[{'paused': True, 'currentTime': 10, 'readyState': 1}]),
        ))

        self.assertIn({'type': 'media_event', 'name': 'playing'}, artifacts)
        self.assertIn({'type': 'playback_time_progress', 'advanced_seconds': 3.0}, artifacts)

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