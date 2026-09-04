"""Server-owned generic capabilities available to the AI testing Agent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityDefinition:
    name: str
    required_arguments: tuple[str, ...]
    evidence_types: tuple[str, ...]
    assertion_kinds: tuple[str, ...]
    risk_level: str


CAPABILITIES: dict[str, CapabilityDefinition] = {
    'browser.navigate': CapabilityDefinition('browser.navigate', ('url',), ('url_snapshot',), ('url',), 'controlled'),
    'browser.inspect': CapabilityDefinition('browser.inspect', (), ('dom_snapshot', 'media_state'), ('text', 'element_state', 'media', 'video'), 'read'),
    'browser.act': CapabilityDefinition('browser.act', ('action',), ('url_snapshot', 'dom_snapshot', 'media_state'), (), 'controlled'),
    'browser.capture': CapabilityDefinition('browser.capture', (), ('screenshot', 'dom_snapshot', 'media_state'), ('visual_change',), 'read'),
    'http.request': CapabilityDefinition('http.request', ('method', 'url'), ('network_response',), ('network',), 'controlled'),
    'api.read_resource': CapabilityDefinition('api.read_resource', ('resource',), ('api_response',), ('api_resource', 'field_value'), 'read'),
    'device.command': CapabilityDefinition('device.command', ('device_id', 'command'), ('command_receipt',), ('command_result',), 'controlled'),
    'data_factory.create': CapabilityDefinition('data_factory.create', ('resource_type',), ('api_response',), ('api_resource',), 'write'),
    'data_factory.cleanup': CapabilityDefinition('data_factory.cleanup', ('resource_reference',), ('api_response',), ('absence',), 'write'),
}


def get_capability(name: str) -> CapabilityDefinition:
    """Resolve an allowed capability or reject planner-invented tool names."""
    capability = CAPABILITIES.get(name)
    if capability is None:
        raise ValueError(f'Unsupported capability: {name}.')
    return capability


def validate_capability_arguments(name: str, arguments: dict[str, object]) -> None:
    """Validate that a planned capability has the minimum declared arguments."""
    capability = get_capability(name)
    missing = [argument for argument in capability.required_arguments if not arguments.get(argument)]
    if missing:
        raise ValueError(f'Capability {name} is missing arguments: {", ".join(missing)}.')


def validate_browser_action(action: str, allowed_capabilities: list[str]) -> None:
    """Reject browser actions that are not permitted by the planned step."""
    normalized_action = action.strip().lower()
    if normalized_action == 'assert':
        required_capability = 'browser.inspect'
    elif normalized_action == 'navigate':
        required_capability = 'browser.navigate'
    else:
        required_capability = 'browser.act'
    if required_capability not in allowed_capabilities:
        raise ValueError(
            f'Browser action {normalized_action} requires capability {required_capability}.'
        )


def allowed_browser_actions(allowed_capabilities: list[str]) -> list[str]:
    """Return browser actions permitted by the step's declared capabilities."""
    actions: list[str] = []
    if 'browser.navigate' in allowed_capabilities:
        actions.append('navigate')
    if 'browser.act' in allowed_capabilities:
        actions.extend([
            'click', 'double_click', 'right_click', 'hover',
            'fill', 'press', 'select', 'scroll', 'wait',
        ])
    if 'browser.inspect' in allowed_capabilities:
        actions.append('assert')
    return actions