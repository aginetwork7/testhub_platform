"""存在性断言 expected 的归一，以及并列候选的嵌套消歧。"""

from django.test import SimpleTestCase

from apps.ai_testing.execution.assertion_registry import parse_assertion
from apps.ai_testing.execution.intent_text import expects_true
from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatAgent


def _existence_assertion(expected_value, operator='exists'):
    return {
        'action': 'assert',
        'assert_kind': 'element_state',
        'operator': operator,
        'expected': {'value': expected_value},
        'target': {'intent': 'thumbnail on the camera 5003_D13 icon'},
        'required': True,
        'evidence_requirements': ['element_state'],
    }


class ExistenceExpectedNormalisationTests(SimpleTestCase):
    """契约层把 True、"true"、空串归一为同一个值，绑定器才不会因写法不同而放弃。"""

    def test_the_three_written_forms_normalise_to_one(self) -> None:
        values = [parse_assertion(_existence_assertion(raw)).expected['value'] for raw in (True, 'true', '')]
        self.assertEqual(values, [True, True, True])

    def test_an_empty_expected_no_longer_reads_as_false(self) -> None:
        # 记录 46 的 TC_006 第 1 步就是这一条：空串让 expects_true 返回 False，
        # visible_element 与 intent_value 两个绑定器都直接放弃，步骤只能判 inconclusive。
        self.assertFalse(expects_true(''))
        normalized = parse_assertion(_existence_assertion(''))
        self.assertTrue(expects_true(normalized.expected['value']))

    def test_not_exists_is_normalised_the_same_way(self) -> None:
        self.assertIs(parse_assertion(_existence_assertion('', operator='not_exists')).expected['value'], True)

    def test_popup_existence_is_normalised_too(self) -> None:
        payload = {**_existence_assertion(''), 'assert_kind': 'popup'}
        self.assertIs(parse_assertion(payload).expected['value'], True)

    def test_a_value_comparison_keeps_its_expected(self) -> None:
        # equals/contains 的 expected 是真正要比对的文本，不能被归一掉。
        payload = {**_existence_assertion('Investigate'), 'operator': 'equals'}
        self.assertEqual(parse_assertion(payload).expected['value'], 'Investigate')


class NestedCandidateTieBreakTests(SimpleTestCase):
    """一个控件会被它的每一层祖先重复报出来，取最内层是确定的；互不包含时仍应拒绝。"""

    resolve = staticmethod(PyUICompatAgent._innermost_of_nested)

    def test_an_ancestor_chain_resolves_to_the_innermost(self) -> None:
        chain = [
            ('div.page', (0, 0, 800, 600)),
            ('div.row', (10, 20, 400, 80)),
            ('span.status', (20, 30, 120, 24)),
        ]
        self.assertEqual(self.resolve(chain), 'span.status')

    def test_disjoint_candidates_are_refused(self) -> None:
        # 七个真正不同的状态控件，猜哪一个都是错的。
        rows = [(f'span.status-{i}', (20, 30 + i * 40, 120, 24)) for i in range(7)]
        self.assertEqual(self.resolve(rows), '')

    def test_a_partial_overlap_is_not_nesting(self) -> None:
        self.assertEqual(self.resolve([('a', (0, 0, 100, 100)), ('b', (50, 50, 100, 100))]), '')

    def test_missing_geometry_refuses_rather_than_guesses(self) -> None:
        self.assertEqual(self.resolve([('a', (0, 0, 100, 100)), ('b', ())]), '')
        self.assertEqual(self.resolve([('a', (0, 0, 100, 0)), ('b', (0, 0, 10, 10))]), '')

    def test_no_candidates_resolves_to_nothing(self) -> None:
        self.assertEqual(self.resolve([]), '')


