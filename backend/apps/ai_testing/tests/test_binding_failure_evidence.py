"""绑定失败时记录当时页面上的候选控件，让「为什么没绑上」可以事后离线分析。"""

import asyncio

from django.test import SimpleTestCase

from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatAgent

CONTROLS = [
    {'name': 'Search site name...', 'role': 'searchbox', 'tag': 'input', 'selector': '#search',
     'rect': {'width': 300, 'height': 40}},
    {'name': 'Camera 5003_D13', 'role': 'button', 'tag': 'div', 'selector': '#cam13',
     'rect': {'width': 160, 'height': 90}, 'aria_expanded': ''},
    {'name': '萧山区', 'role': 'treeitem', 'tag': 'div', 'selector': '#group',
     'rect': {'width': 340, 'height': 32}, 'aria_expanded': 'false'},
    {'name': 'Confirm', 'role': 'button', 'tag': 'button', 'selector': '#ok',
     'rect': {'width': 80, 'height': 32}, 'top_layer': True},
]


class CandidateRankingTests(SimpleTestCase):
    rank = staticmethod(PyUICompatAgent._rank_candidates)

    def test_the_closest_control_comes_first(self) -> None:
        ranked = self.rank('site name search input', CONTROLS)
        self.assertEqual(ranked[0]['name'], 'Search site name...')
        self.assertEqual(ranked[0]['matched_tokens'], 3)

    def test_ranking_uses_subject_tokens_not_every_word(self) -> None:
        # "input" 是控件类型词，不参与计分；主语 site/name/search 命中三个。
        self.assertEqual(self.rank('site name search input', CONTROLS)[0]['matched_tokens'], 3)

    def test_an_unrelated_intent_still_returns_something_to_look_at(self) -> None:
        # 一个候选都不记，等于又回到只有断言那一侧的状态。
        ranked = self.rank('完全无关的东西', CONTROLS)
        self.assertEqual(len(ranked), len(CONTROLS))
        self.assertTrue(all(item['matched_tokens'] == 0 for item in ranked))

    def test_the_list_is_capped(self) -> None:
        many = [{'name': f'Control {i}', 'selector': f'#c{i}'} for i in range(60)]
        self.assertEqual(len(self.rank('control', many)), PyUICompatAgent.BINDING_FAILURE_CANDIDATES)

    def test_only_the_fields_binders_read_are_kept(self) -> None:
        # 产物会进数据库，不能把整页 DOM 塞进去。
        self.assertEqual(
            set(self.rank('site', CONTROLS)[0]),
            {'name', 'role', 'tag', 'selector', 'top_layer', 'aria_expanded', 'size', 'matched_tokens'},
        )

    def test_disclosure_state_survives_into_the_record(self) -> None:
        entry = next(item for item in self.rank('萧山区', CONTROLS) if item['selector'] == '#group')
        self.assertEqual(entry['aria_expanded'], 'false')
        self.assertEqual(entry['role'], 'treeitem')


class SnapshotTests(SimpleTestCase):
    def _agent(self, controls, media):
        agent = PyUICompatAgent.__new__(PyUICompatAgent)

        async def _controls(_page):
            return controls

        async def _media(_page):
            return media
        agent._build_actionable_controls = _controls
        agent._rendered_visual_elements = _media
        return agent

    def test_unnamed_controls_are_dropped(self) -> None:
        agent = self._agent([{'name': '  ', 'selector': '#x'}, {'name': 'Real', 'selector': '#y'}], [])
        snapshot = asyncio.run(agent._binding_failure_snapshot(None))
        self.assertEqual([c['name'] for c in snapshot['controls']], ['Real'])

    def test_the_media_census_counts_by_tag(self) -> None:
        agent = self._agent([], [{'tag': 'img'}, {'tag': 'img'}, {'tag': 'canvas'}])
        # 「observed=0 到底是没媒体还是没新增」曾经要靠临时加日志才问得出来。
        self.assertEqual(asyncio.run(agent._binding_failure_snapshot(None))['media'], {'img': 2, 'canvas': 1})

    def test_a_snapshot_failure_never_breaks_the_run(self) -> None:
        agent = PyUICompatAgent.__new__(PyUICompatAgent)

        async def _boom(_page):
            raise RuntimeError('page closed')
        agent._build_actionable_controls = _boom
        agent._rendered_visual_elements = _boom
        self.assertEqual(asyncio.run(agent._binding_failure_snapshot(None)), {'controls': [], 'media': {}})


class WiringTests(SimpleTestCase):
    def test_the_artifact_carries_candidates_and_media(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._run_deterministic_binders)
        self.assertIn("'candidates': self._rank_candidates(intent, page_snapshot['controls'])", source)
        self.assertIn("'media_inventory': page_snapshot['media']", source)

    def test_the_snapshot_is_taken_once_per_step(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._run_deterministic_binders)
        # 一个失败的步骤只付一次 DOM 遍历，通过的步骤一次都不付。
        self.assertIn('page_snapshot: dict | None = None', source)
        self.assertIn('if page_snapshot is None:', source)
