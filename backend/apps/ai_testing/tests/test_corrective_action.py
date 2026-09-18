"""断言未达成时的有界纠正动作：只揭示、不改变业务状态、只一轮。"""

from django.test import SimpleTestCase

from apps.ai_testing.runtime.pyui_compat.runner import (
    DISCLOSURE_CONTROL_PATTERN,
    STATE_CHANGING_CONTROL_PATTERN,
    PyUICompatAgent,
)


def _agent():
    agent = PyUICompatAgent.__new__(PyUICompatAgent)
    agent._corrective_action_steps = set()
    return agent


class CorrigibleAssertionTests(SimpleTestCase):
    """只有正向断言可以被纠正；负向断言会被纠正动作真正伪造。"""

    pick = staticmethod(PyUICompatAgent._corrigible_assertions)

    def test_positive_existence_is_corrigible(self) -> None:
        self.assertEqual(len(self.pick([{'assert_kind': 'element_state', 'operator': 'exists'}])), 1)

    def test_a_count_assertion_is_corrigible(self) -> None:
        self.assertEqual(len(self.pick([{'assert_kind': 'collection', 'operator': 'greater_than'}])), 1)

    def test_not_exists_is_never_corrigible(self) -> None:
        # 点一下折叠控件就能把行从 DOM 里拿掉，「摄像头不在列表中」于是成立——这是真正的伪造路径。
        for operator in ('not_exists', 'not_contains'):
            with self.subTest(operator=operator):
                self.assertEqual(self.pick([{'assert_kind': 'element_state', 'operator': operator}]), [])

    def test_absence_is_never_corrigible(self) -> None:
        self.assertEqual(self.pick([{'assert_kind': 'absence', 'operator': 'not_exists'}]), [])

    def test_junk_entries_are_ignored(self) -> None:
        self.assertEqual(self.pick([None, 'nonsense', {}]), [])


class ActionWhitelistTests(SimpleTestCase):
    def _refusal(self, action, controls=None):
        return _agent()._corrective_action_refusal(action, controls or [])

    def test_scroll_is_allowed(self) -> None:
        # 视口位置不参与 is_visible 判定，滚动只对虚拟滚动列表有意义，但它不改变任何业务状态。
        self.assertEqual(self._refusal({'action': 'scroll'}), '')

    def test_an_aria_expanded_false_control_is_allowed(self) -> None:
        controls = [{'selector': '#group', 'name': '萧山区', 'aria_expanded': 'false'}]
        self.assertEqual(self._refusal({'action': 'click', 'selector': '#group'}, controls), '')

    def test_a_treeitem_is_allowed(self) -> None:
        controls = [{'selector': '#node', 'name': '萧山区', 'role': 'treeitem'}]
        self.assertEqual(self._refusal({'action': 'click', 'selector': '#node'}, controls), '')

    def test_a_disclosure_label_is_allowed(self) -> None:
        for label in ('Show more', 'expand', '展开', '下一页', 'Load more'):
            with self.subTest(label=label):
                self.assertEqual(self._refusal({'action': 'click', 'selector': '#x', 'accessible_name': label}), '')

    def test_a_committing_control_is_refused(self) -> None:
        for label in ('Confirm', 'Delete user', 'Deactivate', '提交', '保存'):
            with self.subTest(label=label):
                refusal = self._refusal({'action': 'click', 'selector': '#x', 'accessible_name': label})
                self.assertIn('commits or destroys', refusal)

    def test_an_ordinary_control_is_refused(self) -> None:
        refusal = self._refusal({'action': 'click', 'selector': '#x', 'accessible_name': 'Camera 5003_D13'})
        self.assertIn('does not look like it reveals', refusal)

    def test_state_changing_actions_are_refused(self) -> None:
        for name in ('fill', 'select', 'press', 'navigate'):
            with self.subTest(action=name):
                self.assertIn('may change business state', self._refusal({'action': name}))

    def test_hover_is_refused_as_useless_not_as_dangerous(self) -> None:
        # 理由要说准：hover 改变不了 DOM 中元素的存在与可见性，它是无效而非危险。
        refusal = self._refusal({'action': 'hover'})
        self.assertIn('cannot change whether the target exists', refusal)
        self.assertNotIn('business state', refusal)

    def test_a_committing_label_beats_a_disclosure_label(self) -> None:
        # 「确认展开」这种同时命中两边的，必须按拒绝处理。
        refusal = self._refusal({'action': 'click', 'selector': '#x', 'accessible_name': '确认 展开'})
        self.assertIn('commits or destroys', refusal)


class PatternTests(SimpleTestCase):
    def test_the_two_patterns_do_not_overlap_on_common_labels(self) -> None:
        for label in ('Show more', 'expand', '展开', '下一页'):
            with self.subTest(label=label):
                self.assertTrue(DISCLOSURE_CONTROL_PATTERN.search(label))
                self.assertFalse(STATE_CHANGING_CONTROL_PATTERN.search(label))

    def test_destructive_labels_are_caught(self) -> None:
        for label in ('Delete', 'Deactivate', 'Create user', '删除', '停用'):
            with self.subTest(label=label):
                self.assertTrue(STATE_CHANGING_CONTROL_PATTERN.search(label))


class OneRoundOnlyTests(SimpleTestCase):
    def test_a_step_is_corrected_at_most_once(self) -> None:
        import asyncio

        agent = _agent()
        agent._corrective_action_steps.add(3)
        unresolved = [{'assert_kind': 'element_state', 'operator': 'exists'}]
        result = asyncio.run(agent._reveal_assertion_target(None, {'description': 'x'}, 3, unresolved, None, None))
        self.assertFalse(result)

    def test_nothing_corrigible_means_no_round(self) -> None:
        import asyncio

        agent = _agent()
        unresolved = [{'assert_kind': 'absence', 'operator': 'not_exists'}]
        self.assertFalse(asyncio.run(agent._reveal_assertion_target(None, {'description': 'x'}, 1, unresolved, None, None)))
        # 未消耗额度：这一步压根没有可纠正的断言。
        self.assertNotIn(1, agent._corrective_action_steps)


class WiringTests(SimpleTestCase):
    def test_the_corrective_round_runs_after_the_inspect_only_round(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._bind_required_assertions_after_action)
        self.assertLess(source.index('_plan_ai_step_with_retries'), source.rindex('_correct_and_rebind'))

    def test_correction_also_fires_when_the_model_round_is_skipped(self) -> None:
        # 收敛闸门跳过模型轮时也要纠正：页面自上次失败以来没变化，正是该动手而不是再看一眼的时刻。
        import inspect

        source = inspect.getsource(PyUICompatAgent._bind_required_assertions_after_action)
        skip_branch = source[source.index('_exhausted_binding_states'):]
        self.assertIn('_correct_and_rebind', skip_branch.split('try:')[0])

    def test_correction_rebinds_through_the_deterministic_chain(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._correct_and_rebind)
        self.assertIn('_reveal_assertion_target', source)
        self.assertIn('_run_deterministic_binders', source)
        # 仍有未绑定断言时不能报告成功。
        self.assertIn('return not remaining', source)

    def test_the_prompt_forbids_state_changing_actions(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._reveal_assertion_target)
        self.assertIn('must not change any', source)
        self.assertIn('never fill, select or press', source)

    def test_every_attempt_is_recorded(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._reveal_assertion_target)
        self.assertIn("'type': 'corrective_action'", source)
        self.assertIn("'refused_because': refusal", source)
