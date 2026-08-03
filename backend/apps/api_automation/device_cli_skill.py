from __future__ import annotations

import re
import shlex
import time
import os
from datetime import datetime, timezone
from string import Formatter
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.core.cache import cache

from .models import ApiAutomationConfiguration


class DeviceCliSkillError(ValueError):
    """Raised when a device CLI skill request cannot be executed safely."""


class DeviceCliSkill:
    skill_id = 'device_cli.execute'
    _maximum_command_length = 4096
    default_command_blacklist = [
        r'(^|\s)(sudo\s+)?rm\s+(-[A-Za-z]*r[A-Za-z]*f?|--recursive)(\s|$)',
        r'(^|\s)(sudo\s+)?(mkfs(\.|\s|$)|wipefs(\s|$)|fdisk(\s|$)|parted(\s|$))',
        r'(^|\s)(sudo\s+)?dd\s+.*\bof=/dev/',
        r'(^|\s)(sudo\s+)?(reboot|poweroff|shutdown|halt|init\s+[06])(\s|$)',
        r'(^|\s)(sudo\s+)?(passwd|useradd|userdel|usermod|chpasswd|visudo)(\s|$)',
        r'(^|\s)(sudo\s+)?(iptables|nft|ufw|firewall-cmd)(\s|$)',
        r'(^|\s)(sudo\s+)?(chmod\s+(-R\s+)?777|chown\s+-R\s+/)(\s|$)',
        r'(^|\s)(curl|wget)\s+.*\|\s*(ba)?sh(\s|$)',
        r'(^|/)authorized_keys(\s|$)|(^|/)sshd_config(\s|$)',
    ]

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def execute(
        self,
        configuration: ApiAutomationConfiguration,
        device_id: str,
        operation: str | None = None,
        arguments: dict[str, Any] | None = None,
        command: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        device_settings = self._device_settings(configuration)
        self._validate_device_id(device_id)
        arguments = arguments or {}
        remote_command = self._resolve_remote_command(device_settings, operation, arguments, command)
        token = self._get_admin_token(configuration, device_settings)
        connection_command, startup_deadline = self._fetch_connection_command(
            configuration,
            device_settings,
            token,
            device_id,
        )
        result = self._execute_with_remote_ssh_retry(
            configuration,
            device_settings,
            token,
            device_id,
            connection_command,
            remote_command,
            timeout_seconds or configuration.timeout_seconds,
            startup_deadline,
        )
        return {
            'skill_id': self.skill_id,
            'device_id': device_id,
            'operation': operation or ('custom_command' if command else 'connection_check'),
            'status': result['status'],
            'exit_code': result.get('exit_code'),
            'duration_ms': result.get('duration_ms'),
            'stdout': result.get('stdout', ''),
            'stderr': result.get('stderr', ''),
        }

    def _execute_with_remote_ssh_retry(
        self,
        configuration: ApiAutomationConfiguration,
        device_settings: dict[str, Any],
        token: str,
        device_id: str,
        connection_command: str,
        remote_command: str,
        timeout_seconds: int,
        startup_deadline: float | None,
    ) -> dict[str, Any]:
        attempts = max(1, min(int(device_settings.get('remote_ssh_connection_attempts', 30)), 60))
        interval_seconds = max(0.1, min(float(device_settings.get('remote_ssh_connection_retry_interval_seconds', 2)), 10))
        connection_deadline = startup_deadline or (
            time.monotonic() + max(
                1,
                min(float(device_settings.get('remote_ssh_startup_timeout_seconds', 60)), 60),
            )
        )
        result: dict[str, Any] = {}
        for attempt in range(attempts):
            remaining = connection_deadline - time.monotonic()
            if remaining <= 0:
                return result
            if attempt:
                time.sleep(min(interval_seconds, remaining))
                connection_command, _ = self._fetch_connection_command(
                    configuration,
                    device_settings,
                    token,
                    device_id,
                )
            result = self._execute_in_runner(
                connection_command=connection_command,
                remote_command=remote_command,
                timeout_seconds=max(1, min(timeout_seconds, int(remaining))),
            )
            if result.get('status') != 'ERROR' or result.get('error_type') != 'remote_ssh':
                return result
        return result

    @staticmethod
    def _device_settings(configuration: ApiAutomationConfiguration) -> dict[str, Any]:
        settings_payload = (configuration.runtime_settings or {}).get('device_cli', {})
        if not isinstance(settings_payload, dict) or not settings_payload.get('enabled', False):
            raise DeviceCliSkillError('当前环境未启用 device_cli Skill。')
        return settings_payload

    @staticmethod
    def _validate_device_id(device_id: str) -> None:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', device_id):
            raise DeviceCliSkillError('device_id 格式无效。')

    def _get_admin_token(
        self,
        configuration: ApiAutomationConfiguration,
        device_settings: dict[str, Any],
    ) -> tuple[str, float | None]:
        cache_key = f'device-cli:admin-token:{configuration.id}'
        cached_token = cache.get(cache_key)
        if isinstance(cached_token, str) and cached_token:
            return cached_token

        profile_name = str(device_settings.get('auth_profile', 'admin')).lower()
        profile = (configuration.auth_profiles or {}).get(profile_name, {})
        if not isinstance(profile, dict):
            raise DeviceCliSkillError(f'环境未配置 {profile_name} 管理员认证信息。')

        email = self._resolve_secret(profile.get('email') or profile.get('username'))
        password = self._resolve_secret(profile.get('password'))
        password_v2 = self._resolve_secret(profile.get('password_v2')) or password
        if not email or not password or not password_v2:
            raise DeviceCliSkillError('管理员认证缺少 email、password 或 password_v2。')

        password = self._network_password(email, password, configuration, profile)
        password_v2 = self._network_password(email, password_v2, configuration, profile)

        login_path = str(profile.get('login_path', '/auth/login')).strip()
        login_url = self._build_url(configuration.base_url, login_path)
        payload = {
            str(profile.get('email_field', 'email')): email,
            str(profile.get('password_field', 'password')): password,
            str(profile.get('password_v2_field', 'password_v2')): password_v2,
        }
        try:
            response = self._session.post(login_url, json=payload, timeout=configuration.timeout_seconds)
            response.raise_for_status()
            response_payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise DeviceCliSkillError(f'管理员登录失败：{error}') from error

        token = self._nested(response_payload, str(profile.get('token_path', 'token')))
        if not isinstance(token, str) or not token:
            raise DeviceCliSkillError('管理员登录响应缺少 token。')
        cache.set(cache_key, token, self._token_ttl(response_payload, profile, device_settings))
        return token

    def _fetch_connection_command(
        self,
        configuration: ApiAutomationConfiguration,
        device_settings: dict[str, Any],
        token: str,
        device_id: str,
    ) -> str:
        endpoint = str(device_settings.get('ssh_command_path', '/remote_ssh/ssh_cmd')).strip()
        request_url = self._build_url(configuration.base_url, endpoint)
        header_name = str(device_settings.get('authorization_header', 'Authorization'))
        token_prefix = str(device_settings.get('token_prefix', 'Bearer '))
        headers = {header_name: f'{token_prefix}{token}'}
        try:
            response = self._session.get(
                request_url,
                params={str(device_settings.get('device_id_parameter', 'devId')): device_id},
                headers=headers,
                timeout=configuration.timeout_seconds,
            )
            response.raise_for_status()
            response_payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise DeviceCliSkillError(f'获取设备 SSH 连接命令失败：{error}') from error

        if response_payload.get('isOpen') is False:
            if not device_settings.get('auto_enable_remote_ssh', True):
                raise DeviceCliSkillError(f'设备 {device_id} 未开启 remote SSH，无法获取连接命令。')
            self._enable_remote_ssh(configuration, device_settings, headers, device_id)
            startup_deadline = time.monotonic() + max(
                1,
                min(float(device_settings.get('remote_ssh_startup_timeout_seconds', 60)), 60),
            )
            response_payload = self._wait_for_connection_command(
                request_url,
                device_settings,
                headers,
                device_id,
                configuration.timeout_seconds,
                startup_deadline,
            )
            return self._validate_connection_command(response_payload, device_settings, device_id), startup_deadline
        return self._validate_connection_command(response_payload, device_settings, device_id), None

    def _enable_remote_ssh(
        self,
        configuration: ApiAutomationConfiguration,
        device_settings: dict[str, Any],
        headers: dict[str, str],
        device_id: str,
    ) -> None:
        endpoint = str(
            device_settings.get('remote_ssh_enable_path', '/remote_ssh/config')
        ).strip()
        payload = {
            str(device_settings.get('remote_ssh_enable_id_field', 'devId')): device_id,
            str(device_settings.get('remote_ssh_enable_target_version_field', 'targetVersion')): str(
                device_settings.get('remote_ssh_enable_target_version', '')
            ),
            str(device_settings.get('remote_ssh_enable_flag_field', 'open')): True,
        }
        try:
            response = self._session.post(
                self._build_url(configuration.base_url, endpoint),
                json=payload,
                headers=headers,
                timeout=configuration.timeout_seconds,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            response_body = error.response.json() if error.response is not None else {}
            error_name = str(response_body.get('name', '')).lower() if isinstance(response_body, dict) else ''
            error_message = str(response_body.get('message', '')).lower() if isinstance(response_body, dict) else ''
            if error_name == 'code.related_exist' or 'remote ssh is not released' in error_message:
                return
            raise DeviceCliSkillError(f'开启设备 {device_id} 的 remote SSH 失败：{error}') from error
        except requests.RequestException as error:
            raise DeviceCliSkillError(f'开启设备 {device_id} 的 remote SSH 失败：{error}') from error

    def _wait_for_connection_command(
        self,
        request_url: str,
        device_settings: dict[str, Any],
        headers: dict[str, str],
        device_id: str,
        timeout_seconds: int,
        startup_deadline: float,
    ) -> dict[str, Any]:
        attempts = max(1, min(int(device_settings.get('remote_ssh_poll_attempts', 30)), 60))
        interval_seconds = max(0.1, min(float(device_settings.get('remote_ssh_poll_interval_seconds', 2)), 10))
        parameter = str(device_settings.get('device_id_parameter', 'devId'))
        for attempt in range(attempts):
            if attempt:
                remaining = startup_deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(interval_seconds, remaining))
            try:
                response = self._session.get(
                    request_url,
                    params={parameter: device_id},
                    headers=headers,
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as error:
                raise DeviceCliSkillError(f'轮询设备 {device_id} 的 remote SSH 状态失败：{error}') from error
            command = self._nested(payload, str(device_settings.get('ssh_command_path_in_response', 'cmd')))
            if payload.get('isOpen') is not False and isinstance(command, str) and command.strip():
                return payload
        raise DeviceCliSkillError(f'设备 {device_id} 的 remote SSH 开启后 60 秒内未返回 cmd。')

    def _validate_connection_command(
        self,
        response_payload: dict[str, Any],
        device_settings: dict[str, Any],
        device_id: str,
    ) -> str:
        command = self._nested(response_payload, str(device_settings.get('ssh_command_path_in_response', 'cmd')))
        if not isinstance(command, str) or not command.strip():
            raise DeviceCliSkillError(f'设备 {device_id} 的 remote SSH 响应未提供可用 cmd。')
        normalized_command = command.strip()
        if (
            len(normalized_command) > self._maximum_command_length
            or '\n' in normalized_command
            or '\x00' in normalized_command
            or not normalized_command.startswith('expect -c ')
        ):
            raise DeviceCliSkillError('远端返回的 SSH 命令不符合受控 expect 会话格式。')
        return normalized_command

    def _render_operation(
        self,
        device_settings: dict[str, Any],
        operation: str,
        arguments: dict[str, Any],
    ) -> str:
        templates = device_settings.get('command_templates', {})
        if not isinstance(templates, dict):
            raise DeviceCliSkillError('device_cli.command_templates 必须是对象。')
        template = templates.get(operation)
        if not isinstance(template, str) or not template.strip():
            raise DeviceCliSkillError(f'未注册或未启用设备操作：{operation}')

        expected_fields = {
            field_name
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name
        }
        if expected_fields != set(arguments):
            raise DeviceCliSkillError('操作参数与已注册命令模板不匹配。')
        safe_arguments: dict[str, str] = {}
        for key, value in arguments.items():
            if not isinstance(value, (str, int, float)) or '\n' in str(value) or '\x00' in str(value):
                raise DeviceCliSkillError(f'操作参数 {key} 无效。')
            safe_arguments[key] = shlex.quote(str(value))

        command = template.format_map(safe_arguments).strip()
        if not command or len(command) > self._maximum_command_length:
            raise DeviceCliSkillError('渲染后的设备命令无效。')
        return command

    def _resolve_remote_command(
        self,
        device_settings: dict[str, Any],
        operation: str | None,
        arguments: dict[str, Any],
        command: str | None,
    ) -> str:
        if command is not None:
            if operation or arguments:
                raise DeviceCliSkillError('直接命令不能同时指定 operation 或 arguments。')
            normalized_command = str(command).strip()
        else:
            normalized_command = (
                self._render_operation(device_settings, operation, arguments)
                if operation
                else str(device_settings.get('default_command', 'true')).strip()
            )

        if not normalized_command or len(normalized_command) > self._maximum_command_length:
            raise DeviceCliSkillError('设备命令无效。')
        if '\n' in normalized_command or '\x00' in normalized_command:
            raise DeviceCliSkillError('设备命令不能包含换行符或 NUL 字节。')
        self._ensure_command_allowed(device_settings, normalized_command)
        return normalized_command

    @staticmethod
    def _ensure_command_allowed(device_settings: dict[str, Any], command: str) -> None:
        blacklist = device_settings.get('command_blacklist', DeviceCliSkill.default_command_blacklist)
        if not isinstance(blacklist, list) or not all(isinstance(item, str) for item in blacklist):
            raise DeviceCliSkillError('device_cli.command_blacklist 必须是字符串数组。')
        for pattern in blacklist:
            try:
                if re.search(pattern, command, flags=re.IGNORECASE):
                    raise DeviceCliSkillError('该设备命令命中当前环境的命令黑名单。')
            except re.error as error:
                raise DeviceCliSkillError(f'设备命令黑名单正则无效：{error}') from error

    def _execute_in_runner(
        self,
        connection_command: str,
        remote_command: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        runner_url = str(getattr(settings, 'DEVICE_CLI_RUNNER_URL', '')).rstrip('/')
        if not runner_url:
            raise DeviceCliSkillError('未配置 DEVICE_CLI_RUNNER_URL。')
        runner_token = str(getattr(settings, 'DEVICE_CLI_RUNNER_TOKEN', ''))
        headers = {'Content-Type': 'application/json'}
        if runner_token:
            headers['Authorization'] = f'Bearer {runner_token}'
        timeout = max(1, min(int(timeout_seconds), 300))
        try:
            response = self._session.post(
                f'{runner_url}/v1/device-cli/runs',
                json={
                    'connection_command': connection_command,
                    'remote_command': remote_command,
                    'timeout_seconds': timeout,
                },
                headers=headers,
                timeout=timeout + 10,
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            raise DeviceCliSkillError(f'Device Runner 执行失败：{error}') from error
        if not isinstance(result, dict) or result.get('status') not in {'PASSED', 'FAILED', 'ERROR'}:
            raise DeviceCliSkillError('Device Runner 返回了无效结果。')
        return result

    @staticmethod
    def _build_url(base_url: str, path: str) -> str:
        if path.startswith(('http://', 'https://')):
            return path
        return urljoin(f'{base_url.rstrip("/")}/', path.lstrip('/'))

    @staticmethod
    def _nested(payload: Any, path: str) -> Any:
        current = payload
        for part in path.split('.'):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @staticmethod
    def _resolve_secret(value: Any) -> str:
        normalized = str(value or '').strip()
        match = re.fullmatch(r'\$\{([A-Z][A-Z0-9_]*)\}', normalized)
        if match:
            return str(os.getenv(match.group(1), '')).strip()
        return normalized

    @staticmethod
    def _network_password(
        username: str,
        password: str,
        configuration: ApiAutomationConfiguration,
        profile: dict[str, Any],
    ) -> str:
        if profile.get('password_mode', 'argon2_network') == 'plain':
            return password
        security = ((configuration.runtime_settings or {}).get('security', {}) or {}).get('password', {}) or {}
        fixed_salt = security.get('fixed_salt') or (configuration.variables or {}).get('SALT')
        if not fixed_salt:
            raise DeviceCliSkillError('认证配置缺少 SALT，无法执行 Argon2 密码转换。')

        from argon2.low_level import Type, hash_secret_raw

        argon = security.get('argon2', {}) or {}
        first = argon.get('first_stage', {}) or {}
        second = argon.get('second_stage', {}) or {}
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

    @staticmethod
    def _token_ttl(payload: dict[str, Any], profile: dict[str, Any], device_settings: dict[str, Any]) -> int:
        default_ttl = int(device_settings.get('token_cache_seconds', 600))
        expired_at = DeviceCliSkill._nested(payload, str(profile.get('expired_at_path', 'expiredAt')))
        if isinstance(expired_at, (int, float)):
            timestamp = float(expired_at)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            return max(1, min(default_ttl, int(timestamp - time.time() - 120)))
        if isinstance(expired_at, str):
            try:
                expires_at = datetime.fromisoformat(expired_at.replace('Z', '+00:00'))
                return max(1, min(default_ttl, int((expires_at - datetime.now(timezone.utc)).total_seconds() - 120)))
            except ValueError:
                return default_ttl
        return default_ttl