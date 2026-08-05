from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from pathlib import Path
import re
import time
import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit


logger = logging.getLogger(__name__)


class CameraWorkflowCapabilities:
    """Deterministic Site/Camera workflow capabilities for the Alpha Vision UI."""

    def __init__(self, page: Any) -> None:
        self._page = page
        self._ocr_reader: Any | None = None

    async def open_camera_list(self, timeout_ms: int) -> None:
        current_url = str(self._page.url or '')
        parsed = urlsplit(current_url)
        if not parsed.scheme or not parsed.netloc:
            raise AssertionError('cannot derive the application origin for Cameras navigation')
        cameras_url = urlunsplit((parsed.scheme, parsed.netloc, '/dashboard/streaming', '', ''))
        await self._page.goto(cameras_url, wait_until='domcontentloaded', timeout=timeout_ms)
        await self.assert_site_list(timeout_ms)

    async def assert_site_list(self, timeout_ms: int) -> None:
        deadline = time.monotonic() + max(timeout_ms, 1000) / 1000.0
        while time.monotonic() < deadline:
            site_buttons = self._page.locator("#btnSite, [class*='site-item'], [class*='site'] [class*='item']")
            for index in range(await site_buttons.count()):
                candidate = site_buttons.nth(index)
                try:
                    if not await candidate.is_visible(timeout=300):
                        continue
                    text = str(await candidate.text_content() or '')
                    if re.search(r'\d+\s*/\s*\d+', text):
                        return
                except Exception:
                    continue
            await self._page.wait_for_timeout(300)
        raise AssertionError('no visible Site item with camera online/offline counts was found')

    async def select_site_with_online_cameras(self, timeout_ms: int) -> None:
        site_buttons = self._page.locator("#btnSite, [class*='site-item'], [class*='site'] [class*='item']")
        for index in range(await site_buttons.count()):
            candidate = site_buttons.nth(index)
            try:
                if not await candidate.is_visible(timeout=300):
                    continue
                text = str(await candidate.text_content() or '').replace('\n', ' ').strip()
                match = re.search(r'(?P<online>\d+)\s*/\s*(?P<offline>\d+)', text)
                if match and int(match.group('online')) > 0:
                    await candidate.click(timeout=timeout_ms)
                    await self._page.wait_for_timeout(600)
                    await self.assert_camera_list(timeout_ms)
                    return
            except Exception:
                continue
        raise AssertionError('no Site with online cameras was found')

    async def assert_camera_list(self, timeout_ms: int) -> None:
        cards = self._camera_cards()
        for index in range(await cards.count()):
            candidate = cards.nth(index)
            try:
                if await candidate.is_visible(timeout=300):
                    box = await candidate.bounding_box()
                    if box and box['width'] >= 40 and box['height'] >= 20:
                        return
            except Exception:
                continue
        raise AssertionError('no visible Camera card was found under the selected Site')

    async def select_online_camera(self, timeout_ms: int) -> None:
        cards = self._camera_cards()
        for index in range(await cards.count()):
            candidate = cards.nth(index)
            try:
                if not await candidate.is_visible(timeout=300):
                    continue
                is_online = await candidate.evaluate(
                    """
                    element => {
                      const nodes = [element, ...element.querySelectorAll('*')];
                      return nodes.some(node => {
                        const className = String(node.className || '').toLowerCase();
                        if (/(online|status-green|bg-green|text-green)/.test(className)) return true;
                        const styles = getComputedStyle(node);
                        return [styles.color, styles.backgroundColor, styles.fill, styles.stroke, styles.borderColor].some(color => {
                          const match = color.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
                          return match && Number(match[2]) > Number(match[1]) * 1.15 && Number(match[2]) > Number(match[3]) * 1.15;
                        });
                      });
                    }
                    """
                )
                if is_online:
                    await candidate.click(timeout=timeout_ms)
                    return
            except Exception:
                continue
        raise AssertionError('no visible online Camera card was found')

    async def seek_forward_ten_seconds(self, timeout_ms: int) -> dict[str, str]:
        player = self._page.locator('#playerContainer canvas').first
        before_screenshot = await self._capture_player_screenshot(player)
        buttons = self._page.locator('#playerContainer').locator('xpath=..').locator('button')
        deadline = time.monotonic() + max(timeout_ms, 1000) / 1000.0
        while time.monotonic() < deadline:
            if await buttons.count() >= 10:
                break
            await self._page.wait_for_timeout(250)
        if await buttons.count() < 10:
            raise AssertionError('Playback toolbar did not finish loading')
        for index in range(await buttons.count()):
            button = buttons.nth(index)
            try:
                if not await button.is_visible(timeout=200):
                    continue
                await button.hover(timeout=timeout_ms)
                await self._page.wait_for_timeout(100)
                tooltips = self._page.locator('#playerContainer [role="tooltip"], [role="tooltip"]')
                has_forward_tooltip = False
                for tooltip_index in range(await tooltips.count()):
                    tooltip = tooltips.nth(tooltip_index)
                    try:
                        if await tooltip.is_visible(timeout=100) and str(await tooltip.inner_text() or '').strip() == '10s Forward':
                            has_forward_tooltip = True
                            break
                    except Exception:
                        continue
                if not has_forward_tooltip:
                    continue
                await button.click(timeout=timeout_ms)
                await self._page.wait_for_timeout(2000)
                after_screenshot = await self._capture_player_screenshot(player)
                return {
                    'before_screenshot': before_screenshot,
                    'after_screenshot': after_screenshot,
                    **self._save_playback_evidence(before_screenshot, after_screenshot),
                }
            except AssertionError:
                raise
            except Exception:
                continue
        raise AssertionError('10s Forward control was not found')

    async def assert_playback_loaded(self, timeout_ms: int) -> None:
        deadline = time.monotonic() + max(timeout_ms, 1000) / 1000.0
        while time.monotonic() < deadline:
            loading = 'Loading streaming...' in str(await self._page.locator('body').inner_text())
            canvas = self._page.locator('#playerContainer canvas')
            toolbar = self._page.locator('#playerContainer').locator('xpath=..').locator('button')
            if not loading and await canvas.count() and await toolbar.count() >= 10:
                if await canvas.first.is_visible(timeout=200):
                    return
            await self._page.wait_for_timeout(300)
        raise AssertionError('Playback page did not finish loading media and toolbar')

    @staticmethod
    def _save_playback_evidence(before_screenshot: str, after_screenshot: str) -> dict[str, str]:
        from django.conf import settings

        directory = Path(settings.MEDIA_ROOT) / 'ai_testing' / 'playback_evidence'
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        paths = {}
        for label, screenshot in (('before', before_screenshot), ('after', after_screenshot)):
            payload = screenshot.split(',', 1)[1]
            path = directory / f'forward_{timestamp}_{label}.png'
            path.write_bytes(base64.b64decode(payload))
            paths[f'{label}_path'] = str(path.relative_to(Path(settings.MEDIA_ROOT))).replace('\\', '/')
        return paths

    async def _capture_player_screenshot(self, player: Any) -> str:
        box = await player.bounding_box()
        if not box:
            media = self._page.locator('#playerContainer canvas, #playerContainer img, #playerContainer video')
            for index in range(await media.count()):
                candidate = media.nth(index)
                if not await candidate.is_visible(timeout=200):
                    continue
                candidate_box = await candidate.bounding_box()
                if candidate_box and candidate_box['width'] >= 600 and candidate_box['height'] >= 320:
                    box = candidate_box
                    break
        if not box:
            raise AssertionError('Playback media surface is unavailable for visual evidence')
        image_bytes = await self._page.screenshot(
            type='png',
            clip={'x': box['x'], 'y': box['y'], 'width': box['width'], 'height': box['height']},
        )
        return f'data:image/png;base64,{base64.b64encode(image_bytes).decode("ascii")}'

    async def _read_burned_timestamp(self, player: Any) -> float | None:
        try:
            from io import BytesIO

            import easyocr
            import numpy as np
            from PIL import Image

            box = await player.bounding_box()
            if not box:
                media = self._page.locator('img, canvas, video')
                for index in range(await media.count()):
                    candidate = media.nth(index)
                    if not await candidate.is_visible(timeout=200):
                        continue
                    candidate_box = await candidate.bounding_box()
                    if candidate_box and candidate_box['width'] >= 600 and candidate_box['height'] >= 320:
                        box = candidate_box
                        break
            if not box:
                logger.warning('playback timestamp OCR found no visible media surface')
                return None
            clip = {
                'x': box['x'],
                'y': box['y'],
                'width': box['width'],
                'height': min(box['height'] * 0.28, 220),
            }
            image_bytes = await self._page.screenshot(type='png', clip=clip)
            if self._ocr_reader is None:
                self._ocr_reader = await asyncio.to_thread(easyocr.Reader, ['en'], False)
            image = Image.open(BytesIO(image_bytes))
            timestamp_region = image.crop((0, 0, int(image.width * 0.45), int(image.height * 0.7)))
            image = np.array(timestamp_region.resize((timestamp_region.width * 2, timestamp_region.height * 2)))
            results = await asyncio.to_thread(self._ocr_reader.readtext, image, detail=0)
            text = ' '.join(str(item) for item in results)
            match = re.search(r'(\d{1,2})[\s:.]+(\d{2})[\s:.]+(\d{2})', text)
            if not match:
                logger.warning('playback timestamp OCR found no time in text: %s', text)
                return None
            hours, minutes, seconds = (int(value) for value in match.groups())
            return float(hours * 3600 + minutes * 60 + seconds)
        except Exception as error:
            logger.warning('playback timestamp OCR failed: %s', error)
            return None

    def _camera_cards(self) -> Any:
        return self._page.locator(
            "div[class*='grid'] > div, div[class*='grid'] > button, "
            "[class*='camera-item'], [class*='camera'] [class*='preview']"
        )
