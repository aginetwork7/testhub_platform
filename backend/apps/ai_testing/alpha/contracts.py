"""Pure domain contracts for Alpha workflow planning and execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence


MAX_WORKFLOW_ROUNDS = 30


class AlphaDomainError(ValueError):
    """Raised when a workflow domain invariant is violated."""


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    COLLECTING_INPUT = "collecting_input"
    PLANNING = "planning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SkillTier(StrEnum):
    READ = "read"
    RUN = "run"
    WRITE = "write"


TERMINAL_WORKFLOW_STATUSES = frozenset(
    {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }
)

_ALLOWED_TRANSITIONS: Mapping[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: frozenset(
        {WorkflowStatus.COLLECTING_INPUT, WorkflowStatus.PLANNING, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.COLLECTING_INPUT: frozenset(
        {WorkflowStatus.PLANNING, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.PLANNING: frozenset(
        {
            WorkflowStatus.COLLECTING_INPUT,
            WorkflowStatus.AWAITING_CONFIRMATION,
            WorkflowStatus.EXECUTING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.AWAITING_CONFIRMATION: frozenset(
        {WorkflowStatus.PLANNING, WorkflowStatus.EXECUTING, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.EXECUTING: frozenset(
        {WorkflowStatus.REFLECTING, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.REFLECTING: frozenset(
        {
            WorkflowStatus.PLANNING,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.COMPLETED: frozenset(),
    WorkflowStatus.FAILED: frozenset(),
    WorkflowStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class WorkflowState:
    status: WorkflowStatus
    round_count: int


@dataclass(frozen=True, slots=True)
class PlanTask:
    task_key: str
    dependency_keys: tuple[str, ...] = ()


def validate_transition(current: WorkflowStatus, target: WorkflowStatus) -> None:
    """Validate a workflow state transition without mutating workflow state."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise AlphaDomainError(f"Invalid workflow transition: {current} -> {target}")


def record_completed_planning_cycle(round_count: int) -> int:
    """Return the next completed planning-cycle count within the global cap."""
    if round_count < 0:
        raise AlphaDomainError("Workflow round count cannot be negative")
    if round_count >= MAX_WORKFLOW_ROUNDS:
        raise AlphaDomainError(f"Workflow cannot exceed {MAX_WORKFLOW_ROUNDS} planning cycles")
    return round_count + 1


def validate_plan_tasks(tasks: Sequence[PlanTask]) -> None:
    """Ensure a task collection has unique keys and acyclic known dependencies."""
    task_by_key = {task.task_key: task for task in tasks}
    if len(task_by_key) != len(tasks):
        raise AlphaDomainError("Plan task keys must be unique")

    for task in tasks:
        if not task.task_key:
            raise AlphaDomainError("Plan task key cannot be empty")
        unknown_dependencies = set(task.dependency_keys).difference(task_by_key)
        if unknown_dependencies:
            unknown_keys = ", ".join(sorted(unknown_dependencies))
            raise AlphaDomainError(f"Plan task has unknown dependencies: {unknown_keys}")
        if task.task_key in task.dependency_keys:
            raise AlphaDomainError(f"Plan task cannot depend on itself: {task.task_key}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_key: str) -> None:
        if task_key in visited:
            return
        if task_key in visiting:
            raise AlphaDomainError("Plan task dependencies must be acyclic")

        visiting.add(task_key)
        for dependency_key in task_by_key[task_key].dependency_keys:
            visit(dependency_key)
        visiting.remove(task_key)
        visited.add(task_key)

    for task in tasks:
        visit(task.task_key)


def assert_revision_mutable(status: WorkflowStatus, is_frozen: bool) -> None:
    """Reject changes once execution has frozen the current plan revision."""
    if is_frozen or status not in {
        WorkflowStatus.DRAFT,
        WorkflowStatus.COLLECTING_INPUT,
        WorkflowStatus.PLANNING,
        WorkflowStatus.AWAITING_CONFIRMATION,
    }:
        raise AlphaDomainError("Plan revision is not mutable in the current workflow state")