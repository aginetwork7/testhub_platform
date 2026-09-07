"""Resolve server-owned HTTP targets from global environment configuration."""

from __future__ import annotations

from collections.abc import Mapping


def resolve_http_target(configuration: object, target_key: str) -> dict[str, object]:
    """Return one configured read-only target without accepting planner URLs."""
    runtime_settings = getattr(configuration, 'runtime_settings', {})
    targets = runtime_settings.get('ai_testing_http_targets', {}) if isinstance(runtime_settings, Mapping) else {}
    target = targets.get(target_key) if isinstance(targets, Mapping) else None
    if not isinstance(target, Mapping):
        raise ValueError(f'Unsupported AI testing HTTP target: {target_key}.')
    methods = target.get('methods')
    path = target.get('path')
    if not isinstance(methods, list) or 'GET' not in methods or not isinstance(path, str) or not path.startswith('/'):
        raise ValueError(f'Invalid AI testing HTTP target: {target_key}.')
    return {'path': path, 'methods': ('GET',), 'auth_profile': target.get('auth_profile', 'default')}