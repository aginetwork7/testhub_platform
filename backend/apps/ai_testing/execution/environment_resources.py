"""Expose environment-configured test devices to the planner as execution-scoped resources.

Case descriptions refer to "the default test device" or "the target camera". The environment
configuration already names that device (``runtime_settings.api.edge.main_device``) and its cameras,
but nothing carried the names into planning, so the model picked a camera by guesswork. Publishing the
devices as resources lets the visual planner name the camera and lets the runtime correct a click that
lands on a neighbouring card.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

ENVIRONMENT_DEVICE_RESOURCE_TYPE = 'environment_device'
_DEVICE_ROLES = ('main_device', 'backup_device')
_TARGET_DEVICE_PATTERN = re.compile(
    r'\b(default|target|test)\s+(test\s+)?(device|camera)\b|默认.{0,6}(设备|摄像头)|目标.{0,6}(camera|摄像头|设备)',
    re.IGNORECASE,
)


def environment_device_resources(configuration: Any) -> list[dict[str, Any]]:
    """Return one resource per configured device, main device first; [] when none is configured."""
    runtime_settings = getattr(configuration, 'runtime_settings', None)
    if not isinstance(runtime_settings, Mapping):
        return []
    edge = (runtime_settings.get('api') or {}).get('edge') if isinstance(runtime_settings.get('api'), Mapping) else None
    if not isinstance(edge, Mapping):
        return []
    resources: list[dict[str, Any]] = []
    for role in _DEVICE_ROLES:
        device = edge.get(role)
        if not isinstance(device, Mapping):
            continue
        device_id = str(device.get('device_id') or '').strip()
        cameras = [
            str(camera.get('camera_name') or '').strip()
            for camera in (device.get('cameras') or [])
            if isinstance(camera, Mapping) and str(camera.get('camera_name') or '').strip()
        ]
        if not device_id and not cameras:
            continue
        label = 'default test device' if role == 'main_device' else 'backup test device'
        site = str(device.get('site') or device.get('site_name') or device.get('group') or '').strip()
        location = f' The cameras are listed under the site group "{site}"; searching that site name also reveals them.' if site else ''
        resources.append({
            'resource_type': ENVIRONMENT_DEVICE_RESOURCE_TYPE,
            'resource_id': device_id or role,
            'producer_step': 0,
            'resource': {
                'role': role,
                'device_id': device_id,
                'camera_names': cameras,
                'site': site,
                'description': (
                    f'{label} ({role}) configured for this environment; steps that refer to the default or '
                    f'target device or camera mean this device and its cameras: {", ".join(cameras) or device_id}.{location}'
                ),
                'result_correlation': {'match_values': cameras or [device_id]},
            },
        })
    return resources


def default_device_site(execution_resources: list[dict[str, Any]] | None) -> str:
    """Site group of the main device when the environment configuration names one."""
    for role in ('main_device', 'backup_device'):
        for resource in execution_resources or []:
            if not isinstance(resource, dict) or resource.get('resource_type') != ENVIRONMENT_DEVICE_RESOURCE_TYPE:
                continue
            payload = resource.get('resource') if isinstance(resource.get('resource'), dict) else {}
            if str(payload.get('role') or '') == role and str(payload.get('site') or '').strip():
                return str(payload.get('site')).strip()
    return ''


def is_text_input(element: dict[str, Any]) -> bool:
    """Inputs echo their own value as a name and must never count as the item they name.

    Only real form fields qualify. Discovery marks every non-disabled element as ``editable`` (the flag means
    "not readonly/disabled"), so it is deliberately not consulted here: relying on it excluded every card and
    button and silently disabled the target-camera rules.
    """
    tag = str(element.get('tag') or '').strip().casefold()
    role = str(element.get('role') or '').strip().casefold()
    return tag in {'input', 'textarea', 'select'} or role in {'textbox', 'searchbox', 'combobox'}


def default_device_camera_names(execution_resources: list[dict[str, Any]] | None) -> list[str]:
    """Camera names of the main device among execution resources (backup device only when no main device)."""
    by_role: dict[str, list[str]] = {}
    for resource in execution_resources or []:
        if not isinstance(resource, dict) or resource.get('resource_type') != ENVIRONMENT_DEVICE_RESOURCE_TYPE:
            continue
        payload = resource.get('resource') if isinstance(resource.get('resource'), dict) else {}
        names = [str(name).strip() for name in payload.get('camera_names') or [] if str(name).strip()]
        if names:
            by_role.setdefault(str(payload.get('role') or ''), []).extend(names)
    return by_role.get('main_device') or by_role.get('backup_device') or []


def refers_to_target_device(step_description: str, camera_names: list[str] | None = None) -> bool:
    """True when a step talks about the default/target/test device or camera, or names a configured camera."""
    text = str(step_description or '')
    if _TARGET_DEVICE_PATTERN.search(text):
        return True
    lowered = text.casefold()
    return any(str(name).strip() and str(name).strip().casefold() in lowered for name in camera_names or [])
