from __future__ import annotations

import argparse
import json
import logging
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import quote

from playwright.sync_api import Browser, Playwright, sync_playwright


LOGGER = logging.getLogger(__name__)
HEVC_CONTENT_TYPE = 'video/mp4; codecs="hvc1.1.6.L93.B0"'


class ProbeEvidence(TypedDict):
    browser_version: str
    can_play_type: str
    media_capabilities_supported: bool
    ready_state: int
    current_time: float
    video_width: int
    video_height: int
    error_code: int | None
    error_message: str | None
    passed: bool


class QuietRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        LOGGER.debug(format, *args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Verify Chromium HEVC playback without transcoding.')
    parser.add_argument('--browser', type=Path, required=True)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    return parser.parse_args()


def run_probe(playwright: Playwright, browser_path: Path, media_path: Path) -> ProbeEvidence:
    handler = partial(QuietRequestHandler, directory=str(media_path.parent))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    browser: Browser | None = None

    try:
        browser = playwright.chromium.launch(
            executable_path=str(browser_path),
            headless=True,
            args=[
                '--no-sandbox',
                '--autoplay-policy=no-user-gesture-required',
            ],
        )
        page = browser.new_page()
        media_url = f'http://127.0.0.1:{server.server_port}/{quote(media_path.name)}'
        result = page.evaluate(
            """
            async ({mediaUrl, contentType}) => {
                const video = document.createElement('video');
                video.muted = true;
                video.src = mediaUrl;
                document.body.append(video);

                const capability = await navigator.mediaCapabilities.decodingInfo({
                    type: 'file',
                    video: {
                        contentType,
                        width: 352,
                        height: 288,
                        bitrate: 200000,
                        framerate: 25,
                    },
                });
                const loadResult = await new Promise((resolve) => {
                    const timeout = setTimeout(
                        () => resolve({timedOut: true}),
                        15000,
                    );
                    video.addEventListener('loadeddata', () => {
                        clearTimeout(timeout);
                        resolve({timedOut: false});
                    }, {once: true});
                    video.addEventListener('error', () => {
                        clearTimeout(timeout);
                        resolve({timedOut: false});
                    }, {once: true});
                    video.load();
                });

                if (!video.error && !loadResult.timedOut) {
                    await video.play();
                    await new Promise((resolve) => setTimeout(resolve, 1500));
                }

                return {
                    can_play_type: video.canPlayType(contentType),
                    media_capabilities_supported: capability.supported,
                    ready_state: video.readyState,
                    current_time: video.currentTime,
                    video_width: video.videoWidth,
                    video_height: video.videoHeight,
                    error_code: video.error?.code ?? null,
                    error_message: video.error?.message ?? null,
                };
            }
            """,
            {'mediaUrl': media_url, 'contentType': HEVC_CONTENT_TYPE},
        )
        evidence = cast(ProbeEvidence, result)
        evidence['browser_version'] = browser.version
        evidence['passed'] = (
            evidence['error_code'] is None
            and evidence['ready_state'] >= 2
            and evidence['current_time'] >= 0.5
            and evidence['video_width'] > 0
            and evidence['video_height'] > 0
        )
        return evidence
    finally:
        if browser is not None:
            browser.close()
        server.shutdown()
        server.server_close()
        server_thread.join()


def main() -> int:
    args = parse_args()
    browser_path = args.browser.resolve(strict=True)
    media_path = args.media.resolve(strict=True)
    evidence_path = args.evidence.resolve()

    with sync_playwright() as playwright:
        evidence = run_probe(playwright, browser_path, media_path)

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding='utf-8')
    LOGGER.info('HEVC playback evidence written to %s', evidence_path)
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    raise SystemExit(main())