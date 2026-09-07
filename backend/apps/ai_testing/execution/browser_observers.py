"""Server-owned browser evidence observers selected by assertion contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from typing import Any, Protocol


class BrowserEvidenceObserver(Protocol):
    """Collect objective browser facts without making an assertion decision."""

    async def collect(self, page: Any, assertions: Sequence[Mapping[str, object]], context: 'BrowserObservationContext') -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class ObserverDefinition:
    name: str
    evidence_types: tuple[str, ...]
    assertion_kinds: tuple[str, ...]


@dataclass(frozen=True)
class BrowserObservationContext:
    native_media_before: object = None
    visual_frames_before: tuple[dict[str, object], ...] = ()
    canvas_frames_before: tuple[dict[str, object], ...] = ()
    download_events: tuple[dict[str, object], ...] = ()


class NativeMediaObserver:
    """Observe native audio/video state and objectively detected transitions."""

    async def capture_state(self, page: Any) -> list[dict[str, object]]:
        return await page.locator('video, audio').evaluate_all(
            """
            elements => elements.map(element => ({
                tag: element.tagName.toLowerCase(), paused: Boolean(element.paused),
                ended: Boolean(element.ended), readyState: Number(element.readyState),
                networkState: Number(element.networkState), currentTime: Number(element.currentTime),
                duration: Number.isFinite(element.duration) ? Number(element.duration) : null,
                videoWidth: Number(element.videoWidth || 0), videoHeight: Number(element.videoHeight || 0),
                currentSrc: String(element.currentSrc || element.src || ''),
            }))
            """
        )

    async def collect(self, page: Any, assertions: Sequence[Mapping[str, object]], context: BrowserObservationContext) -> list[dict[str, object]]:
        after_state = await self.capture_state(page)
        artifacts: list[dict[str, object]] = [{'type': 'media_state', 'elements': after_state}]
        if not isinstance(context.native_media_before, list):
            return artifacts
        artifacts.extend([
            {'type': 'media_state_before', 'elements': context.native_media_before},
            {'type': 'media_state_after', 'elements': after_state},
        ])
        progress = media_progress_seconds(context.native_media_before, after_state)
        if progress is not None:
            artifacts.append({'type': 'playback_time_progress', 'advanced_seconds': progress})
        if _started_playing(context.native_media_before, after_state):
            artifacts.append({'type': 'media_event', 'name': 'playing'})
        return artifacts


class DOMStateObserver:
    """Observe assertion targets through their runtime-discovered locators."""

    async def collect(self, page: Any, assertions: Sequence[Mapping[str, object]], context: BrowserObservationContext) -> list[dict[str, object]]:
        artifacts: list[dict[str, object]] = []
        for assertion in assertions:
            assert_kind = str(assertion.get('assert_kind') or '')
            if assert_kind not in {'field_value', 'popup', 'element_state', 'collection', 'absence', 'theme'}:
                continue
            if assert_kind == 'theme':
                state = await page.evaluate(
                    """() => {
                        const root = document.documentElement;
                        const body = document.body;
                        const tokens = [
                            root.getAttribute('data-theme'), body && body.getAttribute('data-theme'),
                            root.getAttribute('theme'), body && body.getAttribute('theme'),
                            root.className, body && body.className,
                        ].filter(Boolean).join(' ').toLowerCase();
                        let mode = /(^|[\\s_-])dark([\\s_-]|$)/.test(tokens) ? 'dark'
                            : /(^|[\\s_-])light([\\s_-]|$)/.test(tokens) ? 'light' : '';
                        const colorScheme = getComputedStyle(root).colorScheme.trim().toLowerCase();
                        if (!mode && (colorScheme === 'dark' || colorScheme === 'light')) {
                            mode = colorScheme;
                        }
                        const opaqueColor = (element) => {
                            for (let current = element; current; current = current.parentElement) {
                                const color = getComputedStyle(current).backgroundColor;
                                const channels = color.match(/[\\d.]+/g);
                                if (!channels || channels.length < 3) continue;
                                const alpha = channels.length >= 4 ? Number(channels[3]) : 1;
                                if (alpha <= 0.05) continue;
                                const luminance = (0.2126 * Number(channels[0]) + 0.7152 * Number(channels[1]) + 0.0722 * Number(channels[2])) / 255;
                                return {color, luminance};
                            }
                            return null;
                        };
                        const viewportWidth = Math.max(root.clientWidth, window.innerWidth || 0);
                        const viewportHeight = Math.max(root.clientHeight, window.innerHeight || 0);
                        const points = [
                            [16, viewportHeight * 0.2],
                            [16, viewportHeight * 0.5],
                            [16, viewportHeight * 0.8],
                            [viewportWidth * 0.5, 16],
                            [viewportWidth - 16, 16],
                        ];
                        const surfaces = points
                            .map(([x, y]) => opaqueColor(document.elementFromPoint(x, y)))
                            .filter(Boolean);
                        let backgroundColor = surfaces.length ? surfaces[0].color : '';
                        if (!mode) {
                            if (!surfaces.length) {
                                const documentSurface = opaqueColor(body || root);
                                if (documentSurface) {
                                    surfaces.push(documentSurface);
                                    backgroundColor = documentSurface.color;
                                }
                            }
                            const darkCount = surfaces.filter((surface) => surface.luminance < 0.5).length;
                            const lightCount = surfaces.length - darkCount;
                            if (darkCount !== lightCount) {
                                mode = darkCount > lightCount ? 'dark' : 'light';
                            }
                        }
                        return {mode, background_color: backgroundColor};
                    }"""
                )
                artifacts.append({'type': 'theme_state', **state})
                continue
            target = assertion.get('target')
            locator_value = target.get('locator') if isinstance(target, Mapping) else None
            if isinstance(locator_value, Mapping):
                locator_value = locator_value.get('value')
            locator_text = str(locator_value or '').strip()
            if not locator_text:
                continue
            try:
                locator = page.locator(locator_text)
                count = await locator.count()
                if assert_kind == 'absence':
                    artifacts.append({
                        'type': 'absence_check',
                        'locator': locator_text,
                        'exists': count > 0,
                    })
                    continue
                visible = bool(count and await locator.first.is_visible())
                if assert_kind == 'field_value':
                    value = await locator.first.evaluate(
                        """element => {
                            if ('value' in element && element.value != null) return String(element.value);
                            return String(element.getAttribute('aria-valuetext') || element.getAttribute('aria-label') || element.textContent || '').trim();
                        }"""
                    ) if visible else None
                    artifacts.append({'type': 'structured_value', 'locator': locator_text, 'value': value})
                    continue
                semantic_text = getattr(locator.first, 'evaluate', None)
                if visible and callable(semantic_text):
                    text = await semantic_text(
                        """element => {
                            const value = 'value' in element && element.value != null ? String(element.value).trim() : '';
                            return value || String(
                                element.getAttribute('aria-valuetext')
                                || element.getAttribute('aria-label')
                                || element.getAttribute('placeholder')
                                || element.textContent
                                || ''
                            ).trim();
                        }"""
                    )
                else:
                    text = await locator.first.text_content(timeout=3000) if visible else ''
                artifacts.append({
                    'type': 'collection_state' if assert_kind == 'collection' else 'element_state',
                    'locator': locator_text, 'count': count, 'visible': visible, 'text': str(text or ''),
                })
            except Exception:
                continue
        return artifacts


class VisualFrameObserver:
    async def collect(self, page: Any, assertions: Sequence[Mapping[str, object]], context: BrowserObservationContext) -> list[dict[str, object]]:
        after = await capture_visual_frames(page, assertions)
        artifacts = [{'type': 'visual_frame_before', **frame} for frame in context.visual_frames_before]
        artifacts.extend({'type': 'visual_frame_after', **frame} for frame in after)
        return artifacts


class CanvasStreamObserver:
    """Capture visible media-sized canvases used by WebRTC/WebGL players."""

    async def collect(self, page: Any, assertions: Sequence[Mapping[str, object]], context: BrowserObservationContext) -> list[dict[str, object]]:
        after = await capture_canvas_frames(page, assertions)
        artifacts = [{'type': 'canvas_frame_before', **frame} for frame in context.canvas_frames_before]
        artifacts.extend({'type': 'canvas_frame_after', **frame} for frame in after)
        return artifacts


class DownloadObserver:
    async def collect(self, page: Any, assertions: Sequence[Mapping[str, object]], context: BrowserObservationContext) -> list[dict[str, object]]:
        return [{'type': 'download_task_state', **event} for event in context.download_events]


NATIVE_MEDIA_OBSERVER = NativeMediaObserver()
DOM_STATE_OBSERVER = DOMStateObserver()
VISUAL_FRAME_OBSERVER = VisualFrameObserver()
CANVAS_STREAM_OBSERVER = CanvasStreamObserver()
DOWNLOAD_OBSERVER = DownloadObserver()
OBSERVERS: dict[str, tuple[ObserverDefinition, BrowserEvidenceObserver]] = {
    'native_media': (
        ObserverDefinition(
            'native_media',
            ('media_state', 'media_state_before', 'media_state_after', 'playback_time_progress', 'media_event'),
            ('media', 'video', 'stream_state', 'playback'),
        ),
        NATIVE_MEDIA_OBSERVER,
    ),
    'dom_state': (
        ObserverDefinition(
            'dom_state',
            ('structured_value', 'element_state', 'collection_state', 'absence_check', 'theme_state'),
            ('field_value', 'popup', 'element_state', 'collection', 'absence', 'theme'),
        ),
        DOM_STATE_OBSERVER,
    ),
    'visual_frame': (
        ObserverDefinition('visual_frame', ('visual_frame_before', 'visual_frame_after'), ('visual_change',)),
        VISUAL_FRAME_OBSERVER,
    ),
    'canvas_stream': (
        ObserverDefinition('canvas_stream', ('canvas_frame_before', 'canvas_frame_after'), ('stream_state',)),
        CANVAS_STREAM_OBSERVER,
    ),
    'download': (
        ObserverDefinition('download', ('download_task_state',), ('download_task',)),
        DOWNLOAD_OBSERVER,
    ),
}


def observer_names_for_assertions(assertions: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    kinds = {str(assertion.get('assert_kind') or '') for assertion in assertions}
    return tuple(name for name, (definition, _) in OBSERVERS.items() if kinds.intersection(definition.assertion_kinds))


async def collect_browser_observations(page: Any, assertions: Sequence[Mapping[str, object]], context: BrowserObservationContext) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    for name in observer_names_for_assertions(assertions):
        _, observer = OBSERVERS[name]
        artifacts.extend(await observer.collect(page, assertions, context))
    return artifacts


async def capture_visual_frames(page: Any, assertions: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if not any(str(assertion.get('assert_kind') or '') == 'visual_change' for assertion in assertions):
        return []
    frame = await page.screenshot(type='png', full_page=False, timeout=10000)
    return [{'content_hash': hashlib.sha256(frame).hexdigest()}]


async def capture_canvas_frames(page: Any, assertions: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if not any(str(assertion.get('assert_kind') or '') == 'stream_state' for assertion in assertions):
        return []
    canvases = page.locator('canvas')
    frames: list[dict[str, object]] = []
    for index in range(await canvases.count()):
        canvas = canvases.nth(index)
        try:
            if not await canvas.is_visible():
                continue
            box = await canvas.bounding_box()
            if not box or box['width'] < 160 or box['height'] < 90:
                continue
            frame = await canvas.screenshot(type='png', timeout=5000)
            frames.append({
                'index': index,
                'width': box['width'],
                'height': box['height'],
                'content_hash': hashlib.sha256(frame).hexdigest(),
            })
        except Exception:
            continue
    return frames


def media_progress_seconds(before: Sequence[Mapping[str, object]], after: Sequence[Mapping[str, object]]) -> float | None:
    for before_item, after_item in zip(before, after):
        try:
            return max(0.0, float(after_item.get('currentTime') or 0) - float(before_item.get('currentTime') or 0))
        except (AttributeError, TypeError, ValueError):
            continue
    return None


def _started_playing(before: Sequence[Mapping[str, object]], after: Sequence[Mapping[str, object]]) -> bool:
    return any(
        bool(before_item.get('paused', True)) and not bool(after_item.get('paused', True))
        for before_item, after_item in zip(before, after)
    )