class BindingRoundConvergenceTests(SimpleTestCase):
    """页面结构没变时不再重复问视觉模型同一个问题。"""

    def _agent(self):
        agent = PyUICompatAgent.__new__(PyUICompatAgent)
        agent._exhausted_binding_states = set()
        return agent

    @staticmethod
    def _page_context(fingerprint):
        async def _build(_page):
            return {'url': 'https://example.test/alerts', 'fingerprint': fingerprint}
        return _build

    def _key(self, agent, fingerprint, step_index=3, intent='alert detail view'):
        import asyncio

        agent._build_page_context = self._page_context(fingerprint)
        return asyncio.run(agent._binding_state_key(
            None, step_index, [{'assert_kind': 'element_state', 'target': {'intent': intent}}],
        ))

    def test_the_same_page_and_step_produce_the_same_key(self) -> None:
        agent = self._agent()
        self.assertEqual(self._key(agent, 'abc'), self._key(agent, 'abc'))

    def test_a_changed_page_structure_is_a_new_key(self) -> None:
        agent = self._agent()
        self.assertNotEqual(self._key(agent, 'abc'), self._key(agent, 'def'))

    def test_a_different_step_is_a_new_key(self) -> None:
        agent = self._agent()
        self.assertNotEqual(self._key(agent, 'abc', step_index=3), self._key(agent, 'abc', step_index=4))

    def test_a_different_assertion_is_a_new_key(self) -> None:
        agent = self._agent()
        self.assertNotEqual(self._key(agent, 'abc', intent='alert detail'), self._key(agent, 'abc', intent='camera list'))

    def test_an_unavailable_fingerprint_never_suppresses_a_round(self) -> None:
        # 取不到指纹时必须回到原来的行为，宁可多问一次也不能漏掉可成功的绑定。
        agent = self._agent()
        self.assertEqual(self._key(agent, ''), '')

    def test_the_skip_is_wired_to_the_exhausted_set(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._bind_required_assertions_after_action)
        self.assertIn('binding_state in self._exhausted_binding_states', source)
        self.assertIn('self._exhausted_binding_states.add(binding_state)', source)


class StoredPlanHealingTests(SimpleTestCase):
    """存量计划里的空 expected 在加载时就修好，不必等契约版本号变更重生成。"""

    heal = staticmethod(PyUICompatAgent._normalize_existence_expectations)

    def test_an_empty_expected_is_healed_on_load(self) -> None:
        healed = self.heal([_existence_assertion('')])
        self.assertIs(healed[0]['expected']['value'], True)
        self.assertTrue(expects_true(healed[0]['expected']['value']))

    def test_the_original_assertion_is_not_mutated(self) -> None:
        original = _existence_assertion('')
        self.heal([original])
        self.assertEqual(original['expected']['value'], '')

    def test_other_expected_keys_survive(self) -> None:
        assertion = _existence_assertion('')
        assertion['expected']['minimum_advanced_seconds'] = 3
        healed = self.heal([assertion])
        self.assertEqual(healed[0]['expected']['minimum_advanced_seconds'], 3)

    def test_a_value_comparison_is_left_alone(self) -> None:
        assertion = {**_existence_assertion('Investigate'), 'operator': 'equals'}
        self.assertEqual(self.heal([assertion])[0]['expected']['value'], 'Investigate')

    def test_non_dict_entries_pass_through(self) -> None:
        self.assertEqual(self.heal(['not an assertion', None]), ['not an assertion', None])

    def test_normalisation_is_wired_into_step_loading(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._normalize_step)
        self.assertIn("self._normalize_existence_expectations(raw_step.get('assertions')", source)


class FreshContentIdentityTests(SimpleTestCase):
    """SPA 在稳定容器里换内容时，结构化选择器不变，只能靠文本判断新增。"""

    def _agent(self, baseline_texts):
        agent = PyUICompatAgent.__new__(PyUICompatAgent)
        agent._observable_baseline_texts = set(baseline_texts)
        return agent

    def test_a_new_selector_is_fresh(self) -> None:
        agent = self._agent({'Alerts'})
        self.assertTrue(agent._is_fresh_content({'selector': 'div.new', 'text': 'Alerts'}, {'div.old'}))

    def test_new_text_under_a_reused_selector_is_fresh(self) -> None:
        # 实测：一步里 12 个元素带着页面上此前没有的文本，却只有 1 个选择器是新的。
        agent = self._agent({'Alerts', 'Cameras'})
        element = {'selector': 'div:nth-of-type(1)', 'text': 'Alert detail for 5003_D13'}
        self.assertTrue(agent._is_fresh_content(element, {'div:nth-of-type(1)'}))

    def test_a_reused_selector_showing_old_text_is_not_fresh(self) -> None:
        agent = self._agent({'Alerts'})
        self.assertFalse(agent._is_fresh_content({'selector': 'div:nth-of-type(1)', 'text': 'Alerts'}, {'div:nth-of-type(1)'}))

    def test_a_reused_selector_without_text_is_not_fresh(self) -> None:
        agent = self._agent({'Alerts'})
        self.assertFalse(agent._is_fresh_content({'selector': 'div:nth-of-type(1)', 'text': '   '}, {'div:nth-of-type(1)'}))

    def test_a_page_that_only_lost_content_stays_unfresh(self) -> None:
        # 对照实测：baseline=107 observed=96 且按文本也无新增，说明动作确实没引入内容，应当继续拒绝。
        agent = self._agent({f'label {i}' for i in range(20)})
        observed = [{'selector': f'div:nth-of-type({i})', 'text': f'label {i}'} for i in range(10)]
        baseline = {f'div:nth-of-type({i})' for i in range(20)}
        self.assertEqual([e for e in observed if agent._is_fresh_content(e, baseline)], [])


