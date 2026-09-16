"""Behaviour tests for the in-page discovery scripts, run against static HTML in real Chromium.

These complement the source-string tests: they prove what the injected JavaScript actually
returns for anchored selectors, single-item groups, rendered images and dialog layers.
"""

import asyncio
import unittest

from django.test import SimpleTestCase

from apps.ai_testing.runtime.pyui_compat.runner import RENDERED_VISUAL_ELEMENTS_JS, PyUICompatAgent

TINY_PNG = (
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR42mP8z8DwHwyBGARhBgYGAA+2A/1p5aVXAAAAAElFTkSuQmCC'
)

PAGE = f"""
<html><head><title>Discovery Fixture</title></head>
<body style="margin:0">
  <div id="root">
    <nav><a href="/dashboard/home" style="display:block;width:120px;height:24px">Home</a></nav>
    <ul class="results">
      <li class="row" style="height:24px">Only result</li>
    </ul>
    <div class="cards">
      <div class="card" style="width:200px;height:60px">Card one</div>
      <div class="card" style="width:200px;height:60px">Card two</div>
    </div>
    <img id="hero" src="{TINY_PNG}" width="120" height="80" alt="">
    <span style="display:inline-block;width:80px;height:20px">Plain text</span>
  </div>
  <div class="portal-root">
    <div role="dialog" aria-modal="true" style="position:fixed;top:100px;left:100px;width:600px;height:400px;background:#fff;z-index:1000">
      <h2 style="height:30px">Confirm download</h2>
      <button type="button" style="width:100px;height:32px">Cancel</button>
      <button type="button" style="width:100px;height:32px">Download</button>
    </div>
  </div>
</body></html>
"""


def _chromium_available():
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(_chromium_available(), 'playwright is not installed')
class DomDiscoveryBehaviourTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = PyUICompatAgent(case_name='Discovery_Fixture')
        try:
            cls.snapshot = asyncio.run(cls._discover())
        except Exception as error:  # browser missing in this environment
            raise unittest.SkipTest(f'chromium unavailable: {error}')

    @classmethod
    async def _discover(cls):
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            page = await browser.new_page(viewport={'width': 1200, 'height': 800})
            await page.set_content(PAGE)
            await page.wait_for_timeout(200)
            controls = await cls.agent._build_actionable_controls(page)
            observables = await cls.agent._build_observable_elements(page)
            rendered = await page.evaluate(RENDERED_VISUAL_ELEMENTS_JS)
            await browser.close()
        return {'controls': controls, 'observables': observables, 'rendered': rendered}

    def _control(self, name):
        return next(control for control in self.snapshot['controls'] if control.get('name') == name)

    def test_structural_selectors_anchor_on_unique_ids_and_body_level_classes(self):
        card = next(item for item in self.snapshot['observables'] if item.get('text') == 'Card one' and item.get('tag') == 'div')
        self.assertTrue(card['selector'].startswith('#root > '), card['selector'])
        self.assertNotIn('body > div:nth-of-type', card['selector'])

        title = next(item for item in self.snapshot['observables'] if item.get('text') == 'Confirm download')
        self.assertTrue(title['selector'].startswith('body > div.portal-root > '), title['selector'])

    def test_single_item_lists_still_get_a_group_selector(self):
        row = next(item for item in self.snapshot['observables'] if item.get('text') == 'Only result' and item.get('tag') == 'li')
        self.assertEqual(row['group_size'], 1)
        self.assertTrue(row['group_selector'].endswith('> li.row'), row['group_selector'])

        card = next(item for item in self.snapshot['observables'] if item.get('text') == 'Card one' and item.get('tag') == 'div')
        self.assertEqual(card['group_size'], 2)

    def test_rendered_image_is_discoverable_without_text(self):
        hero = next(item for item in self.snapshot['observables'] if item.get('selector') == '#hero')
        self.assertTrue(hero['has_visual_content'])
        self.assertEqual([item['selector'] for item in self.snapshot['rendered']], ['#hero'])
        self.assertFalse(self.snapshot['rendered'][0]['top_layer'])

    def test_dialog_controls_are_flagged_as_dialog_layer(self):
        download = self._control('Download')
        self.assertTrue(download['blocking_layer'])
        self.assertTrue(download['dialog_layer'])
        self.assertTrue(download['top_layer'])
        self.assertTrue(download['blocking_layer_id'].startswith('body > div.portal-root'), download['blocking_layer_id'])

        home = self._control('Home')
        self.assertFalse(home['blocking_layer'])
        self.assertEqual(home['selector'], '[href="/dashboard/home"]')
