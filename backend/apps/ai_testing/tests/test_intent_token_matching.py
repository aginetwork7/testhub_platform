"""断言 intent 与控件名的匹配：要求主语一致，不要求控件类型词也一致。"""

import re

from django.test import SimpleTestCase

from apps.ai_testing.execution.intent_text import CONTROL_TYPE_WORDS, subject_tokens

IGNORED = {'a', 'an', 'the', 'in', 'on', 'of', 'open', 'role', 'option', 'dropdown', 'menu'}


def _tokens(text):
    return {token for token in re.findall(r'\w+', text.casefold()) if token not in IGNORED}


def _matches(intent, control_name):
    """复刻绑定器的判据：intent 的主语词必须全部出现在控件名里。"""
    return subject_tokens(_tokens(intent)).issubset(_tokens(control_name))


class SubjectTokenTests(SimpleTestCase):
    def test_control_type_words_are_dropped(self) -> None:
        self.assertEqual(subject_tokens({'site', 'name', 'search', 'input'}), {'site', 'name', 'search'})

    def test_layout_words_are_dropped(self) -> None:
        self.assertEqual(subject_tokens({'camera', 'list'}), {'camera'})

    def test_an_intent_made_only_of_type_words_keeps_them(self) -> None:
        # 主语为空时不能返回空集，否则会匹配页面上任何控件。
        self.assertEqual(subject_tokens({'input', 'box'}), {'input', 'box'})

    def test_identifiers_survive(self) -> None:
        self.assertIn('5003_d13', subject_tokens({'camera', '5003_d13', 'thumbnail'}))


class RealWorldMatchTests(SimpleTestCase):
    """记录 167 的实际取值：这一对此前匹配失败，TC_005 第 1 步因此无人可绑。"""

    def test_the_observed_failure_now_matches(self) -> None:
        self.assertTrue(_matches('site name search input', 'Search site name...'))

    def test_it_previously_failed_on_the_type_word_alone(self) -> None:
        # 旧判据是全词匹配；差的就是 input 这一个词。
        self.assertFalse(_tokens('site name search input').issubset(_tokens('Search site name...')))
        self.assertEqual(_tokens('site name search input') - _tokens('Search site name...'), {'input'})


class NoLooseningTooFarTests(SimpleTestCase):
    """放宽的风险是绑错而不是绑不上，主语必须仍然全部命中。"""

    def test_a_different_subject_still_fails(self) -> None:
        self.assertFalse(_matches('site name search input', 'Search alert name...'))

    def test_a_missing_subject_word_still_fails(self) -> None:
        self.assertFalse(_matches('camera 5003_D13 thumbnail', 'Camera 5003_D99'))

    def test_a_bare_type_word_does_not_match_everything(self) -> None:
        self.assertFalse(_matches('input box', 'Search site name...'))

    def test_camera_list_does_not_match_an_unrelated_list(self) -> None:
        # 「camera list」去掉 list 后主语是 camera，不会命中告警列表。
        self.assertFalse(_matches('camera list', 'Alert list'))
        self.assertTrue(_matches('camera list', 'Camera list'))


class WiringTests(SimpleTestCase):
    def test_the_binder_matches_on_subject_tokens(self) -> None:
        import inspect

        from apps.ai_testing.runtime.pyui_compat.runner import PyUICompatAgent

        source = inspect.getsource(PyUICompatAgent._visible_element_binding_from_completed_click)
        self.assertIn('required_tokens = subject_tokens(intent_tokens)', source)
        self.assertIn('required_tokens.issubset(name_tokens)', source)
        # 候选唯一性这道闸门不能松：有歧义时宁可继续拒绝。
        self.assertIn('if len(best_candidates) != 1:', source)

    def test_the_word_list_covers_the_common_control_nouns(self) -> None:
        for word in ('input', 'box', 'field', 'button', 'icon', 'label', 'tab'):
            with self.subTest(word=word):
                self.assertIn(word, CONTROL_TYPE_WORDS)
