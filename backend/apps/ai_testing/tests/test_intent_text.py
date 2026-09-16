from django.test import SimpleTestCase

from apps.ai_testing.execution.intent_text import (
    continuing_collection_locator,
    display_value_from_target,
    exact_text_locator,
    expects_true,
    innermost_selectors,
    is_anchored_selector,
    is_choice_element,
    popup_intent_mismatch,
    selectors_are_nested,
    shared_intent_tokens,
)


class IntentTextTests(SimpleTestCase):
    def test_explicit_target_text_wins_over_intent(self) -> None:
        self.assertEqual(display_value_from_target({'intent': 'status showing To Do', 'text': 'Done'}), 'Done')

    def test_trailing_display_phrase_is_extracted(self) -> None:
        self.assertEqual(display_value_from_target({'intent': 'monitoring view status control showing To Do'}), 'To Do')
        self.assertEqual(display_value_from_target({'intent': 'toast that says Saved successfully.'}), 'Saved successfully')
        self.assertEqual(display_value_from_target({'intent': 'badge labeled 3'}), '3')
        self.assertEqual(display_value_from_target({'intent': 'header displaying "Alert Detail"'}), 'Alert Detail')

    def test_intents_without_a_literal_value_yield_nothing(self) -> None:
        self.assertEqual(display_value_from_target({'intent': 'monitoring detail panel'}), '')
        self.assertEqual(display_value_from_target({'intent': 'dialog showing the selected alert'}), '')
        self.assertEqual(display_value_from_target({'intent': 'row showing camera, site, time, status and agent'}), '')
        self.assertEqual(display_value_from_target(None), '')

    def test_anchored_selector_detection(self) -> None:
        self.assertTrue(is_anchored_selector('[title="To Do"]'))
        self.assertTrue(is_anchored_selector('#status'))
        self.assertTrue(is_anchored_selector('div.portal.z-50'))
        self.assertFalse(is_anchored_selector('#root > div:nth-of-type(2) > p:nth-of-type(1)'))
        self.assertFalse(is_anchored_selector('text=To Do'))
        self.assertFalse(is_anchored_selector(''))

    def test_exact_text_locator_prefers_the_anchored_control_over_repeated_labels(self) -> None:
        elements = [
            {'name': 'To Do', 'selector': '#root > div:nth-of-type(1) > p:nth-of-type(1)'},
            {'name': 'To Do', 'selector': '#root > div:nth-of-type(2) > p:nth-of-type(1)'},
            {'text': 'to do', 'selector': '[title="To Do"]'},
            {'name': '2296 To Do', 'selector': '#header-status'},
        ]

        self.assertEqual(exact_text_locator('To Do', elements), '[title="To Do"]')

    def test_exact_text_locator_declines_ambiguous_or_missing_matches(self) -> None:
        self.assertEqual(exact_text_locator('To Do', [
            {'name': 'To Do', 'selector': '[title="To Do"]'},
            {'name': 'To Do', 'selector': '#status-chip'},
        ]), '')
        self.assertEqual(exact_text_locator('To Do', [
            {'name': 'To Do', 'selector': 'div:nth-of-type(1) > p:nth-of-type(1)'},
            {'name': 'To Do', 'selector': 'div:nth-of-type(2) > p:nth-of-type(1)'},
        ]), '')
        self.assertEqual(exact_text_locator('Done', [{'name': 'To Do', 'selector': '[title="To Do"]'}]), '')
        self.assertEqual(exact_text_locator('', [{'name': '', 'selector': '#x'}]), '')

    def test_exact_text_locator_accepts_a_single_structural_match(self) -> None:
        self.assertEqual(exact_text_locator('Saved', [{'text': 'Saved', 'selector': 'body > div:nth-of-type(3)'}]), 'body > div:nth-of-type(3)')


class PopupIntentMismatchTests(SimpleTestCase):
    def test_dialog_mentioning_the_intent_subject_matches(self) -> None:
        self.assertEqual(popup_intent_mismatch('download confirmation dialog', 'Download clip 08:00 PM - 08:01 PM Cancel Download'), '')
        self.assertEqual(popup_intent_mismatch('user creation dialog', 'Create User Email Phone Role'), '')

    def test_dialog_without_the_intent_subject_is_a_mismatch(self) -> None:
        mismatch = popup_intent_mismatch(
            'download confirmation dialog',
            'Create Case from Playback Select a clip (max length: 5 minutes) Capture Cover Cancel Create Case',
        )
        self.assertIn('does not match "download confirmation dialog"', mismatch)
        self.assertIn('Create Case from Playback', mismatch)

    def test_generic_intents_and_unreadable_dialogs_are_never_judged(self) -> None:
        self.assertEqual(popup_intent_mismatch('confirmation dialog', 'Create Case from Playback'), '')
        self.assertEqual(popup_intent_mismatch('download confirmation dialog', ''), '')
        self.assertEqual(popup_intent_mismatch('下载确认弹窗', 'Create Case from Playback'), '')


