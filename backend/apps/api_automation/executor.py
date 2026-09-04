from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import requests
from django.db.models import QuerySet
from django.utils import timezone
from django_q.exceptions import TimeoutException

from apps.api_automation.models import (
    ApiAutomationCase,
    ApiAutomationCaseResult,
    ApiAutomationRun,
)
from apps.core.models import EnvironmentConfiguration
from apps.api_automation.runner_client import execute_case as execute_case_in_runner
from apps.api_automation.runner_client import generate_run_report
from apps.api_automation.runner_client import is_configured as runner_is_configured
from apps.core.variable_resolver import VariableResolver


logger = logging.getLogger(__name__)
MINIMUM_RUN_TASK_TIMEOUT_SECONDS = 300
MAXIMUM_RUN_TASK_TIMEOUT_SECONDS = 32_400
RUN_FINALIZATION_BUFFER_SECONDS = 120
RUNNER_REQUEST_BUFFER_SECONDS = 15


def _log_run(run: ApiAutomationRun, level: int, message: str, *args: object) -> None:
    logger.log(level, 'run_id=%s project_id=%s ' + message, run.id, run.project_id, *args)


@dataclass
class ExecutionContext:
    configuration: EnvironmentConfiguration
    resolver: VariableResolver
    variables: dict[str, Any]
    session: requests.Session = field(default_factory=requests.Session)
    headers: dict[str, str] = field(default_factory=dict)


def execute_run(run_id: int) -> None:
    run = ApiAutomationRun.objects.select_related('configuration').get(id=run_id)
    if run.status == 'CANCELLED':
        _log_run(run, logging.INFO, 'execution skipped because the run was cancelled.')
        return

    run.status = 'RUNNING'
    run.started_at = timezone.now()
    run.save(update_fields=['status', 'started_at'])

    cases = list(_selected_cases(run))
    run.total_cases = sum(_expected_test_count(case) for case in cases)
    run.save(update_fields=['total_cases'])
    _log_run(run, logging.INFO, 'execution started with %s selected test(s).', run.total_cases)

    try:
        for case in cases:
            run.current_case_name = case.name
            run.save(update_fields=['current_case_name'])
            _log_run(run, logging.INFO, 'case started: case_id=%s name=%s.', case.id, case.name)
            result = _execute_case(run=run, case=case, configuration=run.configuration)
            ApiAutomationCaseResult.objects.update_or_create(
                run=run,
                case=case,
                defaults=result,
            )
            _log_run(
                run,
                logging.ERROR if result['status'] in {'FAILED', 'ERROR'} else logging.INFO,
                'case finished: case_id=%s name=%s status=%s duration_ms=%s error=%s.',
                case.id,
                case.name,
                result['status'],
                result.get('duration_ms'),
                result.get('error_message', ''),
            )
            _update_run_progress(run, cases, include_remaining=True)
    except TimeoutException:
        _log_run(run, logging.ERROR, 'execution exceeded its Django-Q task timeout.')
        _finalize_run(run, cases=cases, force_failed=True)
        return

    _finalize_run(run, cases=cases)


def estimate_run_task_timeout(run: ApiAutomationRun) -> int:
    case_count = _selected_cases(run).count()
    case_timeout = run.configuration.timeout_seconds if run.configuration is not None else 30
    estimated_timeout = max(
        MINIMUM_RUN_TASK_TIMEOUT_SECONDS,
        case_count * (case_timeout + RUNNER_REQUEST_BUFFER_SECONDS) + RUN_FINALIZATION_BUFFER_SECONDS,
    )
    return min(estimated_timeout, MAXIMUM_RUN_TASK_TIMEOUT_SECONDS)


def _finalize_run(
    run: ApiAutomationRun,
    cases: list[ApiAutomationCase] | None = None,
    force_failed: bool = False,
) -> None:
    _update_run_progress(run, cases or list(_selected_cases(run)), include_remaining=False)
    run.current_case_name = ''
    run.ended_at = timezone.now()
    if runner_is_configured():
        try:
            report = generate_run_report(run)
            if report.get('status') == 'PASSED':
                run.report_path = report.get('report_path', '')
                report_counts = report.get('test_counts', {})
                if all(isinstance(report_counts.get(name), int) for name in ('total', 'passed', 'failed', 'skipped')):
                    run.total_cases = report_counts['total']
                    run.passed_cases = report_counts['passed']
                    run.failed_cases = report_counts['failed']
                    run.skipped_cases = report_counts['skipped']
        except requests.RequestException:
            pass
    if force_failed and not run.failed_cases:
        _log_run(run, logging.ERROR, 'execution timed out without a recorded failed test.')
    run.status = 'FAILED' if run.failed_cases else 'COMPLETED'
    run.save(
        update_fields=['total_cases', 'passed_cases', 'failed_cases', 'skipped_cases', 'current_case_name', 'status', 'ended_at', 'report_path']
    )
    _log_run(
        run,
        logging.ERROR if run.status == 'FAILED' else logging.INFO,
        'execution finished: status=%s total=%s passed=%s failed=%s skipped=%s report_path=%s.',
        run.status,
        run.total_cases,
        run.passed_cases,
        run.failed_cases,
        run.skipped_cases,
        run.report_path or '-',
    )


