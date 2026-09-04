"""Deterministic final-state evaluation for AI intelligent test executions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualityGateResult:
    """An auditable final decision derived from execution facts only."""

    status: str
    failed_task_ids: tuple[object, ...]
    incomplete_task_ids: tuple[object, ...]
    failed_assertion_ids: tuple[object, ...]
    inconclusive_assertion_ids: tuple[object, ...]
    missing_assertion_step_ids: tuple[object, ...]


def evaluate_quality_gate(
    planned_tasks: Sequence[Mapping[str, Any]],
    assertion_results: Sequence[Mapping[str, Any]],
) -> QualityGateResult:
    """Return the only status a run may receive after evidence verification."""
    normalized_tasks = tuple(task for task in planned_tasks if isinstance(task, Mapping))
    if not normalized_tasks:
        return QualityGateResult('inconclusive', (), (), (), (), ())

    failed_task_ids = tuple(
        _task_id(task)
        for task in normalized_tasks
        if str(task.get('status', '')).strip().lower() == 'failed'
    )
    if failed_task_ids:
        return QualityGateResult('failed', failed_task_ids, (), (), (), ())

    incomplete_task_ids = tuple(
        _task_id(task)
        for task in normalized_tasks
        if str(task.get('status', '')).strip().lower() not in {'completed', 'skipped'}
    )
    if incomplete_task_ids:
        return QualityGateResult('inconclusive', (), incomplete_task_ids, (), (), ())

    required_step_ids = {
        _task_id(task)
        for task in normalized_tasks
        if bool(task.get('requires_assertion', True))
    }
    results_by_step = _required_assertions_by_step(assertion_results)
    missing_assertion_step_ids = tuple(sorted(required_step_ids.difference(results_by_step), key=str))
    if missing_assertion_step_ids:
        return QualityGateResult('inconclusive', (), (), (), (), missing_assertion_step_ids)

    failed_assertion_ids = tuple(
        _assertion_id(result)
        for result in assertion_results
        if _is_required(result) and str(result.get('status', '')).strip().lower() == 'failed'
    )
    if failed_assertion_ids:
        return QualityGateResult('failed', (), (), failed_assertion_ids, (), ())

    inconclusive_assertion_ids = tuple(
        _assertion_id(result)
        for result in assertion_results
        if _is_required(result) and str(result.get('status', '')).strip().lower() in {'inconclusive', 'invalid_evidence'}
    )
    if inconclusive_assertion_ids:
        return QualityGateResult('inconclusive', (), (), (), inconclusive_assertion_ids, ())

    return QualityGateResult('passed', (), (), (), (), ())


def _required_assertions_by_step(assertion_results: Sequence[Mapping[str, Any]]) -> set[object]:
    return {
        result.get('step_id')
        for result in assertion_results
        if _is_required(result) and result.get('step_id') is not None
    }


def _is_required(result: Mapping[str, Any]) -> bool:
    return isinstance(result, Mapping) and bool(result.get('required', True))


def _task_id(task: Mapping[str, Any]) -> object:
    return task.get('id', task.get('step_id'))


def _assertion_id(result: Mapping[str, Any]) -> object:
    return result.get('id', result.get('assertion_id'))