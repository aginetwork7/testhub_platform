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