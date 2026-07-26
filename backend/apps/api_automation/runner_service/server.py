from __future__ import annotations

import hmac
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import time
import uuid
import re
from xml.etree import ElementTree
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


RUNNER_TOKEN = os.environ.get('API_AUTOMATION_RUNNER_TOKEN', '')
WORK_ROOT = Path(os.environ.get('API_AUTOMATION_RUNNER_WORK_ROOT', '/work'))
ARTIFACT_ROOT = Path(os.environ.get('API_AUTOMATION_RUNNER_ARTIFACT_ROOT', '/artifacts'))
MAX_REQUEST_BYTES = int(os.environ.get('API_AUTOMATION_RUNNER_MAX_REQUEST_BYTES', '1048576'))


class RunnerHandler(BaseHTTPRequestHandler):
    server_version = 'TestHubApiAutomationRunner/1.0'

    def do_GET(self) -> None:
        if self.path == '/healthz':
            self._write_json(HTTPStatus.OK, {'status': 'ok'})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {'error': 'not found'})

    def do_POST(self) -> None:
        if self.path not in {'/v1/runs', '/v1/reports'}:
            self._write_json(HTTPStatus.NOT_FOUND, {'error': 'not found'})
            return
        authorization = self.headers.get('Authorization', '')
        expected_authorization = f'Bearer {RUNNER_TOKEN}'
        if RUNNER_TOKEN and not hmac.compare_digest(authorization, expected_authorization):
            self._write_json(HTTPStatus.UNAUTHORIZED, {'error': 'unauthorized'})
            return
        try:
            content_length = int(self.headers.get('Content-Length', '0'))
            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                raise ValueError('invalid request size')
            payload = json.loads(self.rfile.read(content_length))
            result = _run_pytest_spec(payload) if self.path == '/v1/runs' else _generate_run_report(payload)
        except (ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
            self._write_json(HTTPStatus.BAD_REQUEST, {'error': str(error)})
            return
        self._write_json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args) -> None:
        return

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        response = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def _run_pytest_spec(spec: dict) -> dict:
    started = time.monotonic()
    run_id = str(spec.get('run_id', uuid.uuid4()))
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f'{run_id}-', dir=WORK_ROOT) as directory:
        workdir = Path(directory)
        spec_path = workdir / 'spec.json'
        test_path = workdir / 'test_case.py'
        junit_path = workdir / 'junit.xml'
        allure_path = workdir / 'allure'
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        test_path.write_text(_build_test_module(spec), encoding='utf-8')
        command = [
            'pytest', str(test_path), '--junitxml', str(junit_path),
            '--alluredir', str(allure_path), '--disable-warnings', '--tb=short',
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=int(spec.get('timeout_seconds', 90)),
                env={
                    'PATH': os.environ.get('PATH', ''),
                    'PYTHONPATH': str(Path(__file__).parent),
                    'TESTHUB_SPEC_PATH': str(spec_path),
                },
            )
        except subprocess.TimeoutExpired as error:
            return {
                'status': 'ERROR',
                'duration_ms': (time.monotonic() - started) * 1000,
                'stdout': (error.stdout or '')[-8000:],
                'stderr': (error.stderr or '')[-8000:],
                'error': 'pytest 执行超时。',
                'artifacts': {},
            }
        artifact_id = uuid.uuid4().hex
        artifact_dir = ARTIFACT_ROOT / f'run-{run_id}' / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        if junit_path.exists():
            shutil.copy2(junit_path, artifact_dir / 'junit.xml')
        if allure_path.exists():
            shutil.copytree(allure_path, artifact_dir / 'allure')
        test_counts = _junit_test_counts(junit_path)
        return {
            'status': 'PASSED' if completed.returncode == 0 else 'FAILED',
            'duration_ms': (time.monotonic() - started) * 1000,
            'stdout': completed.stdout[-8000:],
            'stderr': completed.stderr[-8000:],
            'test_counts': test_counts,
            'artifacts': {
                'path': str(artifact_dir.relative_to(ARTIFACT_ROOT)),
                'junit': f'{artifact_dir.relative_to(ARTIFACT_ROOT)}/junit.xml',
                'allure_dir': f'{artifact_dir.relative_to(ARTIFACT_ROOT)}/allure',
            },
        }


