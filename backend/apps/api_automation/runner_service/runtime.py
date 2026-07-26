from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import requests


@dataclass
class RuntimeContext:
    configuration: dict[str, Any]
    session: requests.Session = field(default_factory=requests.Session)
    headers: dict[str, str] = field(default_factory=dict)


def run_case(spec: dict[str, Any]) -> dict[str, Any]:
    case = spec['case']
    if case.get('execution_mode') != 'STRUCTURED':
        return {'status': 'SKIPPED', 'error': '代码模式需要 TestHub 代码兼容运行时。', 'steps': []}

    context = RuntimeContext(configuration=spec['configuration'])
    step_results: list[dict[str, Any]] = []
    if context.configuration.get('auto_login_default_role', True):
        authentication = _authenticate({'role': context.configuration.get('default_role', 'customer')}, context)
        step_results.append(authentication)
        if not authentication['passed']:
            return {'status': 'FAILED', 'error': authentication['error'], 'steps': step_results}
    for step in case['steps']:
        if not step.get('is_executable', False):
            continue
        result = _run_step(step, context)
        step_results.append(result)
        if not result['passed']:
            return {'status': 'FAILED', 'error': result['error'], 'steps': step_results}
    return {'status': 'PASSED', 'error': '', 'steps': step_results}


def _run_step(step: dict[str, Any], context: RuntimeContext) -> dict[str, Any]:
    step_type = step['step_type']
    if step_type == 'AUTHENTICATE':
        return _authenticate(step['request_data'], context)
    if step_type == 'WEBSOCKET_REQUEST':
        return _websocket_request(step['request_data'], step.get('assertions', []), context)
    if step_type == 'MODEL_REQUEST':
        return _model_request(step['request_data'], step.get('assertions', []), context)
    if step_type == 'PAYMENT_ACTION':
        return _payment_action(step['request_data'], step.get('assertions', []), context)
    if step_type != 'HTTP_REQUEST':
        return {'passed': False, 'error': f'Runner 暂不支持步骤类型: {step_type}'}

    request_data = step['request_data']
    method = str(request_data.get('method', '')).upper()
    endpoint = _resolve(request_data.get('endpoint_path') or request_data.get('endpoint'), context.configuration)
    path_params = _resolve(request_data.get('path_params', {}), context.configuration)
    try:
        endpoint = str(endpoint).format(**path_params)
    except KeyError as error:
        return {'passed': False, 'error': f'接口路径缺少参数: {error}'}
    if not method or not endpoint:
        return {'passed': False, 'error': '请求步骤缺少 HTTP 方法或接口路径。'}
    base_url = context.configuration.get('base_url', '')
    url = endpoint if str(endpoint).startswith(('http://', 'https://')) else urljoin(f'{base_url.rstrip("/")}/', str(endpoint).lstrip('/'))
    response = context.session.request(
        method=method,
        url=url,
        params=_resolve(request_data.get('params', {}), context.configuration),
        json=_resolve(request_data.get('body', {}), context.configuration),
        headers={**context.headers, **_resolve(request_data.get('headers', {}), context.configuration)},
        timeout=context.configuration.get('timeout_seconds', 30),
    )
    assertions = [_assert_response(item, response) for item in step.get('assertions', [])]
    failed = next((item for item in assertions if not item['passed']), None)
    return {
        'passed': failed is None,
        'error': failed['error'] if failed else '',
        'status_code': response.status_code,
        'url': url,
        'assertions': assertions,
    }


def _websocket_request(request_data: dict[str, Any], assertions: list[dict[str, Any]], context: RuntimeContext) -> dict[str, Any]:
    websocket_url = _resolve(request_data.get('url') or context.configuration.get('websocket_url'), context.configuration)
    payload = _resolve(request_data.get('payload'), context.configuration)
    if not websocket_url or not isinstance(payload, dict):
        return {'passed': False, 'error': 'WebSocket 步骤缺少地址或 JSON 请求体。'}

    async def send_and_receive() -> dict[str, Any]:
        import websockets

        async with websockets.connect(websocket_url, additional_headers=context.headers) as connection:
            await connection.send(json.dumps(payload))
            return json.loads(await asyncio.wait_for(connection.recv(), context.configuration.get('timeout_seconds', 30)))

    response_data = asyncio.run(send_and_receive())
    if request_data.get('validate_response'):
        _validate_websocket_response(request_data, response_data, context)
    assertion_results = [_assert_data(assertion, response_data) for assertion in assertions]
    failed = next((item for item in assertion_results if not item['passed']), None)
    return {'passed': failed is None, 'error': failed['error'] if failed else '', 'response': response_data, 'assertions': assertion_results}


