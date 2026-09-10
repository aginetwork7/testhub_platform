from typing import Any


def _normalize_z_index(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_blocking_state(actionable_controls: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize blocking controls into the currently active top-layer contract."""
    layers: dict[str, dict[str, Any]] = {}
    for control in actionable_controls:
        if not isinstance(control, dict) or control.get('blocking_layer') is not True:
            continue
        selector = str(control.get('selector') or '').strip()
        layer_id = str(control.get('blocking_layer_id') or selector).strip()
        if not layer_id:
            continue
        layer = layers.setdefault(
            layer_id,
            {'layer_id': layer_id, 'z_index': 0, 'selectors': [], 'semantic_targets': [], 'dialog': False},
        )
        layer['dialog'] = layer['dialog'] or control.get('dialog_layer') is True
        layer['z_index'] = max(layer['z_index'], _normalize_z_index(control.get('z_index')))
        if selector and selector not in layer['selectors']:
            layer['selectors'].append(selector)
        role = str(control.get('role') or '').strip().casefold()
        name = str(control.get('name') or '').strip()
        target = {'role': role, 'accessible_name': name}
        if role and name and target not in layer['semantic_targets']:
            layer['semantic_targets'].append(target)

    ordered_layers = sorted(layers.values(), key=lambda layer: (-layer['z_index'], layer['layer_id']))
    if not ordered_layers:
        return {
            'is_blocked': False,
            'layers': [],
            'active_layer_ids': [],
            'allowed_selectors': [],
            'allowed_semantic_targets': [],
            'dialog_layer_ids': [],
        }

    active_z_index = ordered_layers[0]['z_index']
    active_layers = [layer for layer in ordered_layers if layer['z_index'] == active_z_index]
    return {
        'is_blocked': True,
        'layers': ordered_layers,
        'active_layer_ids': [layer['layer_id'] for layer in active_layers],
        'allowed_selectors': [selector for layer in active_layers for selector in layer['selectors']],
        'allowed_semantic_targets': [target for layer in active_layers for target in layer['semantic_targets']],
        'dialog_layer_ids': [layer['layer_id'] for layer in active_layers if layer['dialog']],
    }