def _junit_test_counts(junit_path: Path) -> dict[str, int]:
    if not junit_path.is_file():
        return {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
    try:
        root = ElementTree.parse(junit_path).getroot()
    except ElementTree.ParseError:
        return {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
    test_cases = root.findall('.//testcase')
    skipped = sum(test_case.find('skipped') is not None for test_case in test_cases)
    failed = sum(
        test_case.find('failure') is not None or test_case.find('error') is not None
        for test_case in test_cases
    )
    total = len(test_cases)
    return {'total': total, 'passed': total - failed - skipped, 'failed': failed, 'skipped': skipped}


def _generate_run_report(payload: dict) -> dict:
    run_id = str(payload.get('run_id', ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('invalid run id')
    run_directory = ARTIFACT_ROOT / f'run-{run_id}'
    result_directories = sorted(path for path in run_directory.glob('*/allure') if path.is_dir() and any(path.iterdir()))
    if not result_directories:
        return {'status': 'ERROR', 'error': '该运行没有 Allure 原始结果。', 'report_path': ''}
    report_directory = run_directory / 'allure-report'
    try:
        completed = subprocess.run(
            ['allure', 'generate', *(str(path) for path in result_directories), '--clean', '--output', str(report_directory)],
            capture_output=True,
            text=True,
            timeout=90,
            env={'PATH': os.environ.get('PATH', '')},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'status': 'ERROR', 'error': f'Allure 完整报告生成失败: {error}', 'report_path': ''}
    report_index = report_directory / 'index.html'
    if completed.returncode != 0 or not report_index.is_file():
        return {'status': 'ERROR', 'error': completed.stderr[-1000:], 'report_path': ''}
    test_counts = _allure_test_counts(report_directory)
    return {
        'status': 'PASSED',
        'report_path': f'run-{run_id}/allure-report/index.html',
        'result_count': len(result_directories),
        'test_counts': test_counts,
    }


def _build_test_module(spec: dict) -> str:
    case = spec['case']
    if case.get('execution_mode') != 'CODE':
        function_name = re.sub(r'\W+', '_', str(case.get('source_function') or 'test_case'))
        if not function_name.startswith('test_'):
            function_name = f'test_{function_name}'
        return (
            'import json\n'
            'from runtime import run_case\n\n'
            f'def {function_name}():\n'
            '    spec = json.loads(open("spec.json", encoding="utf-8").read())\n'
            '    result = run_case(spec)\n'
            '    assert result["status"] == "PASSED", result.get("error", "")\n'
        )
    module_imports = _compatible_module_imports(case.get('module_imports', ''))
    module_support = textwrap.dedent(case.get('module_support_code', '')).strip()
    class_support = textwrap.indent(_normalize_class_support(case.get('class_support_code', '')), '    ')
    setup_code = textwrap.indent(textwrap.dedent(case.get('setup_code', '')).strip(), '    ')
    teardown_code = textwrap.indent(textwrap.dedent(case.get('teardown_code', '')).strip(), '    ')
    source_code = textwrap.indent(textwrap.dedent(case.get('source_code', '')).strip(), '    ')
    return (
        'import asyncio\nimport glob\nimport json\nimport os\nimport re\nimport time\nfrom pathlib import Path\n\n'
        'import pytest\nimport requests\n'
        'from code_compat import (Assertions, DataUtils, MODEL_RESULT_DIR, ModelHandler, PasswordEncryptor, RequestError, StripePaymentService, WebSocketRequest, config, logger, '\
        'WEBSOCKET_PARAMS, api_instance, create_websocket_client, faker)\n\n'
        f'{module_imports}\n\n'
        f'{module_support}\n\n'
        f'class {case.get("source_class") or "TestCase"}:\n'
        f'{class_support or "    pass"}\n\n'
        f'{setup_code}\n\n'
        f'{teardown_code}\n\n'
        f'{source_code}\n'
    )


def _allure_test_counts(report_directory: Path) -> dict[str, int]:
    summary_path = report_directory / 'widgets' / 'summary.json'
    try:
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
    statistic = summary.get('statistic', {})
    return {
        'total': int(statistic.get('total', 0)),
        'passed': int(statistic.get('passed', 0)),
        'failed': int(statistic.get('failed', 0)) + int(statistic.get('broken', 0)),
        'skipped': int(statistic.get('skipped', 0)),
    }


def _compatible_module_imports(source_imports: str) -> str:
    allowed_imports = {
        'arrow', 'datetime', 'json', 'os', 'pprint', 'pytest', 'random', 're', 'time', 'yaml',
    }
    compatible_lines: list[str] = []
    for line in source_imports.splitlines():
        stripped = line.strip()
        if stripped.startswith('import '):
            module_name = stripped.removeprefix('import ').split()[0].split('.')[0]
        elif stripped.startswith('from '):
            module_name = stripped.removeprefix('from ').split()[0].split('.')[0]
        else:
            continue
        if module_name in allowed_imports:
            compatible_lines.append(line)
    return '\n'.join(compatible_lines)


def _normalize_class_support(source_code: str) -> str:
    return textwrap.dedent(source_code).strip()


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 19000), RunnerHandler).serve_forever()