def _model_request(request_data: dict[str, Any], assertions: list[dict[str, Any]], context: RuntimeContext) -> dict[str, Any]:
    profile = context.configuration.get('model_profiles', {}).get(request_data.get('profile'), {})
    if not profile:
        return {'passed': False, 'error': f"模型服务未配置: {request_data.get('profile')}"}
    response = context.session.post(
        _resolve(profile.get('url'), context.configuration),
        json=_resolve(request_data.get('payload', {}), context.configuration),
        headers=_resolve(profile.get('headers', {}), context.configuration),
        timeout=context.configuration.get('timeout_seconds', 30),
    )
    response.raise_for_status()
    response_data = response.json()
    assertion_results = [_assert_data(assertion, response_data) for assertion in assertions]
    failed = next((item for item in assertion_results if not item['passed']), None)
    return {'passed': failed is None, 'error': failed['error'] if failed else '', 'response': response_data, 'assertions': assertion_results}


def _payment_action(request_data: dict[str, Any], assertions: list[dict[str, Any]], context: RuntimeContext) -> dict[str, Any]:
    payment_config = context.configuration.get('payment_config', {})
    base_url = _resolve(payment_config.get('base_url'), context.configuration)
    endpoint = _resolve(request_data.get('endpoint'), context.configuration)
    if not base_url or not endpoint:
        return {'passed': False, 'error': '支付 Mock 服务或操作端点未配置。'}
    response = context.session.post(
        urljoin(f'{base_url.rstrip("/")}/', str(endpoint).lstrip('/')),
        json=_resolve(request_data.get('payload', {}), context.configuration),
        headers=_resolve(payment_config.get('headers', {}), context.configuration),
        timeout=context.configuration.get('timeout_seconds', 30),
    )
    response.raise_for_status()
    response_data = response.json() if response.content else {}
    assertion_results = [_assert_data(assertion, response_data) for assertion in assertions]
    failed = next((item for item in assertion_results if not item['passed']), None)
    return {'passed': failed is None, 'error': failed['error'] if failed else '', 'response': response_data, 'assertions': assertion_results}


def _authenticate(request_data: dict[str, Any], context: RuntimeContext) -> dict[str, Any]:
    role = str(request_data.get('role', '')).lower()
    profile = context.configuration.get('auth_profiles', {}).get(role, {})
    username = _resolve(profile.get('username'), context.configuration)
    password = _resolve(profile.get('password'), context.configuration)
    if not profile or not username or not password:
        return {'passed': False, 'error': f'认证角色未配置: {role}'}
    password = _network_password(str(username), str(password), context.configuration, profile)
    login_path = profile.get('login_path', '/auth/login')
    base_url = context.configuration.get('base_url', '')
    url = login_path if login_path.startswith(('http://', 'https://')) else urljoin(f'{base_url.rstrip("/")}/', login_path.lstrip('/'))
    response = context.session.post(
        url,
        json={profile.get('username_field', 'email'): username, profile.get('password_field', 'password'): password},
        timeout=context.configuration.get('timeout_seconds', 30),
    )
    response.raise_for_status()
    payload = response.json()
    token = _nested(payload, profile.get('token_path', 'token'))
    if not token:
        return {'passed': False, 'error': f'认证响应缺少 token: {role}'}
    token_prefix = profile.get('token_prefix', '') if profile.get('apply_token_prefix', False) else ''
    context.headers[profile.get('authorization_header', 'Authorization')] = f"{token_prefix}{token}"
    org_id = _nested(payload, profile.get('organization_path', 'user.organization.id'))
    if org_id is not None:
        context.headers[profile.get('organization_header', 'x-org-id')] = str(org_id)
    return {'passed': True, 'error': '', 'status_code': response.status_code, 'role': role}