def _expected_test_count(case: ApiAutomationCase) -> int:
    return len(case.parameter_sets) if case.parameter_sets else 1


def _result_test_counts(result: dict[str, Any]) -> dict[str, int]:
    details = result.get('details') or {}
    counts = details.get('test_counts') if isinstance(details, dict) else None
    if isinstance(counts, dict) and all(isinstance(counts.get(name), int) for name in ('total', 'passed', 'failed', 'skipped')):
        return {
            **counts,
            'schema_warnings': int(result['status'] == 'SCHEMA_WARNING'),
        }
    status = result['status']
    return {
        'total': 1,
        'passed': int(status in {'PASSED', 'SCHEMA_WARNING'}),
        'failed': int(status in {'FAILED', 'ERROR'}),
        'skipped': int(status == 'SKIPPED'),
        'schema_warnings': int(status == 'SCHEMA_WARNING'),
    }


def _update_run_progress(
    run: ApiAutomationRun,
    cases: list[ApiAutomationCase],
    include_remaining: bool,
) -> None:
    result_by_case = {
        result['case_id']: result
        for result in run.case_results.values('case_id', 'status', 'details')
    }
    totals = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'schema_warnings': 0}
    for case in cases:
        result = result_by_case.get(case.id)
        if result is None:
            if include_remaining:
                totals['total'] += _expected_test_count(case)
            continue
        counts = _result_test_counts(result)
        for name in totals:
            totals[name] += counts[name]
    run.total_cases = totals['total']
    run.passed_cases = totals['passed']
    run.failed_cases = totals['failed']
    run.skipped_cases = totals['skipped']
    run.schema_warning_cases = totals['schema_warnings']
    run.save(update_fields=['total_cases', 'passed_cases', 'schema_warning_cases', 'failed_cases', 'skipped_cases'])


def _selected_cases(run: ApiAutomationRun) -> QuerySet[ApiAutomationCase]:
    selection = run.selection or {}
    cases = ApiAutomationCase.objects.filter(suite__project=run.project, is_active=True).prefetch_related('steps')
    case_ids = selection.get('case_ids')
    if case_ids:
        return cases.filter(id__in=case_ids)
    suite_id = selection.get('suite_id')
    if suite_id:
        return cases.filter(suite_id=suite_id)
    source_path_prefix = selection.get('source_path_prefix')
    if isinstance(source_path_prefix, str) and source_path_prefix:
        return cases.filter(source_path__startswith=f'{source_path_prefix.rstrip("/")}/')
    return cases


def _execute_case(
    run: ApiAutomationRun,
    case: ApiAutomationCase,
    configuration: EnvironmentConfiguration | None,
) -> dict[str, Any]:
    if case.is_skipped:
        return {
            'status': 'SKIPPED',
            'error_message': case.skip_reason,
            'details': {},
        }
    if configuration is not None and runner_is_configured():
        return _execute_case_in_runner(run, case, configuration)
    if case.execution_mode != 'STRUCTURED':
        return {
            'status': 'SKIPPED',
            'error_message': '该用例包含需由隔离代码执行器运行的代码逻辑。',
            'details': {'execution_mode': case.execution_mode},
        }
    if configuration is None:
        return {
            'status': 'ERROR',
            'error_message': '结构化用例执行需要关联 API 自动化配置。',
            'details': {},
        }

    start_time = time.monotonic()
    context = ExecutionContext(
        configuration=configuration,
        resolver=VariableResolver(),
        variables=configuration.variables or {},
    )
    step_results: list[dict[str, Any]] = []
    try:
        for step in case.steps.filter(is_executable=True):
            step_result = _execute_step(step, context)
            step_results.append(step_result)
            if not step_result['passed']:
                return {
                    'status': 'FAILED',
                    'duration_ms': (time.monotonic() - start_time) * 1000,
                    'error_message': step_result['error'],
                    'details': {'steps': step_results},
                }
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as error:
        return {
            'status': 'ERROR',
            'duration_ms': (time.monotonic() - start_time) * 1000,
            'error_message': str(error),
            'details': {'steps': step_results},
        }

    return {
        'status': 'PASSED',
        'duration_ms': (time.monotonic() - start_time) * 1000,
        'details': {'steps': step_results},
    }


