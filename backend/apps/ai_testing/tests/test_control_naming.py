"""控件取名：表单输入框必须能拿到名字，否则按名匹配的绑定器永远找不到它。"""

import re

from django.test import SimpleTestCase

from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatAgent


def _name_chain():
    """从控件发现的 JS 里取出取名表达式，验证取值顺序。"""
    import inspect

    source = inspect.getsource(PyUICompatAgent._build_actionable_controls)
    match = re.search(r'const name = \((.*?)\)\.trim\(\)', source, re.S)
    assert match, '没有找到取名表达式'
    return [part.strip() for part in match.group(1).split('||')]


class NameChainTests(SimpleTestCase):
    def test_label_and_placeholder_participate(self) -> None:
        chain = ' '.join(_name_chain())
        # 记录 207：intent 是 "create user form Email input"，而候选里根本没有 Email 输入框。
        self.assertIn('labelText', chain)
        self.assertIn('placeholder', chain)

    def test_the_typed_value_stays_after_the_field_name(self) -> None:
        # value 是字段里装着什么，不是字段是什么。填了字之后不能把字段名顶掉。
        chain = _name_chain()
        self.assertLess(chain.index('labelText'), chain.index('element.value'))
        self.assertLess(chain.index('placeholder'), chain.index('element.value'))

    def test_an_explicit_aria_label_still_wins(self) -> None:
        chain = _name_chain()
        self.assertEqual(chain[0], "element.getAttribute('aria-label')")
        self.assertLess(chain.index("element.getAttribute('aria-label')"), chain.index('placeholder'))

    def test_inner_text_still_wins_over_the_placeholder(self) -> None:
        # 有可见文本的控件以文本为准；placeholder 只是输入框没有文本时的兜底。
        chain = _name_chain()
        self.assertLess(chain.index('element.innerText'), chain.index('placeholder'))

    def test_both_label_forms_are_read(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._build_actionable_controls)
        self.assertIn('element.labels', source)        # <label for="...">
        self.assertIn("element.closest('label')", source)  # 包裹型 <label>

    def test_the_name_is_still_truncated(self) -> None:
        import inspect

        source = inspect.getsource(PyUICompatAgent._build_actionable_controls)
        # placeholder 可能很长（"Search site name..."），不能让它撑爆产物与提示词。
        self.assertIn('.slice(0, 120)', source)
