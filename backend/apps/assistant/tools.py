from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import json
import re
from django.db import models

from apps.ai_testing.models import AICase, AiProject


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: Callable[[Any, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolDetectionResult:
    matched: bool
    tool_call: ToolCall | None
    status: str
    error_code: str | None = None
    error_message: str | None = None


TOOL_CALL_SCHEMA = {
    'type': 'object',
    'required': ['name'],
    'properties': {
        'name': {'type': 'string'},
        'args': {'type': 'object'},
        'schema_version': {'type': 'string'},
    },
}


def get_tool_contract_prompt() -> str:
    return (
        '你可以根据用户问题决定是否调用工具。若需要调用工具，必须只返回 JSON，且严格遵循以下格式：\n'
        '{"tool_call":{"name":"list_ai_cases","args":{"limit":20},"schema_version":"v1"}}\n'
        '规则：\n'
        '1) 仅当确实需要工具时返回上述 JSON。\n'
        '2) JSON 之外不要输出任何文字、markdown、解释。\n'
        '3) 当前可用工具仅有 list_ai_cases（获取AI用例管理中的用例列表）。\n'
        '4) 若不需要工具，直接正常回答用户问题。'
    )


def _accessible_ai_project_queryset(user: Any):
    if user is None or not getattr(user, 'is_authenticated', False):
        return AiProject.objects.none()

    return AiProject.objects.filter(
        models.Q(unified_meta_project__owner=user)
        | models.Q(unified_meta_project__members__user=user)
        | models.Q(unified_meta_project__isnull=True, created_by=user)
    ).distinct()


def tool_list_ai_cases(user: Any, args: dict[str, Any]) -> dict[str, Any]:
    limit_raw = args.get('limit', 20)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))

    accessible_projects = _accessible_ai_project_queryset(user)
    queryset = AICase.objects.filter(
        models.Q(project__in=accessible_projects)
        | models.Q(project__isnull=True, created_by=user)
    ).distinct().order_by('-updated_at')[:limit]

    cases = []
    for case in queryset:
        cases.append(
            {
                'id': case.id,
                'name': case.name,
                'project_name': case.project.name if case.project else '未归档',
                'case_mode': case.case_mode,
                'updated_at': case.updated_at.isoformat() if case.updated_at else None,
            }
        )

    return {
        'tool': 'list_ai_cases',
        'count': len(cases),
        'cases': cases,
    }


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    'list_ai_cases': ToolDefinition(
        name='list_ai_cases',
        description='获取AI用例管理中的用例列表',
        handler=tool_list_ai_cases,
    ),
}


def _validate_tool_args(tool_name: str, args: dict[str, Any]) -> tuple[bool, dict[str, Any], str | None]:
    if tool_name == 'list_ai_cases':
        normalized = dict(args)
        if 'limit' not in normalized:
            normalized['limit'] = 20

        try:
            normalized['limit'] = int(normalized['limit'])
        except (TypeError, ValueError):
            return False, {}, 'invalid args.limit, expected integer'

        if not 1 <= normalized['limit'] <= 100:
            return False, {}, 'args.limit out of range: 1-100'

        return True, normalized, None

    return False, {}, f'unsupported tool for schema validation: {tool_name}'


