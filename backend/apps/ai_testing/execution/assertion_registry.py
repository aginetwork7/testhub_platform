"""Server-owned validation for the unified ``action=assert`` contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import AssertionSpec


class AssertionContractError(ValueError):
    """Raised when a planner emits an unsupported or incomplete assertion."""


@dataclass(frozen=True)
class AssertionKindDefinition:
    """Validation rules for one deterministic assertion verifier."""

    allowed_operators: frozenset[str]
    required_evidence: tuple[str, ...]


_EQUALITY_OPERATORS = frozenset({'equals', 'contains', 'matches', 'exists', 'not_exists'})
_TEXT_OPERATORS = _EQUALITY_OPERATORS | {'not_contains'}
_FIELD_VALUE_OPERATORS = frozenset({
    'equals', 'contains', 'starts_with', 'matches', 'exists', 'not_exists',
    'greater_than', 'less_than', 'phone_digits_equals',
})
_ORDERING_OPERATORS = frozenset({'equals', 'contains', 'matches', 'exists', 'not_exists', 'greater_than', 'less_than'})
_COLLECTION_OPERATORS = frozenset({'equals', 'exists', 'not_exists', 'greater_than', 'less_than'})
MEDIA_STATE_FIELDS = frozenset({
    'paused', 'ended', 'readyState', 'networkState', 'currentTime', 'duration',
    'videoWidth', 'videoHeight', 'currentSrc',
})

ASSERTION_KINDS: dict[str, AssertionKindDefinition] = {
    'text': AssertionKindDefinition(_TEXT_OPERATORS, ('dom_snapshot',)),
    'field_value': AssertionKindDefinition(_FIELD_VALUE_OPERATORS, ('structured_value',)),
    'popup': AssertionKindDefinition(_EQUALITY_OPERATORS, ('element_state',)),
    'media': AssertionKindDefinition(_EQUALITY_OPERATORS, ('media_state',)),
    'video': AssertionKindDefinition(_EQUALITY_OPERATORS, ('media_state', 'media_event')),
    'visual_change': AssertionKindDefinition(_EQUALITY_OPERATORS, ('visual_frame_before', 'visual_frame_after')),
    'stream_state': AssertionKindDefinition(_ORDERING_OPERATORS, ('media_state_before', 'media_state_after', 'playback_time_progress')),
    'playback': AssertionKindDefinition(_ORDERING_OPERATORS, ('media_state_before', 'media_state_after', 'playback_time_progress')),
    'element_state': AssertionKindDefinition(_EQUALITY_OPERATORS, ('element_state',)),
    'url': AssertionKindDefinition(_EQUALITY_OPERATORS, ('url_snapshot',)),
    'network': AssertionKindDefinition(_EQUALITY_OPERATORS, ('network_response',)),
    'download_task': AssertionKindDefinition(_EQUALITY_OPERATORS, ('download_task_state',)),
    'api_resource': AssertionKindDefinition(_EQUALITY_OPERATORS, ('api_response',)),
    'command_result': AssertionKindDefinition(_EQUALITY_OPERATORS, ('command_receipt',)),
    'collection': AssertionKindDefinition(_COLLECTION_OPERATORS, ('collection_state',)),
    'absence': AssertionKindDefinition(_EQUALITY_OPERATORS, ('absence_check',)),
    'theme': AssertionKindDefinition(_EQUALITY_OPERATORS, ('theme_state',)),
}


def parse_assertion(payload: Mapping[str, Any]) -> AssertionSpec:
    """Validate a planner assertion before it can enter an execution plan."""
    if payload.get('action') != 'assert':
        raise AssertionContractError('Assertion action must be "assert".')

    assert_kind = _required_string(payload, 'assert_kind')
    definition = ASSERTION_KINDS.get(assert_kind)
    if definition is None:
        raise AssertionContractError(f'Unsupported assert_kind: {assert_kind}.')

    operator = _required_string(payload, 'operator')
    if operator not in definition.allowed_operators:
        raise AssertionContractError(f'Unsupported operator "{operator}" for assert_kind "{assert_kind}".')

    target = _required_mapping(payload, 'target')
    expected = _required_mapping(payload, 'expected')
    _validate_kind_payload(assert_kind, operator, target, expected)
    evidence_requirements = _parse_evidence_requirements(payload)
    missing_evidence = set(definition.required_evidence).difference(evidence_requirements)
    if missing_evidence:
        required_names = ', '.join(sorted(missing_evidence))
        raise AssertionContractError(f'Assertion is missing required evidence: {required_names}.')

    required = payload.get('required', True)
    if not isinstance(required, bool):
        raise AssertionContractError('Assertion required must be a boolean.')

    timeout_ms = payload.get('timeout_ms')
    if timeout_ms is not None and (not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0):
        raise AssertionContractError('Assertion timeout_ms must be a positive integer when provided.')
    evidence_max_age_ms = payload.get('evidence_max_age_ms')
    if evidence_max_age_ms is not None and (not isinstance(evidence_max_age_ms, int) or isinstance(evidence_max_age_ms, bool) or evidence_max_age_ms <= 0):
        raise AssertionContractError('Assertion evidence_max_age_ms must be a positive integer when provided.')

    return AssertionSpec(
        assert_kind=assert_kind,
        target=target,
        operator=operator,
        expected=expected,
        evidence_requirements=evidence_requirements,
        required=required,
        timeout_ms=timeout_ms,
        evidence_max_age_ms=evidence_max_age_ms,
    )


def _validate_kind_payload(
    assert_kind: str,
    operator: str,
    target: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    locator_kinds = {'popup', 'element_state', 'collection', 'media', 'video', 'stream_state', 'playback'}
    if assert_kind in locator_kinds and not (target.get('locator') or target.get('intent')):
        raise AssertionContractError(f'Assertion target for {assert_kind} must include locator or intent.')
    if (
        assert_kind in {'media', 'video'}
        and operator not in {'exists', 'not_exists'}
        and (not set(expected) or not set(expected).issubset(MEDIA_STATE_FIELDS))
    ):
        raise AssertionContractError(
            f'Assertion expected for {assert_kind} may contain only native media fields.'
        )
    if assert_kind in {'stream_state', 'playback'}:
        value = expected.get('minimum_advanced_seconds')
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise AssertionContractError(f'Assertion expected for {assert_kind} must include non-negative minimum_advanced_seconds.')
    if assert_kind == 'visual_change' and not isinstance(expected.get('value'), bool):
        raise AssertionContractError('Assertion expected for visual_change must include boolean value.')
    if assert_kind == 'collection' and not isinstance(expected.get('value'), (int, float, bool)):
        raise AssertionContractError('Assertion expected for collection must include a numeric or boolean value.')
    if assert_kind == 'theme' and str(expected.get('value') or '').strip().lower() not in {'dark', 'light'}:
        raise AssertionContractError('Assertion expected for theme must be dark or light.')


def _required_string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise AssertionContractError(f'Assertion {field_name} must be a non-empty string.')
    return value.strip()


def _required_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping) or not value:
        raise AssertionContractError(f'Assertion {field_name} must be a non-empty object.')
    return dict(value)


def _parse_evidence_requirements(payload: Mapping[str, Any]) -> tuple[str, ...]:
    value = payload.get('evidence_requirements')
    if not isinstance(value, list) or not value:
        raise AssertionContractError('Assertion evidence_requirements must be a non-empty array.')
    requirements = tuple(_validate_evidence_name(item) for item in value)
    if len(set(requirements)) != len(requirements):
        raise AssertionContractError('Assertion evidence_requirements must not contain duplicates.')
    return requirements


def _validate_evidence_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssertionContractError('Assertion evidence requirement must be a non-empty string.')
    return value.strip()