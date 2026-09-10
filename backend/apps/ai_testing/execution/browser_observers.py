"""Server-owned browser evidence observers selected by assertion contracts."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from io import BytesIO
from typing import Any, Protocol

from asgiref.sync import sync_to_async
from PIL import Image, ImageStat


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
        if progress is None:
            # No comparable native media element: the measured native progress is zero, which lets
            # playback/stream evaluation fall through to canvas or visual evidence instead of stalling.
            progress = 0.0
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
                has_visual_content = False
                target_visual_content = target.get('visual_content') if isinstance(target, Mapping) else None
                if visible and target_visual_content == 'image':
                    has_visual_content = bool(await locator.first.evaluate(
                        """element => [element, ...element.querySelectorAll('img, canvas, video, [style]')].some(candidate => {
                            if (candidate instanceof HTMLImageElement) return candidate.complete && candidate.naturalWidth > 1 && candidate.naturalHeight > 1;
                            if (candidate instanceof HTMLCanvasElement) return candidate.width > 1 && candidate.height > 1;
                            if (candidate instanceof HTMLVideoElement) return candidate.readyState >= 2 && candidate.videoWidth > 1 && candidate.videoHeight > 1;
                            return getComputedStyle(candidate).backgroundImage !== 'none';
                        })"""
                    ))
                visual_signal = None
                if has_visual_content:
                    visual_signal = measure_visual_signal(await locator.first.screenshot(type='png', timeout=5000))
                state_artifact = {
                    'type': 'collection_state' if assert_kind == 'collection' else 'element_state',
                    'locator': locator_text, 'count': count, 'visible': visible, 'text': str(text or ''),
                }
                if target_visual_content == 'image':
                    state_artifact['has_visual_content'] = has_visual_content
                    state_artifact['visual_signal'] = visual_signal
                artifacts.append(state_artifact)
            except Exception:
                continue
        return artifacts


class VisualFrameObserver:
    async def collect(self, page: Any, assertions: Sequence[Mapping[str, object]], context: BrowserObservationContext) -> list[dict[str, object]]:
        after = await capture_visual_frames(page, assertions)
        artifacts = [
            {'type': 'visual_frame_before', 'content_hash': frame['content_hash']}
            for frame in context.visual_frames_before
        ]
        artifacts.extend(
            {'type': 'visual_frame_after', 'content_hash': frame['content_hash']}
            for frame in after
        )
        if any(str(assertion.get('assert_kind') or '') == 'playback' for assertion in assertions):
            native_after = await NATIVE_MEDIA_OBSERVER.capture_state(page)
            visual_progress = None
            if not _native_playback_satisfies(assertions, context.native_media_before, native_after):
                visual_progress = await compare_playback_timestamps(context.visual_frames_before, after)
            if visual_progress is not None:
                artifacts.append({'type': 'playback_visual_progress', **visual_progress})
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
        ObserverDefinition(
            'visual_frame',
            ('visual_frame_before', 'visual_frame_after', 'playback_visual_progress'),
            ('visual_change', 'playback'),
        ),
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


async def capture_largest_media_frame(page: Any) -> bytes | None:
    """Screenshot the dominant visible player surface so only its burned-in clock is in view."""
    try:
        surfaces = page.locator('canvas, video')
        best = None
        best_area = 0.0
        for index in range(await surfaces.count()):
            candidate = surfaces.nth(index)
            if not await candidate.is_visible():
                continue
            box = await candidate.bounding_box()
            if not box or box['width'] < 160 or box['height'] < 90:
                continue
            area = float(box['width']) * float(box['height'])
            if area > best_area:
                best, best_area = candidate, area
        if best is None:
            return None
        return await best.screenshot(type='png', timeout=5000)
    except Exception:
        return None


async def capture_visual_frames(page: Any, assertions: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    kinds = {str(assertion.get('assert_kind') or '') for assertion in assertions}
    if not kinds.intersection({'visual_change', 'playback'}):
        return []
    frame = await capture_largest_media_frame(page) if 'playback' in kinds else None
    if frame is None:
        frame = await page.screenshot(type='png', full_page=False, timeout=10000)
    return [{
        'content_hash': hashlib.sha256(frame).hexdigest(),
        'image_url': f'data:image/png;base64,{base64.b64encode(frame).decode("ascii")}',
    }]


async def compare_playback_timestamps(
    before_frames: Sequence[Mapping[str, object]],
    after_frames: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    before_image = str(before_frames[0].get('image_url') or '') if before_frames else ''
    after_image = str(after_frames[0].get('image_url') or '') if after_frames else ''
    if not before_image or not after_image:
        return None

    from apps.ai_testing.models import AITestModelConfig, AITestPromptConfig
    from apps.core.llm import LLMCallContext, LLMClientError, OpenAICompatibleClient

    def load_configuration() -> tuple[object | None, str]:
        config = (
            AITestModelConfig.objects.filter(role='executor_vision', is_active=True).order_by('id').first()
            or AITestModelConfig.objects.filter(role='planner_vision', is_active=True).order_by('id').first()
        )
        prompt = (
            AITestPromptConfig.get_active_config('executor_vision')
            or AITestPromptConfig.get_active_config('planner_vision')
        )
        return config, str(prompt.content if prompt is not None else '')

    config, configured_prompt = await sync_to_async(load_configuration)()
    if config is None or not configured_prompt:
        return None
    messages = [
        {
            'role': 'system',
            'content': configured_prompt,
        },
        {
            'role': 'user',
            'content': [
                {
                    'type': 'text',
                    'text': (
                        'Assess playback advance only. Both images show the same video player surface: the first is before the action, the second is after. '
                        'Read the burned-in timestamp overlay (OSD clock) rendered inside the video picture itself; ignore list, timeline, or system-clock text outside the picture. '
                        'Return only JSON with before_time, after_time (24-hour HH:MM:SS), advanced_seconds, and confidence between 0 and 1; use low confidence when either clock is unreadable.'
                    ),
                },
                {'type': 'image_url', 'image_url': {'url': before_image}},
                {'type': 'image_url', 'image_url': {'url': after_image}},
            ],
        },
    ]
    try:
        response = await OpenAICompatibleClient.complete(
            config,
            messages,
            context=LLMCallContext(component='ai_testing', operation='playback_timestamp_evidence'),
            max_tokens=256,
            response_format={'type': 'json_object'},
        )
        payload = json.loads(str(response['choices'][0]['message']['content']).strip())
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, LLMClientError):
        return None
    return visual_timestamp_progress(payload)


def visual_timestamp_progress(payload: object) -> dict[str, object] | None:
    """Turn a model's before/after clock reading into signed playback progress."""
    if not isinstance(payload, Mapping):
        return None
    try:
        before_seconds = _timestamp_seconds(payload.get('before_time'))
        after_seconds = _timestamp_seconds(payload.get('after_time'))
        confidence = float(payload.get('confidence') or 0)
    except (TypeError, ValueError):
        return None
    if before_seconds is None or after_seconds is None or not 0 <= confidence <= 1:
        return None
    advanced_seconds = after_seconds - before_seconds
    # Only a clock that wrapped past midnight may be normalized; any other backwards
    # reading is a regression (or a misread) and must not count as progress.
    if advanced_seconds < 0 and before_seconds >= 23 * 60 * 60 and after_seconds <= 60 * 60:
        advanced_seconds += 24 * 60 * 60
    return {
        'before_time': str(payload.get('before_time')),
        'after_time': str(payload.get('after_time')),
        'advanced_seconds': advanced_seconds,
        'confidence': confidence,
    }


