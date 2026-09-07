"""Server-owned invariants for compiling model-generated execution steps."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class StepCompilationError(ValueError):
    """Raised when a generated step cannot form a verifiable transition."""


def compile_browser_step(
    *,
    description: str,
    allowed_capabilities: Sequence[str],
    assertions: Sequence[dict[str, Any]],
    step_index: int,
    correlates_resource: str = '',
) -> dict[str, Any]:
    """Compile one browser transition with a mandatory immediate postcondition."""
    required_assertions = [
        assertion
        for assertion in assertions
        if isinstance(assertion, dict) and assertion.get('required', True) is not False
    ]
    if not required_assertions:
        raise StepCompilationError(
            f'Browser step {step_index} must declare at least one required assertion '
            'for the immediate state produced by its transition.'
        )

    compiled_capabilities = list(allowed_capabilities)
    if 'browser.inspect' not in compiled_capabilities:
        compiled_capabilities.append('browser.inspect')

    step: dict[str, Any] = {
        'executor': 'browser',
        'step_mode': 'ai',
        'description': description,
        'allowed_capabilities': compiled_capabilities,
        'assertions': list(assertions),
        'verification_required': True,
    }
    if correlates_resource:
        step['correlates_resource'] = correlates_resource
    return step