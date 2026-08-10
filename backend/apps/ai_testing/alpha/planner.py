"""Validation boundary between Alpha Planner JSON and persisted task revisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apps.ai_testing.alpha.contracts import AlphaDomainError, PlanTask, SkillTier, validate_plan_tasks
from apps.ai_testing.alpha.skills.registry import SkillRegistry, SkillRegistryError


MAX_PLAN_TASKS = 50


class PlanValidationError(ValueError):
    """Raised when a Planner response is structurally or semantically unsafe."""


@dataclass(frozen=True, slots=True)
class PlannedTask:
    """Normalized task safe to persist in an Alpha draft revision."""

    task_key: str
    skill_name: str
    skill_version: str
    tier: SkillTier
    normalized_arguments: dict[str, object]
    dependency_keys: tuple[str, ...]
    parent_key: str | None


def parse_plan_payload(payload: object, registry: SkillRegistry) -> tuple[PlannedTask, ...]:
    """Validate a model payload against server-owned task and Skill contracts."""
    if not isinstance(payload, Mapping) or set(payload) != {'tasks'}:
        raise PlanValidationError('Planner output must contain only a tasks field')

    raw_tasks = payload['tasks']
    if not isinstance(raw_tasks, list) or not raw_tasks or len(raw_tasks) > MAX_PLAN_TASKS:
        raise PlanValidationError(f'Planner output must contain 1 to {MAX_PLAN_TASKS} tasks')

    planned_tasks: list[PlannedTask] = []
    graph_tasks: list[PlanTask] = []
    for raw_task in raw_tasks:
        planned_task = _parse_task(raw_task, registry)
        planned_tasks.append(planned_task)
        graph_tasks.append(
            PlanTask(
                task_key=planned_task.task_key,
                dependency_keys=planned_task.dependency_keys,
            )
        )

    try:
        validate_plan_tasks(graph_tasks)
    except AlphaDomainError as error:
        raise PlanValidationError(str(error)) from error

    task_keys = {task.task_key for task in planned_tasks}
    for task in planned_tasks:
        if task.parent_key is not None and task.parent_key not in task_keys:
            raise PlanValidationError(f'Plan task has an unknown parent: {task.parent_key}')
        if task.parent_key == task.task_key:
            raise PlanValidationError(f'Plan task cannot be its own parent: {task.task_key}')
    return tuple(planned_tasks)


def _parse_task(raw_task: object, registry: SkillRegistry) -> PlannedTask:
    if not isinstance(raw_task, Mapping):
        raise PlanValidationError('Planner task must be an object')

    allowed_fields = {'key', 'skill', 'arguments', 'depends_on', 'parent'}
    unknown_fields = set(raw_task).difference(allowed_fields)
    if unknown_fields:
        fields = ', '.join(sorted(str(field) for field in unknown_fields))
        raise PlanValidationError(f'Planner task contains unknown fields: {fields}')

    task_key = raw_task.get('key')
    skill_name = raw_task.get('skill')
    arguments = raw_task.get('arguments', {})
    dependencies = raw_task.get('depends_on', [])
    parent_key = raw_task.get('parent')
    if not isinstance(task_key, str) or not task_key:
        raise PlanValidationError('Planner task key must be a non-empty string')
    if not isinstance(skill_name, str) or not skill_name:
        raise PlanValidationError('Planner task skill must be a non-empty string')
    if not isinstance(arguments, Mapping):
        raise PlanValidationError('Planner task arguments must be an object')
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise PlanValidationError('Planner task dependencies must be a string list')
    if parent_key is not None and not isinstance(parent_key, str):
        raise PlanValidationError('Planner task parent must be a string or null')

    try:
        definition = registry.get(skill_name)
        normalized_arguments = definition.normalize_arguments(arguments)
    except SkillRegistryError as error:
        raise PlanValidationError(str(error)) from error
    return PlannedTask(
        task_key=task_key,
        skill_name=definition.name,
        skill_version=definition.version,
        tier=definition.tier,
        normalized_arguments=normalized_arguments,
        dependency_keys=tuple(dependencies),
        parent_key=parent_key,
    )