class VisibleElementScopeTests(SimpleTestCase):
    """弹层打开时只认弹层内容；没有弹层时普通控件也应当可绑。"""

    @staticmethod
    def _scope(controls):
        # 复刻绑定器里的取值规则，验证作用域选择本身。
        scoped = [c for c in controls if c.get('top_layer') is True]
        if not scoped and not any(c.get('blocking_layer') is True for c in controls):
            scoped = controls
        return [c['name'] for c in scoped]

    def test_a_dialog_keeps_ownership_of_the_screen(self) -> None:
        controls = [
            {'name': 'Confirm', 'top_layer': True},
            {'name': 'Camera 5003_D13', 'top_layer': False},
        ]
        self.assertEqual(self._scope(controls), ['Confirm'])

    def test_ordinary_content_is_bindable_with_no_layer_open(self) -> None:
        # TC_005 第 3 步：列表项不是弹层，此前没有任何绑定器能接。
        controls = [{'name': 'Camera 5003_D13', 'top_layer': False}]
        self.assertEqual(self._scope(controls), ['Camera 5003_D13'])

    def test_a_blocking_layer_without_top_layer_controls_still_refuses(self) -> None:
        controls = [
            {'name': 'Camera 5003_D13', 'top_layer': False},
            {'name': 'overlay', 'top_layer': False, 'blocking_layer': True},
        ]
        self.assertEqual(self._scope(controls), [])

    def test_the_binder_uses_this_scoping_rule(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._visible_element_binding_from_completed_click)
        self.assertIn("control.get('top_layer') is True", source)
        self.assertIn("control.get('blocking_layer') is True", source)


class FreshMediaIdentityTests(SimpleTestCase):
    """筛选列表会复用行容器，缩略图选择器不变而图片已经换了。"""

    def _agent(self, baseline_elements):
        agent = PyUICompatAgent.__new__(PyUICompatAgent)
        agent._rendered_visual_baseline_elements = baseline_elements
        return agent

    def test_a_new_selector_is_fresh(self) -> None:
        agent = self._agent({'img.a': {'content_key': 'a.jpg|64x64'}})
        self.assertTrue(agent._is_fresh_media({'selector': 'img.b', 'content_key': 'b.jpg|64x64'}, {'img.a'}))

    def test_a_reused_selector_showing_a_different_picture_is_fresh(self) -> None:
        # TC_005 第 4 步与 TC_006 第 1 步卡住的正是这一种。
        agent = self._agent({'img.row1': {'content_key': 'old.jpg|64x64'}})
        element = {'selector': 'img.row1', 'content_key': 'new.jpg|64x64'}
        self.assertTrue(agent._is_fresh_media(element, {'img.row1'}))

    def test_the_same_picture_in_the_same_place_is_not_fresh(self) -> None:
        agent = self._agent({'img.row1': {'content_key': 'same.jpg|64x64'}})
        self.assertFalse(agent._is_fresh_media({'selector': 'img.row1', 'content_key': 'same.jpg|64x64'}, {'img.row1'}))

    def test_a_missing_content_key_does_not_invent_freshness(self) -> None:
        agent = self._agent({'img.row1': {'content_key': 'same.jpg|64x64'}})
        self.assertFalse(agent._is_fresh_media({'selector': 'img.row1'}, {'img.row1'}))

    def test_an_unknown_baseline_entry_is_not_fresh(self) -> None:
        agent = self._agent({})
        self.assertFalse(agent._is_fresh_media({'selector': 'img.row1', 'content_key': 'x'}, {'img.row1'}))

    def test_the_inventory_reports_a_content_key(self) -> None:
        from apps.ai_testing.runtime.pyui_compat.runner import RENDERED_VISUAL_ELEMENTS_JS

        self.assertIn('content_key', RENDERED_VISUAL_ELEMENTS_JS)
        self.assertIn('currentSrc', RENDERED_VISUAL_ELEMENTS_JS)


