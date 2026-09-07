"""Immutable contracts shared by planning, execution, and verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssertionSpec:
    """One evidence-backed assertion requested by an execution plan."""

    assert_kind: str
    target: dict[str, Any]
    operator: str
    expected: dict[str, Any]
    evidence_requirements: tuple[str, ...]
    required: bool
    timeout_ms: int | None
    evidence_max_age_ms: int | None