def _execute_case_in_runner(
    run: ApiAutomationRun,
    case: ApiAutomationCase,
    configuration: EnvironmentConfiguration,
) -> dict[str, Any]:
    try:
        result = execute_case_in_runner(run, case, configuration)
    except requests.RequestException as error:
        return {
            'status': 'ERROR',
            'error_message': f'Runner 请求失败: {error}',
            'details': {'runner': True},
        }
    test_counts = result.get('test_counts', {})
    result_status = result.get('status', 'ERROR')
    if (
        result_status == 'PASSED'
        and isinstance(test_counts, dict)
        and test_counts.get('total', 0) > 0
        and test_counts.get('skipped') == test_counts.get('total')
    ):
        result_status = 'SKIPPED'
    details = {
        'runner': True,
        'test_counts': test_counts,
        'stdout': result.get('stdout', ''),
        'stderr': result.get('stderr', ''),
        'artifacts': result.get('artifacts', {}),
    }
    schema_validation = _schema_validation_details(details['stdout'], details['stderr'])
    if schema_validation is not None:
        details['schema_validation'] = schema_validation
    schema_warnings = result.get('schema_warnings', [])
    if isinstance(schema_warnings, list) and schema_warnings:
        details['schema_warnings'] = schema_warnings
    return {
        'status': result_status,
        'duration_ms': result.get('duration_ms'),
        'error_message': result.get('error') or result.get('stderr', ''),
        'details': details,
    }


def _schema_validation_details(stdout: str, stderr: str) -> dict[str, str] | None:
    match = re.search(
        r'HTTP Schema 校验失败 \[(?P<method>\w+) (?P<path>.+) (?P<status>\d+)\]: (?P<field>.*?): (?P<message>.+)',
        f'{stdout}\n{stderr}',
    )
    if match is None:
        return None
    return match.groupdict()


def _execute_step(step, context: ExecutionContext) -> dict[str, Any]:
    if step.step_type == 'AUTHENTICATE':
        return _authenticate(step.request_data, context)
    if step.step_type == 'WEBSOCKET_REQUEST':
        return _execute_websocket_request(step.request_data, step.assertions, context)
    if step.step_type == 'MODEL_REQUEST':
        return _execute_model_request(step.request_data, step.assertions, context)
    if step.step_type == 'PAYMENT_ACTION':
        return _execute_payment_action(step.request_data, step.assertions, context)
    if step.step_type != 'HTTP_REQUEST':
        raise ValueError(f'不支持执行步骤类型: {step.step_type}')

    request_data = step.request_data
    assertions = step.assertions
    method = str(request_data.get('method', '')).upper()
    endpoint_path = _resolve_value(
        request_data.get('endpoint_path') or request_data.get('endpoint'),
        context.variables,
        context.resolver,
    )
    if not method or not isinstance(endpoint_path, str):
        raise ValueError('请求步骤缺少可执行的 HTTP 方法或接口路径。')

    url = endpoint_path if endpoint_path.startswith(('http://', 'https://')) else urljoin(
        f'{context.configuration.base_url.rstrip("/")}/', endpoint_path.lstrip('/'),
    )
    headers = _resolve_value(request_data.get('headers', {}), context.variables, context.resolver)
    response = context.session.request(
        method=method,
        url=url,
        params=_resolve_value(request_data.get('params', {}), context.variables, context.resolver),
        headers={**context.headers, **headers},
        json=_resolve_value(request_data.get('body', {}), context.variables, context.resolver),
        timeout=context.configuration.timeout_seconds,
    )
    assertion_results = [_evaluate_assertion(assertion, response) for assertion in assertions]
    failed_assertion = next((result for result in assertion_results if not result['passed']), None)
    return {
        'method': method,
        'url': url,
        'status_code': response.status_code,
        'passed': failed_assertion is None,
        'error': failed_assertion['error'] if failed_assertion else '',
        'assertions': assertion_results,
    }