def _assert_response(assertion: dict[str, Any], response: requests.Response) -> dict[str, Any]:
    assertion_type = assertion.get('type', '')
    arguments = assertion.get('arguments', [])
    if assertion_type == 'assert_status_code' and len(arguments) >= 2:
        expected = arguments[1]
        passed = response.status_code == expected
        return {'type': assertion_type, 'passed': passed, 'error': '' if passed else f'状态码期望 {expected}，实际 {response.status_code}'}
    return {'type': assertion_type, 'passed': False, 'error': f'Runner 暂不支持断言: {assertion_type}'}


def _assert_data(assertion: dict[str, Any], response_data: Any) -> dict[str, Any]:
    assertion_type = assertion.get('type', '')
    expected = assertion.get('expected')
    actual = _nested(response_data, assertion.get('path', '')) if assertion.get('path') else response_data
    if assertion_type in {'equals', 'assert_equal'}:
        passed = actual == expected
    elif assertion_type in {'contains', 'assert_in'}:
        passed = expected in actual if actual is not None else False
    elif assertion_type in {'not_empty', 'assert_not_empty'}:
        passed = bool(actual)
    elif assertion_type in {'contains_key', 'assert_contains_key'}:
        passed = isinstance(actual, dict) and expected in actual
    else:
        return {'type': assertion_type, 'passed': False, 'error': f'Runner 暂不支持断言: {assertion_type}'}
    return {'type': assertion_type, 'passed': passed, 'error': '' if passed else f'{assertion_type} 断言失败。'}


def _resolve(value: Any, configuration: dict[str, Any]) -> Any:
    variables = configuration.get('variables', {})
    if isinstance(value, dict):
        if set(value) == {'expression'}:
            raise ValueError(f"不支持动态表达式: {value['expression']}")
        return {key: _resolve(item, configuration) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, configuration) for item in value]
    if not isinstance(value, str):
        return value
    for key, item in variables.items():
        replacement = item.get('currentValue', item.get('initialValue', '')) if isinstance(item, dict) else item
        value = value.replace(f'{{{{{key}}}}}', str(replacement))
    return value


def _network_password(username: str, password: str, configuration: dict[str, Any], profile: dict[str, Any]) -> str:
    if profile.get('password_mode', 'argon2_network') == 'plain':
        return password
    security = configuration.get('runtime_settings', {}).get('security', {}).get('password', {})
    fixed_salt = security.get('fixed_salt') or configuration.get('variables', {}).get('SALT')
    if not fixed_salt:
        raise ValueError('认证配置缺少 SALT，无法执行 Argon2 密码转换。')
    from argon2.low_level import Type, hash_secret_raw

    argon = security.get('argon2', {})
    first = argon.get('first_stage', {})
    second = argon.get('second_stage', {})
    password_salt = hash_secret_raw(
        secret=username.encode('ascii'),
        salt=str(fixed_salt).encode('ascii'),
        time_cost=first.get('time_cost', 1),
        memory_cost=first.get('memory_cost', 46) * 1024,
        parallelism=first.get('parallelism', 1),
        hash_len=first.get('hash_len', 16),
        type=Type.ID,
        version=19,
    ).hex()
    return hash_secret_raw(
        secret=password.encode('ascii'),
        salt=password_salt.encode('ascii'),
        time_cost=second.get('time_cost', 1),
        memory_cost=second.get('memory_cost', 46) * 1024,
        parallelism=second.get('parallelism', 1),
        hash_len=second.get('hash_len', 32),
        type=Type.ID,
        version=19,
    ).hex()


def _nested(data: Any, path: str) -> Any:
    if not path:
        return data
    current = data
    for key in path.split('.'):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _validate_websocket_response(request_data: dict[str, Any], response_data: dict[str, Any], context: RuntimeContext) -> None:
    error = response_data.get('result', {}).get('error')
    if error:
        raise AssertionError(f'WebSocket 返回错误: {error}')
    action = request_data.get('request', {}).get('act', '')
    schema = context.configuration.get('websocket_schemas', {}).get(action)
    if not schema:
        return
    from jsonschema import Draft7Validator

    errors = sorted(Draft7Validator(schema).iter_errors(response_data), key=lambda item: item.path)
    if errors:
        raise AssertionError(f'WebSocket Schema 校验失败: {errors[0].message}')