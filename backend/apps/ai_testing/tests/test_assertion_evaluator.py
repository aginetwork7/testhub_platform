import unittest

from apps.ai_testing.execution.assertion_evaluator import evaluate_assertion
from apps.ai_testing.execution.assertion_registry import parse_assertion


class AssertionEvaluatorTests(unittest.TestCase):
    def test_contains_matches_user_visible_text_case_insensitively(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'element_state',
            'target': {'locator': '#status'},
            'operator': 'contains',
            'expected': {'value': 'investigate'},
            'evidence_requirements': ['element_state'],
        })

        result = evaluate_assertion(assertion, [
            {'type': 'element_state', 'locator': '#status', 'visible': True, 'text': 'Investigate'},
        ])

        self.assertEqual(result.status, 'passed')

    def test_url_assertion_passes_with_current_url_evidence(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'url',
            'target': {'page': 'current'},
            'operator': 'contains',
            'expected': {'value': '/dashboard'},
            'evidence_requirements': ['url_snapshot'],
        })

        result = evaluate_assertion(assertion, [{'type': 'url_snapshot', 'url': 'https://test.example/dashboard'}])

        self.assertEqual(result.status, 'passed')

    def test_url_assertion_fails_with_nonmatching_current_url_evidence(self) -> None:
        assertion = parse_assertion({
            'action': 'assert', 'assert_kind': 'url', 'target': {'page': 'current'},
            'operator': 'contains', 'expected': {'value': '/dashboard'},
            'evidence_requirements': ['url_snapshot'],
        })

        result = evaluate_assertion(assertion, [{'type': 'url_snapshot', 'url': 'https://test.example/login'}])

        self.assertEqual(result.status, 'failed')

    def test_text_assertion_fails_when_evidence_does_not_match(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'text',
            'target': {'locator': {'strategy': 'css', 'value': 'h1'}},
            'operator': 'equals',
            'expected': {'value': 'Dashboard'},
            'evidence_requirements': ['dom_snapshot'],
        })

        result = evaluate_assertion(assertion, [{'type': 'dom_snapshot', 'text': 'Projects'}])

        self.assertEqual(result.status, 'failed')

    def test_assertion_is_inconclusive_without_required_evidence(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'field_value',
            'target': {'field': 'project_name'},
            'operator': 'equals',
            'expected': {'value': 'Release validation'},
            'evidence_requirements': ['structured_value'],
        })

        result = evaluate_assertion(assertion, [])

        self.assertEqual(result.status, 'inconclusive')

    def test_field_value_assertion_uses_structured_evidence(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'field_value',
            'target': {'field': 'resource.status'},
            'operator': 'equals',
            'expected': {'value': 'created'},
            'evidence_requirements': ['structured_value'],
        })

        result = evaluate_assertion(assertion, [{'type': 'structured_value', 'value': 'created'}])

        self.assertEqual(result.status, 'passed')

    def test_field_value_assertion_uses_only_bound_target_evidence(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'field_value',
            'target': {'field': 'category', 'locator': '#category'},
            'operator': 'equals',
            'expected': {'value': 'Other'},
            'evidence_requirements': ['structured_value'],
        })

        result = evaluate_assertion(assertion, [
            {'type': 'structured_value', 'locator': '#status', 'value': 'Investigate'},
            {'type': 'structured_value', 'locator': '#category', 'value': 'Other'},
        ])

        self.assertEqual(result.status, 'passed')

    def test_api_resource_assertion_uses_resource_creation_response(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'api_resource',
            'target': {'resource_type': 'alert_event'},
            'operator': 'equals',
            'expected': {'value': 'event-123'},
            'evidence_requirements': ['api_response'],
        })

        result = evaluate_assertion(assertion, [{'type': 'api_response', 'resource_id': 'event-123'}])

        self.assertEqual(result.status, 'passed')

    def test_absence_assertion_uses_absence_check_evidence(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'absence',
            'target': {'resource': 'temporary-alert'},
            'operator': 'equals',
            'expected': {'value': False},
            'evidence_requirements': ['absence_check'],
        })

        result = evaluate_assertion(assertion, [{'type': 'absence_check', 'exists': False}])

        self.assertEqual(result.status, 'passed')

    def test_absence_assertion_fails_when_resource_exists(self) -> None:
        assertion = parse_assertion({
            'action': 'assert', 'assert_kind': 'absence', 'target': {'resource': 'temporary-alert'},
            'operator': 'equals', 'expected': {'value': False},
            'evidence_requirements': ['absence_check'],
        })

        result = evaluate_assertion(assertion, [{'type': 'absence_check', 'exists': True}])

        self.assertEqual(result.status, 'failed')

    def test_video_assertion_uses_native_media_state(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'video',
            'target': {'locator': {'strategy': 'css', 'value': 'video'}},
            'operator': 'equals',
            'expected': {'paused': False, 'readyState': 4},
            'evidence_requirements': ['media_state', 'media_event'],
        })

        result = evaluate_assertion(assertion, [
            {'type': 'media_state', 'elements': [{'paused': False, 'readyState': 4, 'ended': False}]},
            {'type': 'media_event', 'name': 'playing'},
        ])

        self.assertEqual(result.status, 'passed')

    def test_media_assertion_fails_with_nonmatching_media_state(self) -> None:
        assertion = parse_assertion({
            'action': 'assert', 'assert_kind': 'media', 'target': {'locator': 'video'},
            'operator': 'equals', 'expected': {'paused': False},
            'evidence_requirements': ['media_state'],
        })

        result = evaluate_assertion(assertion, [{'type': 'media_state', 'elements': [{'paused': True}]}])

        self.assertEqual(result.status, 'failed')

    def test_media_exists_assertion_uses_native_media_elements(self) -> None:
        assertion = parse_assertion({
            'action': 'assert', 'assert_kind': 'media', 'target': {'locator': 'video'},
            'operator': 'exists', 'expected': {'value': True},
            'evidence_requirements': ['media_state'],
        })

        result = evaluate_assertion(assertion, [{'type': 'media_state', 'elements': [{'paused': True}]}])

        self.assertEqual(result.status, 'passed')

    def test_video_assertion_fails_with_nonmatching_media_state(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'video', 'target': {'locator': 'video'}, 'operator': 'equals', 'expected': {'paused': False}, 'evidence_requirements': ['media_state', 'media_event']})
        result = evaluate_assertion(assertion, [{'type': 'media_state', 'elements': [{'paused': True}]}, {'type': 'media_event', 'name': 'playing'}])

        self.assertEqual(result.status, 'failed')

    def test_video_assertion_is_inconclusive_without_media_event(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'video', 'target': {'locator': 'video'}, 'operator': 'equals', 'expected': {'paused': False}, 'evidence_requirements': ['media_state', 'media_event']})
        result = evaluate_assertion(assertion, [{'type': 'media_state', 'elements': [{'paused': False}]}])

        self.assertEqual(result.status, 'inconclusive')

    def test_stream_assertion_requires_active_time_progress(self) -> None:
        assertion = parse_assertion({
            'action': 'assert',
            'assert_kind': 'stream_state',
            'target': {'locator': {'strategy': 'css', 'value': 'video'}},
            'operator': 'equals',
            'expected': {'minimum_advanced_seconds': 2},
            'evidence_requirements': ['media_state_before', 'media_state_after', 'playback_time_progress'],
        })

        result = evaluate_assertion(assertion, [
            {'type': 'media_state_before', 'elements': [{'paused': True, 'currentTime': 10}]},
            {'type': 'media_state_after', 'elements': [{'paused': False, 'currentTime': 13}]},
            {'type': 'playback_time_progress', 'advanced_seconds': 3},
        ])

        self.assertEqual(result.status, 'passed')

    def test_playback_assertion_fails_without_required_progress(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'playback', 'target': {'locator': 'video'}, 'operator': 'greater_than', 'expected': {'minimum_advanced_seconds': 2}, 'evidence_requirements': ['media_state_before', 'media_state_after', 'playback_time_progress']})
        result = evaluate_assertion(assertion, [{'type': 'media_state_before', 'elements': [{'paused': True}]}, {'type': 'media_state_after', 'elements': [{'paused': False}]}, {'type': 'playback_time_progress', 'advanced_seconds': 1}])

        self.assertEqual(result.status, 'failed')

    def test_playback_assertion_is_inconclusive_without_progress_evidence(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'playback', 'target': {'locator': 'video'}, 'operator': 'greater_than', 'expected': {'minimum_advanced_seconds': 2}, 'evidence_requirements': ['media_state_before', 'media_state_after', 'playback_time_progress']})
        result = evaluate_assertion(assertion, [{'type': 'media_state_before', 'elements': []}, {'type': 'media_state_after', 'elements': []}])

        self.assertEqual(result.status, 'inconclusive')

    def test_field_value_conflict_is_inconclusive(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'field_value', 'target': {'field': 'state'}, 'operator': 'equals', 'expected': {'value': 'created'}, 'evidence_requirements': ['structured_value']})
        result = evaluate_assertion(assertion, [{'type': 'structured_value', 'value': 'created'}, {'type': 'structured_value', 'value': 'failed'}])

        self.assertEqual(result.status, 'inconclusive')

    def test_api_resource_conflict_is_inconclusive(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'api_resource', 'target': {'resource_type': 'alert'}, 'operator': 'equals', 'expected': {'value': 'one'}, 'evidence_requirements': ['api_response']})
        result = evaluate_assertion(assertion, [{'type': 'api_response', 'resource_id': 'one'}, {'type': 'api_response', 'resource_id': 'two'}])

        self.assertEqual(result.status, 'inconclusive')

    def test_element_state_assertions_use_target_evidence(self) -> None:
        for assert_kind in ('popup', 'element_state'):
            with self.subTest(assert_kind=assert_kind):
                assertion = parse_assertion({'action': 'assert', 'assert_kind': assert_kind, 'target': {'locator': 'body'}, 'operator': 'contains', 'expected': {'value': 'Ready'}, 'evidence_requirements': ['element_state']})
                result = evaluate_assertion(assertion, [{'type': 'element_state', 'locator': 'body', 'visible': True, 'text': 'Ready for review'}])

                self.assertEqual(result.status, 'passed')

    def test_collection_assertion_uses_target_count_evidence(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'collection', 'target': {'locator': '.item'}, 'operator': 'greater_than', 'expected': {'value': 1}, 'evidence_requirements': ['collection_state']})

        result = evaluate_assertion(assertion, [{'type': 'collection_state', 'locator': '.item', 'count': 2}])

        self.assertEqual(result.status, 'passed')

    def test_network_and_command_result_use_structured_evidence(self) -> None:
        cases = (('network', 'network_response', 'status', 200), ('command_result', 'command_receipt', 'exit_code', 0))
        for assert_kind, evidence_type, key, value in cases:
            with self.subTest(assert_kind=assert_kind):
                assertion = parse_assertion({'action': 'assert', 'assert_kind': assert_kind, 'target': {'request': 'current'}, 'operator': 'equals', 'expected': {'value': value}, 'evidence_requirements': [evidence_type]})
                self.assertEqual(evaluate_assertion(assertion, [{'type': evidence_type, key: value}]).status, 'passed')

    def test_download_task_assertion_uses_completion_evidence(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'download_task', 'target': {'download': 'current'}, 'operator': 'equals', 'expected': {'value': 'completed'}, 'evidence_requirements': ['download_task_state']})

        result = evaluate_assertion(assertion, [{'type': 'download_task_state', 'status': 'completed'}])

        self.assertEqual(result.status, 'passed')

    def test_visual_change_uses_before_and_after_frame_hashes(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'visual_change', 'target': {'page': 'current'}, 'operator': 'equals', 'expected': {'value': True}, 'evidence_requirements': ['visual_frame_before', 'visual_frame_after']})
        result = evaluate_assertion(assertion, [{'type': 'visual_frame_before', 'content_hash': 'before'}, {'type': 'visual_frame_after', 'content_hash': 'after'}])

        self.assertEqual(result.status, 'passed')

    def test_visual_change_fails_without_expected_change(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'visual_change', 'target': {'page': 'current'}, 'operator': 'equals', 'expected': {'value': True}, 'evidence_requirements': ['visual_frame_before', 'visual_frame_after']})
        result = evaluate_assertion(assertion, [{'type': 'visual_frame_before', 'content_hash': 'same'}, {'type': 'visual_frame_after', 'content_hash': 'same'}])

        self.assertEqual(result.status, 'failed')

    def test_visual_change_is_inconclusive_without_both_snapshots(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'visual_change', 'target': {'page': 'current'}, 'operator': 'equals', 'expected': {'value': True}, 'evidence_requirements': ['visual_frame_before', 'visual_frame_after']})
        result = evaluate_assertion(assertion, [{'type': 'visual_frame_before', 'content_hash': 'before'}])

        self.assertEqual(result.status, 'inconclusive')

    def test_stream_state_fails_without_active_progress(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'stream_state', 'target': {'locator': 'video'}, 'operator': 'equals', 'expected': {'minimum_advanced_seconds': 2}, 'evidence_requirements': ['media_state_before', 'media_state_after', 'playback_time_progress']})
        result = evaluate_assertion(assertion, [{'type': 'media_state_before', 'elements': []}, {'type': 'media_state_after', 'elements': [{'paused': True}]}, {'type': 'playback_time_progress', 'advanced_seconds': 3}])

        self.assertEqual(result.status, 'failed')

    def test_stream_state_is_inconclusive_without_progress_evidence(self) -> None:
        assertion = parse_assertion({'action': 'assert', 'assert_kind': 'stream_state', 'target': {'locator': 'video'}, 'operator': 'equals', 'expected': {'minimum_advanced_seconds': 2}, 'evidence_requirements': ['media_state_before', 'media_state_after', 'playback_time_progress']})
        result = evaluate_assertion(assertion, [{'type': 'media_state_before', 'elements': []}, {'type': 'media_state_after', 'elements': []}])

        self.assertEqual(result.status, 'inconclusive')