def _authenticate(request_data: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
    role = str(request_data.get('role', '')).lower()
    profile = context.configuration.auth_profiles.get(role, {})
    if not profile:
        raise ValueError(f'未配置认证角色: {role}')
    password_mode = profile.get('password_mode', 'plain')
    if password_mode != 'plain':
        raise ValueError(f'认证角色 {role} 使用 {password_mode} 密码转换，需配置独立认证适配器。')
    username = _resolve_value(profile.get('username'), context.variables, context.resolver)
    password = _resolve_value(profile.get('password'), context.variables, context.resolver)
    if not username or not password:
        raise ValueError(f'认证角色 {role} 缺少用户名或密码引用。')
    login_path = profile.get('login_path', '/auth/login')
    url = login_path if login_path.startswith(('http://', 'https://')) else urljoin(
        f'{context.configuration.base_url.rstrip("/")}/', login_path.lstrip('/'),
    )
    response = context.session.post(
        url,
        json={profile.get('username_field', 'email'): username, profile.get('password_field', 'password'): password},
        timeout=context.configuration.timeout_seconds,
    )
    response.raise_for_status()
    response_data = response.json()
    token = _get_nested_value(response_data, profile.get('token_path', 'token'))
    if not token:
        raise ValueError(f'认证角色 {role} 的响应中缺少 token。')
    context.headers[profile.get('authorization_header', 'Authorization')] = f"{profile.get('token_prefix', '')}{token}"
    org_id = _get_nested_value(response_data, profile.get('organization_path', 'user.organization.id'))
    if org_id is not None:
        context.headers[profile.get('organization_header', 'x-org-id')] = str(org_id)
    return {'type': 'AUTHENTICATE', 'role': role, 'passed': True, 'status_code': response.status_code, 'error': ''}


def _execute_websocket_request(
    request_data: dict[str, Any], assertions: list[dict[str, Any]], context: ExecutionContext
) -> dict[str, Any]:
    websocket_url = _resolve_value(request_data.get('url') or context.configuration.websocket_url, context.variables, context.resolver)
    payload = _resolve_value(request_data.get('payload'), context.variables, context.resolver)
    if not websocket_url or not isinstance(payload, dict):
        raise ValueError('WebSocket 步骤缺少连接地址或 JSON 请求体。')

    async def send_and_receive() -> dict[str, Any]:
        import websockets

        try:
            connection = await websockets.connect(websocket_url, additional_headers=context.headers)
        except TypeError:
            connection = await websockets.connect(websocket_url, extra_headers=context.headers)
        async with connection:
            await connection.send(json.dumps(payload))
            return json.loads(await asyncio.wait_for(connection.recv(), context.configuration.timeout_seconds))

    response_data = asyncio.run(send_and_receive())
    assertion_results = [_evaluate_data_assertion(assertion, response_data) for assertion in assertions]
    failed_assertion = next((item for item in assertion_results if not item['passed']), None)
    return {'type': 'WEBSOCKET_REQUEST', 'passed': failed_assertion is None, 'response': response_data, 'assertions': assertion_results, 'error': failed_assertion['error'] if failed_assertion else ''}


def _execute_model_request(
    request_data: dict[str, Any], assertions: list[dict[str, Any]], context: ExecutionContext
) -> dict[str, Any]:
    profile_name = request_data.get('profile')
    profile = context.configuration.model_profiles.get(profile_name, {})
    if not profile:
        raise ValueError(f'未配置模型服务: {profile_name}')
    url = _resolve_value(profile.get('url'), context.variables, context.resolver)
    headers = _resolve_value(profile.get('headers', {}), context.variables, context.resolver)
    payload = _resolve_value(request_data.get('payload', {}), context.variables, context.resolver)
    response = context.session.post(url, json=payload, headers=headers, timeout=context.configuration.timeout_seconds)
    response.raise_for_status()
    response_data = response.json()
    assertion_results = [_evaluate_data_assertion(assertion, response_data) for assertion in assertions]
    failed_assertion = next((item for item in assertion_results if not item['passed']), None)
    return {'type': 'MODEL_REQUEST', 'passed': failed_assertion is None, 'status_code': response.status_code, 'response': response_data, 'assertions': assertion_results, 'error': failed_assertion['error'] if failed_assertion else ''}


def _execute_payment_action(
    request_data: dict[str, Any], assertions: list[dict[str, Any]], context: ExecutionContext
) -> dict[str, Any]:
    payment_config = context.configuration.payment_config
    base_url = _resolve_value(payment_config.get('base_url'), context.variables, context.resolver)
    endpoint = _resolve_value(request_data.get('endpoint'), context.variables, context.resolver)
    if not base_url or not endpoint:
        raise ValueError('支付步骤缺少支付 Mock 服务地址或动作端点。')
    headers = _resolve_value(payment_config.get('headers', {}), context.variables, context.resolver)
    response = context.session.post(
        urljoin(f'{base_url.rstrip("/")}/', endpoint.lstrip('/')),
        json=_resolve_value(request_data.get('payload', {}), context.variables, context.resolver),
        headers=headers,
        timeout=context.configuration.timeout_seconds,
    )
    response.raise_for_status()
    response_data = response.json() if response.content else {}
    assertion_results = [_evaluate_data_assertion(assertion, response_data) for assertion in assertions]
    failed_assertion = next((item for item in assertion_results if not item['passed']), None)
    return {'type': 'PAYMENT_ACTION', 'passed': failed_assertion is None, 'status_code': response.status_code, 'response': response_data, 'assertions': assertion_results, 'error': failed_assertion['error'] if failed_assertion else ''}


def _resolve_value(value: Any, variables: dict[str, Any], resolver: VariableResolver) -> Any:
    if isinstance(value, dict):
        if set(value) == {'expression'}:
            raise ValueError(f"无法执行动态 Python 表达式: {value['expression']}")
        return {key: _resolve_value(item, variables, resolver) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, variables, resolver) for item in value]
    if not isinstance(value, str):
        return value

    resolved = value
    for key, item in variables.items():
        if isinstance(item, dict):
            replacement = item.get('currentValue', item.get('initialValue', ''))
        else:
            replacement = item
        resolved = resolved.replace(f'{{{{{key}}}}}', str(replacement))
    return resolver.resolve(resolved)


