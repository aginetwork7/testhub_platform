"""Generic resource creation contract for data-factory capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .tools.business_tools import BusinessTools


def create_resource(resource_type: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Create one resource payload through a registered resource adapter."""
    if resource_type != 'alert_event':
        return {'success': False, 'error': f'Unsupported resource type: {resource_type}.'}

    result = BusinessTools.construct_alert_event(**dict(arguments))
    if not result.get('success'):
        return result
    payload = result.get('result')
    event_id = ((payload or {}).get('event') or {}).get('meta', {}).get('uuid')
    return {
        'success': True,
        'resource_type': resource_type,
        'resource_id': event_id,
        'resource': payload,
        'result': payload,
    }


def cleanup_resource(resource_reference: Mapping[str, Any]) -> dict[str, Any]:
    """Clean up a resource through a registered adapter when one is available."""
    resource_type = str(resource_reference.get('resource_type', '')).strip()
    resource_id = resource_reference.get('resource_id')
    if resource_type != 'alert_event' or not resource_id:
        return {'success': False, 'error': 'Unsupported resource cleanup request.'}
    return {'success': False, 'error': 'alert_event cleanup is not configured for this environment.'}