class VanishingMediaKindTests(SimpleTestCase):
    """关闭播放器的断言，planner 会写成 element_state 或 absence，两种都要能确定性绑定。"""

    gate = staticmethod(PyUICompatAgent._vanishing_media_assertions)

    @staticmethod
    def _step(assert_kind, operator='not_exists', intent='live video stream player for camera 5003_D13'):
        return {'assertions': [{
            'assert_kind': assert_kind, 'operator': operator,
            'expected': {'value': True}, 'target': {'intent': intent}, 'required': True,
        }]}

    def test_absence_counts_as_a_vanishing_media_assertion(self) -> None:
        # 记录 91：写成 absence 时无人接手，locator 由模型猜出，猜中残留容器就判失败。
        self.assertEqual(len(self.gate(self._step('absence'))), 1)

    def test_element_state_still_counts(self) -> None:
        self.assertEqual(len(self.gate(self._step('element_state'))), 1)

    def test_an_exists_assertion_is_not_a_vanish(self) -> None:
        self.assertEqual(self.gate(self._step('absence', operator='exists')), [])

    def test_a_non_media_intent_is_not_a_vanish(self) -> None:
        self.assertEqual(self.gate(self._step('absence', intent='confirmation dialog')), [])

    def test_an_already_bound_target_is_skipped(self) -> None:
        step = self._step('absence')
        step['assertions'][0]['target']['locator'] = '#player'
        self.assertEqual(self.gate(step), [])

    def test_the_baseline_is_captured_for_such_a_step(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._capture_rendered_visual_baseline)
        self.assertIn('_vanishing_media_assertions(step)', source)


class NamedControlGuardTests(SimpleTestCase):
    """「最大的新增块」不能用来回答「某个具名控件是否存在」。"""

    @staticmethod
    def _matches(intent):
        from apps.ai_testing.runtime.pyui_compat.runner import NAMED_CONTROL_INTENT_PATTERN
        return bool(NAMED_CONTROL_INTENT_PATTERN.search(intent))

    def test_a_named_button_is_recognised(self) -> None:
        # 记录 103 第 12 步：这条被绑到了通用布局容器，步骤假通过，流程断在后面。
        self.assertTrue(self._matches('Deactivate button on the selected user detail'))

    def test_other_control_nouns_are_recognised(self) -> None:
        for intent in ('the Cameras icon', 'notify checkbox', 'dark mode toggle', 'View Playback link', 'Settings tab'):
            with self.subTest(intent=intent):
                self.assertTrue(self._matches(intent))

    def test_a_region_intent_is_not_a_named_control(self) -> None:
        for intent in (
            'monitoring view area below which alert status controls are shown',
            'Alert detail view introduced after opening the first alert',
            'cameras list search results',
        ):
            with self.subTest(intent=intent):
                self.assertFalse(self._matches(intent))

    def test_the_binder_refuses_named_controls(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._fresh_content_binding_from_completed_action)
        self.assertIn('NAMED_CONTROL_INTENT_PATTERN', source)
        self.assertIn('leave it to a name-matching binder', source)


class BinderActionCoverageTests(SimpleTestCase):
    """在搜索框输入是最典型的「引入新内容」，内容类绑定器都应当接受 fill。"""

    @staticmethod
    def _accepted_actions(method):
        import inspect
        import re

        source = inspect.getsource(method)
        match = re.search(r"action\.get\('action'\) not in \{([^}]*)\}", source)
        assert match, f'没有找到 {method.__name__} 的动作集合'
        return {token.strip().strip("\'") for token in match.group(1).split(',') if token.strip()}

    def test_fresh_content_accepts_fill(self) -> None:
        # TC_006 冷跑第 1 步：动作是 fill，此前 fresh_content 直接跳过，筛选后的列表无人可绑。
        self.assertIn('fill', self._accepted_actions(PyUICompatAgent._fresh_content_binding_from_completed_action))

    def test_the_content_binders_agree_on_fill(self) -> None:
        for method in (
            PyUICompatAgent._fresh_content_binding_from_completed_action,
            PyUICompatAgent._rendered_visual_binding_from_completed_action,
            PyUICompatAgent._collection_binding_from_completed_action,
            PyUICompatAgent._intent_value_binding_from_completed_action,
        ):
            with self.subTest(binder=method.__name__):
                self.assertIn('fill', self._accepted_actions(method))