class ValueDisplayLocatorTests(SimpleTestCase):
    def test_choice_elements_are_recognised(self) -> None:
        self.assertTrue(is_choice_element({'role': 'option', 'tag': 'div'}))
        self.assertTrue(is_choice_element({'role': '', 'tag': 'li', 'top_layer': True, 'group_size': 4}))
        self.assertFalse(is_choice_element({'role': '', 'tag': 'span', 'top_layer': False, 'group_size': 4}))
        self.assertFalse(is_choice_element({'role': 'button', 'tag': 'button'}))

    def test_skip_choices_ignores_the_still_open_option_and_binds_the_display(self) -> None:
        elements = [
            {'name': 'Close', 'selector': 'body > div:nth-of-type(5) > div:nth-of-type(2)', 'role': 'option', 'top_layer': True, 'group_size': 3},
            {'name': 'Close', 'selector': '[title="Close"]', 'tag': 'span', 'top_layer': False, 'group_size': 1},
        ]
        self.assertEqual(exact_text_locator('Close', elements, skip_choices=True), '[title="Close"]')
        self.assertEqual(exact_text_locator('Close', elements[:1], skip_choices=True), '')

    def test_containing_match_is_a_fallback_only_for_short_texts(self) -> None:
        elements = [
            {'text': 'Status: Close', 'selector': '#status-display'},
            {'text': 'Close ' + 'x' * 60, 'selector': '#long-paragraph'},
        ]
        self.assertEqual(exact_text_locator('Close', elements, allow_containing=True), '#status-display')
        self.assertEqual(exact_text_locator('Close', elements), '')

    def test_case_sensitive_matching_separates_a_label_from_a_committed_value(self) -> None:
        elements = [{'name': 'close', 'selector': '[aria-label="close"]'}, {'name': 'Close', 'selector': '[title="Close"]'}]
        self.assertEqual(exact_text_locator('Close', elements, case_sensitive=True), '[title="Close"]')
        self.assertEqual(exact_text_locator('Close', elements), '')

    def test_nested_wrappers_repeating_the_text_collapse_to_the_innermost_element(self) -> None:
        elements = [
            {'text': 'Close', 'selector': '#root > div:nth-of-type(2) > div:nth-of-type(1)'},
            {'text': 'Close', 'selector': '#root > div:nth-of-type(2) > div:nth-of-type(1) > p:nth-of-type(1)'},
        ]
        self.assertEqual(exact_text_locator('Close', elements), '#root > div:nth-of-type(2) > div:nth-of-type(1) > p:nth-of-type(1)')
        elements.append({'text': 'Close', 'selector': '#root > div:nth-of-type(9) > p:nth-of-type(1)'})
        self.assertEqual(exact_text_locator('Close', elements), '')

    def test_innermost_and_nesting_helpers(self) -> None:
        outer = '#root > div:nth-of-type(2)'
        inner = '#root > div:nth-of-type(2) > ul:nth-of-type(1) > li:nth-of-type(1)'
        self.assertEqual(innermost_selectors([outer, inner, '#other']), [inner, '#other'])
        self.assertTrue(selectors_are_nested(outer, inner))
        self.assertTrue(selectors_are_nested(inner, outer))
        self.assertFalse(selectors_are_nested(inner, '#other'))
        self.assertFalse(selectors_are_nested('', inner))

    def test_expected_true_accepts_serialised_booleans(self) -> None:
        for value in (True, 'true', 'True', ' TRUE ', '1', 'yes'):
            self.assertTrue(expects_true(value), value)
        for value in (False, 'false', '', None, 'Magic Search V2', 0):
            self.assertFalse(expects_true(value), value)


class ContinuingCollectionTests(SimpleTestCase):
    CAMERA_GROUP = '#root > div:nth-of-type(4) > div.cursor-grab'
    SITE_GROUP = '#root > div:nth-of-type(2) > div.group\\/site-item'

    def _predecessors(self):
        return [
            {'step_num': 2, 'assertions': [{
                'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0},
                'target': {'intent': 'site search result rows matching the target site', 'locator': self.SITE_GROUP},
            }]},
            {'step_num': 3, 'assertions': [{
                'assert_kind': 'collection', 'operator': 'greater_than', 'expected': {'value': 0},
                'target': {'intent': 'camera items listed for the selected site', 'locator': self.CAMERA_GROUP},
            }]},
        ]

    def test_shared_tokens_ignore_list_words_and_match_on_stems(self) -> None:
        self.assertEqual(shared_intent_tokens('online camera entries in the site camera list', 'camera items listed for the selected site'), 2)
        self.assertEqual(shared_intent_tokens('cameras shown in the list', 'camera rows'), 1)
        self.assertEqual(shared_intent_tokens('result rows in the list', 'items displayed on the page'), 0)

    def test_picks_the_predecessor_collection_sharing_the_most_subject_words(self) -> None:
        present = {self.SITE_GROUP, self.CAMERA_GROUP}
        self.assertEqual(
            continuing_collection_locator('online camera entries in the site camera list', self._predecessors(), present),
            self.CAMERA_GROUP,
        )
        self.assertEqual(
            continuing_collection_locator('search result rows for the site', self._predecessors(), present),
            self.SITE_GROUP,
        )

    def test_ties_go_to_the_latest_predecessor(self) -> None:
        self.assertEqual(
            continuing_collection_locator('entries for the site', self._predecessors(), {self.SITE_GROUP, self.CAMERA_GROUP}),
            self.CAMERA_GROUP,
        )

    def test_declines_without_a_shared_subject_word_or_a_present_locator(self) -> None:
        self.assertEqual(continuing_collection_locator('alarm records in the table', self._predecessors(), {self.SITE_GROUP, self.CAMERA_GROUP}), '')
        self.assertEqual(continuing_collection_locator('online camera entries', self._predecessors(), {self.SITE_GROUP}), '')
        self.assertEqual(continuing_collection_locator('online camera entries', self._predecessors(), set()), '')
        self.assertEqual(continuing_collection_locator('online camera entries', [], None), '')

    def test_only_non_empty_collection_contracts_are_continued(self) -> None:
        predecessors = [{'assertions': [
            {'assert_kind': 'collection', 'operator': 'equals', 'expected': {'value': 0}, 'target': {'intent': 'camera rows', 'locator': '#empty-cameras'}},
            {'assert_kind': 'element_state', 'operator': 'exists', 'target': {'intent': 'camera panel', 'locator': '#camera-panel'}},
        ]}]
        self.assertEqual(continuing_collection_locator('camera entries', predecessors, None), '')