def _timestamp_seconds(value: object) -> int | None:
    match = re.search(r'(?<!\d)(\d{1,2}):(\d{2}):(\d{2})(?!\d)(?:\s*([AaPp][Mm]))?', str(value or '').strip())
    if match is None:
        return None
    hours, minutes, seconds = (int(part) for part in match.groups()[:3])
    meridiem = (match.group(4) or '').lower()
    if meridiem:
        if hours < 1 or hours > 12:
            return None
        hours = hours % 12 + (12 if meridiem == 'pm' else 0)
    if hours > 23 or minutes > 59 or seconds > 59:
        return None
    return hours * 3600 + minutes * 60 + seconds


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
                'visual_signal': measure_visual_signal(frame),
            })
        except Exception:
            continue
    return frames


def media_progress_seconds(before: Sequence[Mapping[str, object]], after: Sequence[Mapping[str, object]]) -> float | None:
    progress_values: list[float] = []
    for before_item, after_item in zip(before, after):
        try:
            progress_values.append(
                max(0.0, float(after_item.get('currentTime') or 0) - float(before_item.get('currentTime') or 0))
            )
        except (AttributeError, TypeError, ValueError):
            continue
    return max(progress_values) if progress_values else None


def measure_visual_signal(frame: bytes) -> bool:
    try:
        image = Image.open(BytesIO(frame)).convert('RGB').resize((64, 64))
        color_count = len(image.getcolors(maxcolors=4097) or [])
        average_deviation = sum(ImageStat.Stat(image).stddev) / 3
    except (OSError, ValueError):
        return False
    return color_count >= 256 and average_deviation >= 12


def _native_playback_satisfies(
    assertions: Sequence[Mapping[str, object]],
    before: object,
    after: Sequence[Mapping[str, object]],
) -> bool:
    if not isinstance(before, Sequence) or isinstance(before, (str, bytes)):
        return False
    minimums = [
        assertion.get('expected', {}).get('minimum_advanced_seconds')
        for assertion in assertions
        if assertion.get('assert_kind') == 'playback' and isinstance(assertion.get('expected'), Mapping)
    ]
    try:
        required_progress = max(float(value) for value in minimums)
    except (TypeError, ValueError):
        return False
    progress = media_progress_seconds(before, after)
    return (
        progress is not None
        and progress >= required_progress
        and any(not bool(item.get('paused', True)) for item in after)
    )


def _started_playing(before: Sequence[Mapping[str, object]], after: Sequence[Mapping[str, object]]) -> bool:
    return any(
        bool(before_item.get('paused', True)) and not bool(after_item.get('paused', True))
        for before_item, after_item in zip(before, after)
    )