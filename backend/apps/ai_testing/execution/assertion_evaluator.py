"""Deterministic evaluation of unified assertions against raw evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import AssertionSpec
from .assertion_registry import MEDIA_STATE_FIELDS


@dataclass(frozen=True)
class AssertionEvaluation:
    """A verifier decision that the quality gate can persist and audit."""

    status: str
    actual: dict[str, Any]
    reason: str


def evaluate_assertion(
    assertion: AssertionSpec,
    evidence: Sequence[Mapping[str, Any]],
) -> AssertionEvaluation:
    """Evaluate supported assertion kinds without consulting an AI model."""
    artifacts_by_type = _artifacts_by_type(evidence)
    missing_evidence = [
        evidence_type
        for evidence_type in assertion.evidence_requirements
        if evidence_type not in artifacts_by_type
    ]
    if missing_evidence:
        return AssertionEvaluation(
            'inconclusive',
            {},
            f'Missing required evidence: {", ".join(missing_evidence)}.',
        )

    if assertion.assert_kind == 'url':
        actual_url = _first_value(artifacts_by_type['url_snapshot'], 'url')
        return _compare(assertion, actual_url, 'url')
    if assertion.assert_kind == 'text':
        actual_text = _first_value(artifacts_by_type['dom_snapshot'], 'text')
        return _compare(assertion, actual_text, 'text')
    if assertion.assert_kind in {'popup', 'element_state'}:
        state = _matching_target_state(artifacts_by_type['element_state'], assertion.target)
        if state is None:
            return AssertionEvaluation('inconclusive', {}, 'Target element state was not captured.')
        if assertion.target.get('visual_content') == 'image' and assertion.operator in {'exists', 'not_exists'}:
            actual = (
                bool(state.get('visible'))
                and bool(state.get('has_visual_content'))
                and bool(state.get('visual_signal'))
            )
            return _compare(assertion, actual, 'has_visual_content')
        actual = state.get('visible') if assertion.operator in {'exists', 'not_exists'} else state.get('text')
        return _compare(assertion, actual, 'visible' if assertion.operator in {'exists', 'not_exists'} else 'text')
    if assertion.assert_kind == 'collection':
        state = _matching_target_state(artifacts_by_type['collection_state'], assertion.target)
        if state is None:
            return AssertionEvaluation('inconclusive', {}, 'Target collection state was not captured.')
        return _compare(assertion, state.get('count'), 'count')
    if assertion.assert_kind == 'visual_change':
        before = _first_value(artifacts_by_type['visual_frame_before'], 'content_hash')
        after = _first_value(artifacts_by_type['visual_frame_after'], 'content_hash')
        if before is None or after is None:
            return AssertionEvaluation('inconclusive', {}, 'Visual change evidence is incomplete.')
        changed = str(before) != str(after)
        expected_changed = assertion.expected.get('value', True)
        expected = str(expected_changed).lower() in {'true', '1', 'yes'}
        return AssertionEvaluation('passed' if changed == expected else 'failed', {'changed': changed}, 'DOM state changed.' if changed == expected else 'DOM change did not match expectation.')
    if assertion.assert_kind == 'field_value':
        locator = assertion.target.get('locator')
        if locator:
            state = _matching_target_state(artifacts_by_type['structured_value'], assertion.target)
            if state is None:
                return AssertionEvaluation('inconclusive', {}, 'Target structured value was not captured.')
            actual_value = state.get('value')
        else:
            if _has_conflicting_values(artifacts_by_type['structured_value'], 'value'):
                return AssertionEvaluation('inconclusive', {}, 'Conflicting structured evidence values.')
            actual_value = _first_value(artifacts_by_type['structured_value'], 'value')
        return _compare(assertion, actual_value, 'value')
    if assertion.assert_kind == 'api_resource':
        if _has_conflicting_values(artifacts_by_type['api_response'], 'resource_id'):
            return AssertionEvaluation('inconclusive', {}, 'Conflicting API resource evidence values.')
        resource_id = _first_value(artifacts_by_type['api_response'], 'resource_id')
        return _compare(assertion, resource_id, 'resource_id')
    if assertion.assert_kind == 'network':
        return _compare(assertion, _first_value(artifacts_by_type['network_response'], 'status'), 'status')
    if assertion.assert_kind == 'download_task':
        return _compare(assertion, _last_value(artifacts_by_type['download_task_state'], 'status'), 'status')
    if assertion.assert_kind == 'command_result':
        return _compare(assertion, _first_value(artifacts_by_type['command_receipt'], 'exit_code'), 'exit_code')
    if assertion.assert_kind == 'absence':
        exists = _first_value(artifacts_by_type['absence_check'], 'exists')
        return _compare(assertion, exists, 'exists')
    if assertion.assert_kind == 'theme':
        mode = _first_value(artifacts_by_type['theme_state'], 'mode')
        return _compare(assertion, mode, 'mode')
    if assertion.assert_kind in {'media', 'video'}:
        media_elements = _first_value(artifacts_by_type['media_state'], 'elements')
        return _evaluate_media_state(assertion, media_elements)
    if assertion.assert_kind in {'stream_state', 'playback'}:
        return _evaluate_playback_progress(assertion, artifacts_by_type)

    return AssertionEvaluation(
        'inconclusive',
        {},
        f'No deterministic evaluator has been implemented for {assertion.assert_kind}.',
    )


def _artifacts_by_type(evidence: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for artifact in evidence:
        artifact_type = artifact.get('artifact_type') or artifact.get('type')
        if isinstance(artifact_type, str) and artifact_type:
            grouped.setdefault(artifact_type, []).append(artifact)
    return grouped


def _first_value(artifacts: Sequence[Mapping[str, Any]], key: str) -> object:
    for artifact in artifacts:
        metadata = artifact.get('metadata')
        if isinstance(metadata, Mapping) and key in metadata:
            return metadata[key]
        if key in artifact:
            return artifact[key]
    return None


def _last_value(artifacts: Sequence[Mapping[str, Any]], key: str) -> object:
    return _first_value(tuple(reversed(artifacts)), key)


def _matching_target_state(artifacts: Sequence[Mapping[str, Any]], target: Mapping[str, Any]) -> Mapping[str, Any] | None:
    locator = target.get('locator')
    for artifact in artifacts:
        metadata = artifact.get('metadata') if isinstance(artifact.get('metadata'), Mapping) else artifact
        if metadata.get('locator') == locator:
            return metadata
    return None


def _has_conflicting_values(artifacts: Sequence[Mapping[str, Any]], key: str) -> bool:
    values = {_first_value([artifact], key) for artifact in artifacts}
    return len(values.difference({None})) > 1


def _compare(assertion: AssertionSpec, actual_value: object, actual_key: str) -> AssertionEvaluation:
    expected_value = assertion.expected.get('value')
    if actual_value is None:
        return AssertionEvaluation('inconclusive', {}, f'No {actual_key} value was captured in evidence.')

    actual_text = str(actual_value)
    expected_text = str(expected_value)
    if assertion.operator == 'equals':
        passed = actual_text == expected_text
    elif assertion.operator == 'phone_digits_equals':
        actual_digits = ''.join(character for character in actual_text if character.isdigit())
        expected_digits = ''.join(character for character in expected_text if character.isdigit())
        passed = bool(expected_digits) and actual_digits == expected_digits
    elif assertion.operator == 'contains':
        passed = expected_text.casefold() in actual_text.casefold()
    elif assertion.operator == 'starts_with':
        passed = actual_text.casefold().startswith(expected_text.casefold())
    elif assertion.operator == 'not_contains':
        passed = expected_text.casefold() not in actual_text.casefold()
    elif assertion.operator == 'matches':
        try:
            passed = re.search(expected_text, actual_text) is not None
        except re.error:
            return AssertionEvaluation('inconclusive', {actual_key: actual_value}, 'Expected regular expression is invalid.')
    elif assertion.operator == 'exists':
        passed = bool(actual_value)
    elif assertion.operator == 'not_exists':
        passed = not bool(actual_value)
    elif assertion.operator == 'greater_than':
        try:
            passed = float(actual_value) > float(expected_value)
        except (TypeError, ValueError):
            return AssertionEvaluation('inconclusive', {actual_key: actual_value}, 'Evidence value is not numeric.')
    elif assertion.operator == 'less_than':
        try:
            passed = float(actual_value) < float(expected_value)
        except (TypeError, ValueError):
            return AssertionEvaluation('inconclusive', {actual_key: actual_value}, 'Evidence value is not numeric.')
    else:
        return AssertionEvaluation('inconclusive', {actual_key: actual_value}, 'Unsupported comparison operator.')

    return AssertionEvaluation(
        'passed' if passed else 'failed',
        {actual_key: actual_value},
        'Assertion matched evidence.' if passed else 'Assertion did not match evidence.',
    )


def _evaluate_media_state(assertion: AssertionSpec, media_elements: object) -> AssertionEvaluation:
    if not isinstance(media_elements, list):
        return AssertionEvaluation('inconclusive', {}, 'Media state evidence has no element list.')

    if assertion.operator in {'exists', 'not_exists'}:
        exists = bool(media_elements)
        passed = exists if assertion.operator == 'exists' else not exists
        return AssertionEvaluation(
            'passed' if passed else 'failed',
            {'exists': exists},
            'Media existence matched evidence.' if passed else 'Media existence did not match evidence.',
        )

    expected = assertion.expected
    expected_keys = set(expected).intersection(MEDIA_STATE_FIELDS)
    if not expected_keys:
        return AssertionEvaluation('inconclusive', {}, 'Media assertion has no supported expected fields.')

    for element in media_elements:
        if not isinstance(element, Mapping):
            continue
        if all(element.get(key) == expected[key] for key in expected_keys):
            return AssertionEvaluation('passed', {'element': dict(element)}, 'Media state matched evidence.')
    return AssertionEvaluation('failed', {'elements': media_elements}, 'No media element matched the expected state.')


def _evaluate_playback_progress(
    assertion: AssertionSpec,
    artifacts_by_type: Mapping[str, list[Mapping[str, Any]]],
) -> AssertionEvaluation:
    before = _first_value(artifacts_by_type['media_state_before'], 'elements')
    after = _first_value(artifacts_by_type['media_state_after'], 'elements')
    progress = _first_value(artifacts_by_type['playback_time_progress'], 'advanced_seconds')
    if not isinstance(before, list) or not isinstance(after, list) or progress is None:
        return AssertionEvaluation('inconclusive', {}, 'Playback evidence is incomplete.')
    try:
        advanced_seconds = float(progress)
        minimum = float(assertion.expected.get('minimum_advanced_seconds', 0))
    except (TypeError, ValueError):
        return AssertionEvaluation('inconclusive', {}, 'Playback progress evidence is not numeric.')
    after_is_playing = any(isinstance(item, Mapping) and not item.get('paused', True) for item in after)
    native_playback_passed = advanced_seconds >= minimum and after_is_playing
    visual_progress = _first_value(artifacts_by_type.get('playback_visual_progress', []), 'advanced_seconds')
    visual_confidence = _first_value(artifacts_by_type.get('playback_visual_progress', []), 'confidence')
    try:
        visual_playback_passed = float(visual_progress) >= minimum and float(visual_confidence) >= 0.8
    except (TypeError, ValueError):
        visual_playback_passed = False
    changed_canvas_indexes = _changed_canvas_indexes(artifacts_by_type) if assertion.assert_kind == 'stream_state' else []
    passed = native_playback_passed or visual_playback_passed or bool(changed_canvas_indexes)
    return AssertionEvaluation(
        'passed' if passed else 'failed',
        {
            'advanced_seconds': advanced_seconds,
            'after_is_playing': after_is_playing,
            'visual_advanced_seconds': visual_progress,
            'visual_confidence': visual_confidence,
            'changed_canvas_indexes': changed_canvas_indexes,
        },
        'Playback state advanced.' if native_playback_passed else
        'Visible playback timestamp advanced.' if visual_playback_passed else
        'Visible media canvas frames changed.' if changed_canvas_indexes else
        'Playback did not advance in an active media element.',
    )


def _changed_canvas_indexes(
    artifacts_by_type: Mapping[str, list[Mapping[str, Any]]],
) -> list[int]:
    before_frames = {
        _artifact_metadata(frame).get('index'): _artifact_metadata(frame).get('content_hash')
        for frame in artifacts_by_type.get('canvas_frame_before', [])
        if _artifact_metadata(frame).get('index') is not None
        and _artifact_metadata(frame).get('content_hash')
    }
    changed: list[int] = []
    for frame in artifacts_by_type.get('canvas_frame_after', []):
        metadata = _artifact_metadata(frame)
        index = metadata.get('index')
        before_hash = before_frames.get(index)
        after_hash = metadata.get('content_hash')
        before_signal = next((
            bool(_artifact_metadata(frame).get('visual_signal'))
            for frame in artifacts_by_type.get('canvas_frame_before', [])
            if _artifact_metadata(frame).get('index') == index
        ), False)
        after_signal = bool(metadata.get('visual_signal'))
        if isinstance(index, int) and before_hash and after_hash and before_hash != after_hash and before_signal and after_signal:
            changed.append(index)
    return changed


def _artifact_metadata(artifact: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = artifact.get('metadata')
    return metadata if isinstance(metadata, Mapping) else artifact