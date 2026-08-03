from __future__ import annotations

import hmac
import json
import os
import re
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pexpect


RUNNER_TOKEN = os.environ.get('DEVICE_CLI_RUNNER_TOKEN', '')
MAX_REQUEST_BYTES = int(os.environ.get('DEVICE_CLI_RUNNER_MAX_REQUEST_BYTES', '32768'))


class DeviceCliRunnerHandler(BaseHTTPRequestHandler):
    server_version = 'TestHubDeviceCliRunner/1.0'

    def do_GET(self) -> None:
        if self.path == '/healthz':
            self._write_json(HTTPStatus.OK, {'status': 'ok'})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {'error': 'not found'})

    def do_POST(self) -> None:
        if self.path != '/v1/device-cli/runs':
            self._write_json(HTTPStatus.NOT_FOUND, {'error': 'not found'})
            return
        expected = f'Bearer {RUNNER_TOKEN}'
        if RUNNER_TOKEN and not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
            self._write_json(HTTPStatus.UNAUTHORIZED, {'error': 'unauthorized'})
            return
        try:
            content_length = int(self.headers.get('Content-Length', '0'))
            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                raise ValueError('invalid request size')
            payload = json.loads(self.rfile.read(content_length))
            result = _run_device_command(payload)
        except (ValueError, json.JSONDecodeError) as error:
            self._write_json(HTTPStatus.BAD_REQUEST, {'error': str(error)})
            return
        self._write_json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args) -> None:
        return

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _run_device_command(payload: dict) -> dict:
    connection_command = str(payload.get('connection_command', '')).strip()
    remote_command = str(payload.get('remote_command', '')).strip()
    timeout_seconds = max(1, min(int(payload.get('timeout_seconds', 30)), 300))
    if (
        not connection_command.startswith('expect -c ')
        or '\n' in connection_command
        or len(connection_command) > 8192
    ):
        raise ValueError('invalid connection command')
    if not remote_command or '\n' in remote_command or len(remote_command) > 4096:
        raise ValueError('invalid remote command')

    marker = f'__TESTHUB_DEVICE_EXIT_{uuid.uuid4().hex}__'
    started = time.monotonic()
    child = pexpect.spawn('/bin/sh', ['-lc', connection_command], encoding='utf-8', timeout=timeout_seconds)
    try:
        child.sendline(
            f'export PAGER=cat SYSTEMD_PAGER=cat GIT_PAGER=cat; '
            f'{remote_command}; printf "\\n{marker}:%s\\n" $?'
        )
        child.expect(re.escape(marker) + r':(\d+)', timeout=timeout_seconds)
        exit_code = int(child.match.group(1))
        output = child.before[-8000:]
        child.sendline('exit')
        return {
            'status': 'PASSED' if exit_code == 0 else 'FAILED',
            'exit_code': exit_code,
            'duration_ms': round((time.monotonic() - started) * 1000, 2),
            'stdout': output,
            'stderr': '',
        }
    except pexpect.TIMEOUT:
        return {
            'status': 'ERROR',
            'error_type': 'remote_ssh',
            'exit_code': None,
            'duration_ms': round((time.monotonic() - started) * 1000, 2),
            'stdout': '',
            'stderr': '设备命令执行超时。',
        }
    except pexpect.EOF:
        return {
            'status': 'ERROR',
            'error_type': 'remote_ssh',
            'exit_code': None,
            'duration_ms': round((time.monotonic() - started) * 1000, 2),
            'stdout': '',
            'stderr': '远端 SSH 会话在执行命令前意外关闭。',
        }
    finally:
        child.close(force=True)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 19001), DeviceCliRunnerHandler).serve_forever()