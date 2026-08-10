"""Strict registry for Skills that Alpha is permitted to dispatch."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from apps.ai_testing.alpha.contracts import SkillTier


class SkillRegistryError(ValueError):
    """Raised when a Skill is unknown or its arguments violate its contract."""


@dataclass(frozen=True, slots=True)
class ArgumentField:
    """One server-defined JSON-compatible Skill argument."""

    name: str
    value_type: type[object]
    required: bool = True
    allow_none: bool = False


SkillHandler = Callable[[object, Mapping[str, object]], Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """The complete server-owned contract for one executable Skill."""

    name: str
    version: str
    tier: SkillTier
    risky: bool
    arguments: tuple[ArgumentField, ...]
    handler: SkillHandler

    @property
    def requires_confirmation(self) -> bool:
        return self.tier is SkillTier.WRITE or self.risky

    def normalize_arguments(self, arguments: Mapping[str, object]) -> dict[str, object]:
        expected_fields = {field.name: field for field in self.arguments}
        unknown_fields = set(arguments).difference(expected_fields)
        if unknown_fields:
            invalid_fields = ', '.join(sorted(unknown_fields))
            raise SkillRegistryError(f'Unexpected Skill arguments: {invalid_fields}')

        normalized: dict[str, object] = {}
        for field in self.arguments:
            value = arguments.get(field.name)
            if value is None:
                if field.required and not field.allow_none:
                    raise SkillRegistryError(f'Missing required Skill argument: {field.name}')
                if field.name in arguments:
                    normalized[field.name] = None
                continue
            if type(value) is not field.value_type:
                raise SkillRegistryError(f'Invalid type for Skill argument: {field.name}')
            normalized[field.name] = value
        return normalized


class SkillRegistry:
    """In-memory registry that rejects model-selected callables and free-form input."""

    def __init__(self) -> None:
        self._definitions: dict[str, SkillDefinition] = {}

    def register(self, definition: SkillDefinition) -> None:
        if not definition.name:
            raise SkillRegistryError('Skill name cannot be empty')
        if definition.name in self._definitions:
            raise SkillRegistryError(f'Skill is already registered: {definition.name}')
        self._definitions[definition.name] = definition

    def get(self, name: str) -> SkillDefinition:
        try:
            return self._definitions[name]
        except KeyError as error:
            raise SkillRegistryError(f'Unregistered Skill: {name}') from error

    def definitions(self) -> tuple[SkillDefinition, ...]:
        return tuple(self._definitions.values())

    def normalize_arguments(self, name: str, arguments: Mapping[str, object]) -> dict[str, object]:
        return self.get(name).normalize_arguments(arguments)

    def dispatch(self, name: str, user: object, arguments: Mapping[str, object]) -> Mapping[str, object]:
        definition = self.get(name)
        normalized_arguments = definition.normalize_arguments(arguments)
        return definition.handler(user, normalized_arguments)