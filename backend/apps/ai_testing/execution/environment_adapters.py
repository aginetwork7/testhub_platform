"""Controlled capability adapters bound to global environment configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin

import requests

from .http_targets import resolve_http_target


def request_http(
    configuration: object,
    target_key: str,
    method: str = 'GET',
    params: Mapping[str, Any] | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Perform a read-only request to a server-registered environment target."""
    normalized_method = method.upper()
    target = resolve_http_target(configuration, target_key)
    if normalized_method not in target['methods']:
        raise ValueError(f'HTTP method {normalized_method} is not allowed for target: {target_key}.')
    base_url = str(getattr(configuration, 'base_url', '') or '').strip()
    if not base_url:
        raise ValueError('Global environment does not define a base URL.')
    response = (session or requests.Session()).request(
        normalized_method,
        urljoin(f'{base_url.rstrip("/")}/', str(target['path']).lstrip('/')),
        params=dict(params or {}),
        timeout=int(getattr(configuration, 'timeout_seconds', 30) or 30),
    )
    response.raise_for_status()
    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text
    evidence = {
        'type': 'network_response',
        'target_key': target_key,
        'method': normalized_method,
        'url': response.url,
        'status_code': response.status_code,
    }
    return {'response': payload, 'evidence': [evidence]}


def read_api_resource(
    configuration: object,
    resource: str,
    params: Mapping[str, Any] | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Read one configured API resource and return API evidence for assertions."""
    result = request_http(configuration, resource, params=params, session=session)
    return {
        **result,
        'evidence': [
            *result['evidence'],
            {'type': 'api_response', 'resource': resource, 'response': result['response']},
        ],
    }