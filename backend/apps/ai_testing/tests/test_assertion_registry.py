import unittest

from apps.ai_testing.execution.assertion_registry import AssertionContractError, parse_assertion


class AssertionRegistryTests(unittest.TestCase):
    def test_parses_evidence_backed_text_assertion(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'text',
            'target': {'locator': {'strategy': 'css', 'value': '[data-testid="title"]'}},
            'operator': 'contains',
            'expected': {'value': 'Dashboard'},
            'evidence_requirements': ['dom_snapshot'],
        })

        self.assertEqual(assertion.assert_kind, 'text')
        self.assertTrue(assertion.required)
        self.assertEqual(assertion.evidence_requirements, ('dom_snapshot',))

    def test_rejects_non_assert_action(self) -> None:
        with self.assertRaisesRegex(AssertionContractError, 'must be "assert"'):
            parse_assertion({
                'action': 'click',
                'assert_kind': 'text',
                'target': {'locator': 'title'},
                'operator': 'contains',
                'expected': {'value': 'Dashboard'},
                'evidence_requirements': ['dom_snapshot'],
            })

    def test_rejects_unknown_assert_kind(self) -> None:
        with self.assertRaisesRegex(AssertionContractError, 'Unsupported assert_kind'):
            parse_assertion({
                'action': 'assert',
                'assert_kind': 'model_claim',
                'target': {'locator': 'title'},
                'operator': 'contains',
                'expected': {'value': 'Dashboard'},
                'evidence_requirements': ['dom_snapshot'],
            })

    def test_stream_assertion_requires_progress_evidence(self) -> None:
        with self.assertRaisesRegex(AssertionContractError, 'playback_time_progress'):
            parse_assertion({
                'action': 'assert',
                'assert_kind': 'stream_state',
                'target': {'locator': 'video'},
                'operator': 'equals',
                'expected': {'minimum_advanced_seconds': 1},
                'evidence_requirements': ['media_state_before', 'media_state_after'],
            })

    def test_rejects_playback_without_numeric_progress_expectation(self) -> None:
        with self.assertRaisesRegex(AssertionContractError, 'minimum_advanced_seconds'):
            parse_assertion({
                'action': 'assert', 'assert_kind': 'playback', 'target': {'locator': 'video'},
                'operator': 'equals', 'expected': {'value': 'playing'},
                'evidence_requirements': ['media_state_before', 'media_state_after', 'playback_time_progress'],
            })

    def test_rejects_video_with_unsupported_descriptive_state(self) -> None:
        with self.assertRaisesRegex(AssertionContractError, 'native media fields'):
            parse_assertion({
                'action': 'assert', 'assert_kind': 'video', 'target': {'locator': 'video'},
                'operator': 'equals', 'expected': {'value': 'playing'},
                'evidence_requirements': ['media_state', 'media_event'],
            })

    def test_stream_assertion_accepts_numeric_progress_operator(self) -> None:
        assertion = parse_assertion({
            'action': 'assert', 'assert_kind': 'stream_state', 'target': {'locator': 'video'},
            'operator': 'greater_than', 'expected': {'minimum_advanced_seconds': 1},
            'evidence_requirements': ['media_state_before', 'media_state_after', 'playback_time_progress'],
        })

        self.assertEqual(assertion.operator, 'greater_than')

    def test_phone_digits_operator_is_limited_to_field_values(self) -> None:
        with self.assertRaisesRegex(AssertionContractError, 'Unsupported operator'):
            parse_assertion({
                'action': 'assert',
                'assert_kind': 'text',
                'target': {'locator': '#phone'},
                'operator': 'phone_digits_equals',
                'expected': {'value': '+1 6465180948'},
                'evidence_requirements': ['dom_snapshot'],
            })

    def test_text_supports_not_contains(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'text',
            'target': {'page': 'current'},
            'operator': 'not_contains',
            'expected': {'value': 'removed record'},
            'evidence_requirements': ['dom_snapshot'],
        })

        self.assertEqual(assertion.operator, 'not_contains')

    def test_element_state_rejects_not_contains(self) -> None:
        with self.assertRaisesRegex(AssertionContractError, 'Unsupported operator'):
            parse_assertion({
                'action': 'assert',
                'assert_kind': 'element_state',
                'target': {'intent': 'status label'},
                'operator': 'not_contains',
                'expected': {'value': 'removed'},
                'evidence_requirements': ['element_state'],
            })

    def test_element_state_accepts_semantic_target_before_binding(self) -> None:
        assertion = parse_assertion({
            'action': 'assert', 'assert_kind': 'element_state',
            'target': {'intent': 'result status'}, 'operator': 'exists',
            'expected': {'value': True}, 'evidence_requirements': ['element_state'],
        })

        self.assertEqual(assertion.target, {'intent': 'result status'})

    def test_collection_rejects_descriptive_count(self) -> None:
        with self.assertRaisesRegex(AssertionContractError, 'Unsupported operator'):
            parse_assertion({
                'action': 'assert', 'assert_kind': 'collection', 'target': {'intent': 'results'},
                'operator': 'contains', 'expected': {'value': 'at least one'},
                'evidence_requirements': ['collection_state'],
            })

    def test_theme_accepts_dark_or_light_expected_value(self) -> None:
        assertion = parse_assertion({
            'action': 'assert', 'assert_kind': 'theme', 'target': {'page': 'current'},
            'operator': 'equals', 'expected': {'value': 'dark'},
            'evidence_requirements': ['theme_state'],
        })

        self.assertEqual(assertion.assert_kind, 'theme')