def _extract_contract_tool_call(message: str, tool_call_payload: Any = None) -> dict[str, Any] | None:
    if isinstance(tool_call_payload, dict):
        return tool_call_payload

    text = str(message or '').strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    embedded = parsed.get('tool_call')
    if isinstance(embedded, dict):
        return embedded
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    normalized = str(text or '').strip()
    if not normalized:
        return None

    if normalized.startswith('```'):
        normalized = re.sub(r'^```(?:json)?\s*', '', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\s*```$', '', normalized)

    # Direct object
    try:
        parsed = json.loads(normalized)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Extract first JSON object block
    matched = re.search(r'(\{[\s\S]*\})', normalized)
    if not matched:
        return None
    try:
        parsed = json.loads(matched.group(1))
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def parse_tool_call_from_model_output(model_output: str) -> ToolDetectionResult:
    payload = _extract_json_object(model_output)
    if not isinstance(payload, dict):
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='no_contract',
            error_code='no_json_object',
            error_message='model output does not contain JSON object contract',
        )

    contract = payload.get('tool_call') if isinstance(payload.get('tool_call'), dict) else payload
    if not isinstance(contract, dict):
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='invalid_contract',
            error_code='contract_not_object',
            error_message='tool_call contract is not an object',
        )

    tool_name = contract.get('name')
    if not isinstance(tool_name, str) or tool_name not in TOOL_REGISTRY:
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='invalid_contract',
            error_code='unknown_tool_name',
            error_message=f'invalid tool name: {tool_name}',
        )

    args = contract.get('args', {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='invalid_contract',
            error_code='args_not_object',
            error_message='tool args must be an object',
        )

    valid, normalized_args, validate_error = _validate_tool_args(tool_name, args)
    if not valid:
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='args_validation_failed',
            error_code='invalid_tool_args',
            error_message=validate_error,
        )

    return ToolDetectionResult(
        matched=True,
        tool_call=ToolCall(name=tool_name, args=normalized_args),
        status='ok',
    )


def parse_tool_call_from_request_contract(message: str, tool_call_payload: Any = None) -> ToolDetectionResult:
    """Strict contract-based detection. No keyword matching.

    Accepted contract:
    {
      "name": "list_ai_cases",
      "args": {"limit": 20},
      "schema_version": "v1"
    }
    """
    payload = _extract_contract_tool_call(message=message, tool_call_payload=tool_call_payload)
    if not payload:
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='no_contract',
            error_code='no_tool_call_payload',
            error_message='request payload does not contain tool_call contract',
        )

    tool_name = payload.get('name')
    if not isinstance(tool_name, str) or tool_name not in TOOL_REGISTRY:
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='invalid_contract',
            error_code='unknown_tool_name',
            error_message=f'invalid tool name: {tool_name}',
        )

    args = payload.get('args', {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='invalid_contract',
            error_code='args_not_object',
            error_message='tool args must be an object',
        )

    valid, normalized_args, validate_error = _validate_tool_args(tool_name, args)
    if not valid:
        return ToolDetectionResult(
            matched=False,
            tool_call=None,
            status='args_validation_failed',
            error_code='invalid_tool_args',
            error_message=validate_error,
        )

    return ToolDetectionResult(
        matched=True,
        tool_call=ToolCall(name=tool_name, args=normalized_args),
        status='ok',
    )


def detect_tool_call_from_model_output(model_output: str) -> ToolCall | None:
    result = parse_tool_call_from_model_output(model_output)
    return result.tool_call if result.matched else None


def detect_tool_call(message: str, tool_call_payload: Any = None) -> ToolCall | None:
    result = parse_tool_call_from_request_contract(message=message, tool_call_payload=tool_call_payload)
    return result.tool_call if result.matched else None


def execute_tool_call(tool_call: ToolCall, user: Any) -> dict[str, Any]:
    tool_def = TOOL_REGISTRY.get(tool_call.name)
    if not tool_def:
        return {
            'tool': tool_call.name,
            'error': f'unknown tool: {tool_call.name}',
        }

    try:
        return tool_def.handler(user, tool_call.args)
    except Exception as exc:  # pragma: no cover
        return {
            'tool': tool_call.name,
            'error': str(exc),
        }


def format_tool_result_for_user(result: dict[str, Any]) -> str:
    if result.get('error'):
        return f"工具调用失败: {result.get('error')}"

    if result.get('tool') == 'list_ai_cases':
        cases = result.get('cases') or []
        if not cases:
            return '当前没有可访问的AI用例。'

        lines = [f"共找到 {len(cases)} 条AI用例："]
        for idx, case in enumerate(cases, start=1):
            lines.append(
                f"{idx}. [{case.get('id')}] {case.get('name')}"
                f" | 项目: {case.get('project_name')}"
                f" | 模式: {case.get('case_mode')}"
            )
        return '\n'.join(lines)

    return json.dumps(result, ensure_ascii=False)
