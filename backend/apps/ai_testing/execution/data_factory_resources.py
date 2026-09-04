"""Environment-authorized adapters for AI testing data-factory resources."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from apps.data_factory.tools.business_tools import BusinessTools


class DataFactoryResourceError(ValueError):
    """Raised when a configured data-factory resource cannot be executed."""


@dataclass(frozen=True)
class ResourceAdapter:
    name: str
    create: Callable[[object, Mapping[str, object], Mapping[str, object]], dict[str, object]]


def create_configured_resource(configuration: object, resource_type: str, arguments: Mapping[str, object]) -> dict[str, object]:
    resource = _configured_resource(configuration, resource_type)
    allowed_arguments = resource.get('allowed_arguments', [])
    if not isinstance(allowed_arguments, list) or not all(isinstance(item, str) for item in allowed_arguments):
        raise DataFactoryResourceError(f'Resource {resource_type} has invalid allowed_arguments.')
    unexpected = set(arguments).difference(allowed_arguments)
    if unexpected:
        raise DataFactoryResourceError(f'Resource {resource_type} received unsupported arguments: {", ".join(sorted(unexpected))}.')
    allowed_values = resource.get('allowed_values', {})
    if not isinstance(allowed_values, Mapping):
        raise DataFactoryResourceError(f'Resource {resource_type} has invalid allowed_values.')
    for name, values in allowed_values.items():
        if name in arguments and (not isinstance(values, list) or arguments[name] not in values):
            raise DataFactoryResourceError(f'Resource {resource_type} argument {name} has an unsupported value.')
    default_arguments = resource.get('default_arguments', {})
    if not isinstance(default_arguments, Mapping):
        raise DataFactoryResourceError(f'Resource {resource_type} has invalid default_arguments.')
    adapter_name = str(resource.get('adapter') or '').strip()
    adapter = ADAPTERS.get(adapter_name)
    if adapter is None:
        raise DataFactoryResourceError(f'Resource {resource_type} has no registered adapter.')
    return adapter.create(configuration, resource, {**default_arguments, **arguments})


def configured_resource_summaries(configuration: object) -> list[dict[str, object]]:
    settings = _settings(configuration)
    resources = settings.get('resources', {})
    if not isinstance(resources, Mapping):
        return []
    return [
        {'resource_type': str(name), 'allowed_arguments': list(resource.get('allowed_arguments', [])), 'allowed_values': resource.get('allowed_values', {})}
        for name, resource in resources.items()
        if isinstance(resource, Mapping) and resource.get('enabled') is True and str(resource.get('adapter') or '') in ADAPTERS
    ]


def _configured_resource(configuration: object, resource_type: str) -> Mapping[str, object]:
    resources = _settings(configuration).get('resources', {})
    resource = resources.get(resource_type) if isinstance(resources, Mapping) else None
    if not isinstance(resource, Mapping) or resource.get('enabled') is not True:
        raise DataFactoryResourceError(f'Resource {resource_type} is not enabled for this environment.')
    return resource


def _settings(configuration: object) -> Mapping[str, object]:
    runtime_settings = getattr(configuration, 'runtime_settings', {})
    settings = runtime_settings.get('ai_testing_data_factory', {}) if isinstance(runtime_settings, Mapping) else {}
    if not isinstance(settings, Mapping):
        raise DataFactoryResourceError('ai_testing_data_factory must be an object.')
    return settings


def _create_alert_event(configuration: object, resource: Mapping[str, object], arguments: Mapping[str, object]) -> dict[str, object]:
    device_name = str(resource.get('device') or '').strip()
    camera_index = resource.get('camera_index')
    if not device_name or not isinstance(camera_index, int) or camera_index < 0:
        raise DataFactoryResourceError('alert_event requires configured device and camera_index.')
    edge = ((getattr(configuration, 'runtime_settings', {}) or {}).get('api', {}) or {}).get('edge', {})
    device = edge.get(f'{device_name}_device', {}) if isinstance(edge, Mapping) else {}
    cameras = device.get('cameras', []) if isinstance(device, Mapping) else []
    if camera_index >= len(cameras) or not isinstance(cameras[camera_index], Mapping):
        raise DataFactoryResourceError('Configured alert_event camera is unavailable.')
    camera = cameras[camera_index]
    event_arguments = dict(arguments)
    media_prefix = str(event_arguments.pop('media_prefix', '') or '').strip()
    media_groups = []
    if media_prefix:
        alert_type = str(event_arguments.get('alert_type') or '').strip()
        media_root = Path(__file__).resolve().parents[2] / 'data_factory' / 'data_warehouse' / 'events' / alert_type
        media_file = media_root / f'{media_prefix}_snap_image_0.jpeg'
        try:
            media_groups = BusinessTools.collect_event_media(media_root, str(media_file.relative_to(media_root)))
        except ValueError as error:
            raise DataFactoryResourceError(str(error)) from error
        event_arguments['count'] = len(media_groups)
    payload = BusinessTools.construct_alert_event(
        camera_mac=str(camera.get('camera_mac') or ''),
        camera_name=str(camera.get('camera_name') or ''),
        **event_arguments,
    )
    if not payload.get('success'):
        raise DataFactoryResourceError(str(payload.get('error') or 'alert_event construction failed.'))
    device_key = configuration.get_event_device_key(device_name)
    report = BusinessTools.report_alert_events(
        events=[payload['result']], base_url=str(getattr(configuration, 'base_url', '') or ''),
        device_id=str(device.get('device_id') or ''), device_key=device_key,
        timeout_seconds=int(getattr(configuration, 'timeout_seconds', 30)), paths=edge.get('path', {}),
        media_groups=media_groups or None, s3_url=str(edge.get('s3_url') or ''),
    )
    if not report.get('success') or not report.get('event_ids'):
        raise DataFactoryResourceError(str(report.get('error') or 'alert_event reporting failed.'))
    return {
        'success': True,
        'resource_type': 'alert_event',
        'resource_id': report['event_ids'][0],
        'resource': {
            'event_ids': report['event_ids'],
            'media_prefix': media_prefix,
            'result_correlation': {
                **dict(resource.get('result_correlation', {})),
                'match_values': [
                    str(camera.get('camera_name') or '').strip(),
                    str(event_arguments.get('alert_type') or '').strip(),
                ],
            },
        },
    }


ADAPTERS: dict[str, ResourceAdapter] = {'alert_event': ResourceAdapter('alert_event', _create_alert_event)}