def _evaluate_assertion(assertion: dict[str, Any], response: requests.Response) -> dict[str, Any]:
    assertion_type = assertion.get('type', '')
    arguments = assertion.get('arguments', [])
    if assertion_type == 'assert_status_code' and len(arguments) >= 2:
        expected = arguments[1]
        passed = response.status_code == expected
        return {
            'type': assertion_type,
            'passed': passed,
            'expected': expected,
            'actual': response.status_code,
            'error': '' if passed else f'状态码断言失败: 期望 {expected}, 实际 {response.status_code}',
        }
    if assertion_type == 'assert_header' and len(arguments) >= 3:
        header_name = arguments[1]
        expected = arguments[2]
        actual = response.headers.get(header_name)
        passed = actual == expected
        return {
            'type': assertion_type,
            'passed': passed,
            'expected': expected,
            'actual': actual,
            'error': '' if passed else f'响应头断言失败: {header_name} 期望 {expected}, 实际 {actual}',
        }
    if assertion_type in {'assert_json_contains', 'assert_json_matches'} and len(arguments) >= 2:
        try:
            response_data = response.json()
        except requests.JSONDecodeError:
            return {'type': assertion_type, 'passed': False, 'expected': arguments[1], 'actual': None, 'error': '响应不是 JSON。'}
        if assertion_type == 'assert_json_matches':
            passed = response_data == arguments[1]
        else:
            expected_data = arguments[1]
            passed = isinstance(expected_data, dict) and all(response_data.get(key) == value for key, value in expected_data.items())
        return {
            'type': assertion_type,
            'passed': passed,
            'expected': arguments[1],
            'actual': response_data,
            'error': '' if passed else f'{assertion_type} 断言失败。',
        }
    return {
        'type': assertion_type,
        'passed': False,
        'expected': arguments,
        'actual': None,
        'error': f'暂不支持结构化执行断言: {assertion_type}',
    }


def _evaluate_data_assertion(assertion: dict[str, Any], response_data: Any) -> dict[str, Any]:
    assertion_type = assertion.get('type', '')
    path = assertion.get('path', '')
    expected = assertion.get('expected')
    actual = _get_nested_value(response_data, path) if path else response_data
    if assertion_type in {'equals', 'assert_equal'}:
        passed = actual == expected
    elif assertion_type in {'contains', 'assert_in'}:
        passed = expected in actual if actual is not None else False
    elif assertion_type in {'not_empty', 'assert_not_empty'}:
        passed = bool(actual)
    elif assertion_type in {'contains_key', 'assert_contains_key'}:
        passed = isinstance(actual, dict) and expected in actual
    else:
        return {
            'type': assertion_type,
            'passed': False,
            'expected': expected,
            'actual': actual,
            'error': f'暂不支持结构化数据断言: {assertion_type}',
        }
    return {
        'type': assertion_type,
        'passed': passed,
        'expected': expected,
        'actual': actual,
        'error': '' if passed else f'{assertion_type} 断言失败。',
    }


def _get_nested_value(data: Any, path: str) -> Any:
    current_value = data
    for part in path.split('.'):
        if isinstance(current_value, dict):
            current_value = current_value.get(part)
        elif isinstance(current_value, list) and part.isdigit():
            index = int(part)
            current_value = current_value[index] if 0 <= index < len(current_value) else None
        else:
            return None
        if current_value is None:
            return None
    return current_value