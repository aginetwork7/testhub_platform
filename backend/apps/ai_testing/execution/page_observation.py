"""Structured, bounded page observations for browser planning."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from playwright.async_api import Error as PlaywrightError


logger = logging.getLogger('django')


async def capture_accessibility_snapshot(page: Any, max_nodes: int = 300) -> dict[str, object]:
    """Capture Chromium's computed accessibility tree without affecting execution."""
    session = None
    try:
        session = await page.context.new_cdp_session(page)
        frame_tree = await session.send('Page.getFrameTree')
        payload = await session.send('Accessibility.getFullAXTree')
        page_version = str(frame_tree.get('frameTree', {}).get('frame', {}).get('loaderId') or '')
        nodes = _normalize_accessibility_nodes(payload.get('nodes'), max_nodes=max_nodes)
        fingerprint_payload = json.dumps(
            {'page_version': page_version, 'nodes': nodes},
            ensure_ascii=True,
            sort_keys=True,
            separators=(',', ':'),
        )
        return {
            'snapshot_id': hashlib.sha256(fingerprint_payload.encode('utf-8')).hexdigest(),
            'page_version': page_version,
            'nodes': nodes,
        }
    except (AttributeError, KeyError, TypeError, PlaywrightError) as error:
        logger.warning('planner_v2 failed to capture accessibility snapshot: %s', error)
        return {'snapshot_id': '', 'page_version': '', 'nodes': []}
    finally:
        if session is not None:
            try:
                await session.detach()
            except (AttributeError, PlaywrightError):
                pass


def _normalize_accessibility_nodes(raw_nodes: object, max_nodes: int = 300) -> list[dict[str, object]]:
    if not isinstance(raw_nodes, list):
        return []

    normalized: list[dict[str, object]] = []
    for raw_node in raw_nodes:
        if len(normalized) >= max_nodes:
            break
        if not isinstance(raw_node, dict) or raw_node.get('ignored') is True:
            continue
        role = _ax_value(raw_node.get('role'))
        name = _ax_value(raw_node.get('name'))
        if not role and not name:
            continue
        node_id = str(raw_node.get('nodeId') or '').strip()
        if not node_id:
            continue
        properties = {
            str(item.get('name')): _ax_value(item.get('value'))
            for item in raw_node.get('properties', [])
            if isinstance(item, dict) and item.get('name') and _ax_value(item.get('value')) != ''
        }
        normalized.append({
            'node_id': f'ax:{node_id}',
            'backend_dom_node_id': raw_node.get('backendDOMNodeId'),
            'role': role,
            'name': name,
            'description': _ax_value(raw_node.get('description')),
            'value': _ax_value(raw_node.get('value')),
            'states': properties,
            'child_ids': [f'ax:{child_id}' for child_id in raw_node.get('childIds', []) if child_id],
        })
    return normalized


def _ax_value(value: object) -> object:
    if not isinstance(value, dict):
        return ''
    return value.get('value', '')