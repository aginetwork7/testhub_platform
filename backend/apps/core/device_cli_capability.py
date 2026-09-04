"""Core-owned, read-only device CLI capability for global environments."""

from __future__ import annotations

import os
import re
import shlex
import time
from datetime import datetime, timezone
from string import Formatter
from typing import Any
from urllib.parse import urljoin

import requests
from argon2.low_level import Type, hash_secret_raw
from django.conf import settings
from django.core.cache import cache


class DeviceCliCapabilityError(ValueError):
    """Raised when a device CLI request exceeds the allowed capability."""


class DeviceCliCapability:
    """Execute approved commands only against explicitly SSH-enabled devices."""

    _maximum_command_length = 4096
    _read_only_command_pattern = re.compile(
        r'^\s*(?:systemctl\s+is-active|ps(?:\s|$)|pgrep(?:\s|$)|cat\s+|grep\s+|test\s+|df(?:\s|$)|free(?:\s|$)|uptime\s*$|ip\s+(?:addr|route|link)\b|ss(?:\s|$)|journalctl(?:\s|$)|hostname(?:\s|$)|uname(?:\s|$))'
    )
    _command_blacklist = [
        r'(^|\s)(sudo\s+)?rm\s+',
        r'(^|\s)(sudo\s+)?(mkfs(\.|\s|$)|wipefs(\s|$)|fdisk(\s|$)|parted(\s|$))',
        r'(^|\s)(sudo\s+)?dd\s+.*\bof=/dev/',
        r'(^|\s)(sudo\s)?(reboot|poweroff|shutdown|halt)(\s|$)',
        r'(^|\s)(sudo\s)?(iptables|nft|ufw|firewall-cmd)(\s|$)',
        r'(^|\s)(sudo\s)?(useradd|userdel|usermod|passwd)(\s|$)',
        r'(^|/)authorized_keys(\s|$)|(^|/)sshd_config(\s|$)',
    ]

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def execute(
        self,
        environment_configuration: Any,
        device_id: str,
        operation: str | None = None,
        arguments: dict[str, Any] | None = None,
        command: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        settings_payload = self.device_settings(environment_configuration)
        self.validate_device_id(device_id)
        resolved_command = self._resolve_command(settings_payload, operation, arguments or {}, command)
        token = self._get_admin_token(environment_configuration, settings_payload)
        connection_command = self._fetch_connection_command(
            environment_configuration,
            settings_payload,
            token,
            device_id,
        )
        result = self._execute_in_runner(
            connection_command,
            resolved_command,
            timeout_seconds or environment_configuration.timeout_seconds,
        )
        return {
            'skill_id': 'device_cli.execute',
            'device_id': device_id,
            'operation': operation or ('custom_command' if command else 'connection_check'),
            'status': result['status'],
            'exit_code': result.get('exit_code'),
            'duration_ms': result.get('duration_ms'),
            'stdout': result.get('stdout', ''),
            'stderr': result.get('stderr', ''),
        }

    @staticmethod
    def device_settings(environment_configuration: Any) -> dict[str, Any]:
        runtime_settings = getattr(environment_configuration, 'runtime_settings', {})
        settings_payload = runtime_settings.get('device_cli', {}) if isinstance(runtime_settings, dict) else {}
        if not isinstance(settings_payload, dict) or not settings_payload.get('enabled', False):
            raise DeviceCliCapabilityError('Global environment has not enabled device CLI.')
        return settings_payload

    @staticmethod
    def validate_device_id(device_id: str) -> None:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', device_id):
            raise DeviceCliCapabilityError('device_id format is invalid.')

    @classmethod
    def validate_command(cls, command: str) -> None:
        if not command or len(command) > cls._maximum_command_length or '\n' in command or '\x00' in command:
            raise DeviceCliCapabilityError('device command is invalid.')
        if any(re.search(pattern, command, re.IGNORECASE) for pattern in cls._command_blacklist):
            raise DeviceCliCapabilityError('device command is not permitted.')
        if re.search(r'[;&|><`$()]', command) or not cls._read_only_command_pattern.match(command):
            raise DeviceCliCapabilityError('device command must be read-only.')

    @staticmethod
    def validate_connection_response(payload: dict[str, Any]) -> str:
        if payload.get('isOpen') is not True:
            raise DeviceCliCapabilityError('Device remote SSH is not enabled.')
        connection_command = str(payload.get('command') or payload.get('sshCommand') or '').strip()
        if not connection_command:
            raise DeviceCliCapabilityError('Device SSH connection command is missing.')
        return connection_command

    def _resolve_command(
        self,
        device_settings: dict[str, Any],
        operation: str | None,
        arguments: dict[str, Any],
        command: str | None,
    ) -> str:
        if command is not None:
            if operation or arguments:
                raise DeviceCliCapabilityError('Direct commands cannot include operation or arguments.')
            resolved_command = str(command).strip()
        elif operation:
            templates = device_settings.get('command_templates', {})
            template = templates.get(operation) if isinstance(templates, dict) else None
            if not isinstance(template, str) or not template.strip():
                raise DeviceCliCapabilityError('Device operation is not registered.')
            expected_fields = {field for _, field, _, _ in Formatter().parse(template) if field}
            if expected_fields != set(arguments):
                raise DeviceCliCapabilityError('Device operation arguments do not match the command template.')
            resolved_command = template.format_map({key: shlex.quote(str(value)) for key, value in arguments.items()}).strip()
        else:
            resolved_command = str(device_settings.get('default_command', 'true')).strip()
        self.validate_command(resolved_command)
        return resolved_command

    def _get_admin_token(self, configuration: Any, device_settings: dict[str, Any]) -> str:
        cache_key = f'device-cli:admin-token:{configuration.id}'
        cached_token = cache.get(cache_key)
        if isinstance(cached_token, str) and cached_token:
            return cached_token
        profile_name = str(device_settings.get('auth_profile', 'admin')).lower()
        profile = (configuration.auth_profiles or {}).get(profile_name, {})
        if not isinstance(profile, dict):
            raise DeviceCliCapabilityError(f'Environment lacks {profile_name} administrator credentials.')
        email = self._resolve_secret(profile.get('email') or profile.get('username'))
        password = self._resolve_secret(profile.get('password'))
        password_v2 = self._resolve_secret(profile.get('password_v2')) or password
        if not email or not password or not password_v2:
            raise DeviceCliCapabilityError('Administrator credentials are incomplete.')
        payload = {
            str(profile.get('email_field', 'email')): email,
            str(profile.get('password_field', 'password')): self._network_password(email, password, configuration, profile),
            str(profile.get('password_v2_field', 'password_v2')): self._network_password(email, password_v2, configuration, profile),
        }
        try:
            response = self._session.post(
                self._build_url(configuration.base_url, str(profile.get('login_path', '/auth/login'))),
                json=payload,
                timeout=configuration.timeout_seconds,
            )
            response.raise_for_status()
            response_payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise DeviceCliCapabilityError(f'Administrator login failed: {error}') from error
        token = self._nested(response_payload, str(profile.get('token_path', 'token')))
        if not isinstance(token, str) or not token:
            raise DeviceCliCapabilityError('Administrator login response lacks a token.')
        cache.set(cache_key, token, self._token_ttl(response_payload, profile, device_settings))
        return token

    def _fetch_connection_command(self, configuration: Any, device_settings: dict[str, Any], token: str, device_id: str) -> str:
        headers = {
            str(device_settings.get('authorization_header', 'Authorization')):
            f"{device_settings.get('token_prefix', 'Bearer ')}{token}",
        }
        try:
            response = self._session.get(
                self._build_url(configuration.base_url, str(device_settings.get('ssh_command_path', '/remote_ssh/ssh_cmd'))),
                params={str(device_settings.get('device_id_parameter', 'devId')): device_id},
                headers=headers,
                timeout=configuration.timeout_seconds,
            )
            response.raise_for_status()
            response_payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise DeviceCliCapabilityError(f'Unable to obtain device SSH connection command: {error}') from error
        connection_command = self.validate_connection_response(response_payload)
        if not connection_command.startswith('expect -c ') or '\n' in connection_command or '\x00' in connection_command:
            raise DeviceCliCapabilityError('Device SSH connection command is not a controlled expect session.')
        return connection_command

    def _execute_in_runner(self, connection_command: str, remote_command: str, timeout_seconds: int) -> dict[str, Any]:
        runner_url = str(getattr(settings, 'DEVICE_CLI_RUNNER_URL', '')).rstrip('/')
        if not runner_url:
            raise DeviceCliCapabilityError('DEVICE_CLI_RUNNER_URL is not configured.')
        timeout = max(1, min(int(timeout_seconds), 300))
        headers = {'Content-Type': 'application/json'}
        runner_token = str(getattr(settings, 'DEVICE_CLI_RUNNER_TOKEN', ''))
        if runner_token:
            headers['Authorization'] = f'Bearer {runner_token}'
        try:
            response = self._session.post(f'{runner_url}/v1/device-cli/runs', json={
                'connection_command': connection_command,
                'remote_command': remote_command,
                'timeout_seconds': timeout,
            }, headers=headers, timeout=timeout + 10)
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            raise DeviceCliCapabilityError(f'Device Runner execution failed: {error}') from error
        if not isinstance(result, dict) or result.get('status') not in {'PASSED', 'FAILED', 'ERROR'}:
            raise DeviceCliCapabilityError('Device Runner returned an invalid result.')
        return result

    @staticmethod
    def _build_url(base_url: str, path: str) -> str:
        return path if path.startswith(('http://', 'https://')) else urljoin(f'{base_url.rstrip("/")}/', path.lstrip('/'))

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
        return str(os.getenv(match.group(1), '')).strip() if match else normalized

    @classmethod
    def _network_password(cls, username: str, password: str, configuration: Any, profile: dict[str, Any]) -> str:
        if profile.get('password_mode', 'argon2_network') == 'plain':
            return password
        security = ((configuration.runtime_settings or {}).get('security', {}) or {}).get('password', {}) or {}
        fixed_salt = security.get('fixed_salt') or (configuration.variables or {}).get('SALT')
        if not fixed_salt:
            raise DeviceCliCapabilityError('Credential configuration lacks SALT.')
        argon = security.get('argon2', {}) or {}
        first = argon.get('first_stage', {}) or {}
        second = argon.get('second_stage', {}) or {}
        password_salt = hash_secret_raw(secret=username.encode('ascii'), salt=str(fixed_salt).encode('ascii'), time_cost=first.get('time_cost', 1), memory_cost=first.get('memory_cost', 46) * 1024, parallelism=first.get('parallelism', 1), hash_len=first.get('hash_len', 16), type=Type.ID, version=19).hex()
        return hash_secret_raw(secret=password.encode('ascii'), salt=password_salt.encode('ascii'), time_cost=second.get('time_cost', 1), memory_cost=second.get('memory_cost', 46) * 1024, parallelism=second.get('parallelism', 1), hash_len=second.get('hash_len', 32), type=Type.ID, version=19).hex()

    @classmethod
    def _token_ttl(cls, payload: dict[str, Any], profile: dict[str, Any], device_settings: dict[str, Any]) -> int:
        default_ttl = int(device_settings.get('token_cache_seconds', 600))
        expired_at = cls._nested(payload, str(profile.get('expired_at_path', 'expiredAt')))
        if isinstance(expired_at, (int, float)):
            timestamp = float(expired_at) / 1000 if expired_at > 10_000_000_000 else float(expired_at)
            return max(1, min(default_ttl, int(timestamp - time.time() - 120)))
        if isinstance(expired_at, str):
            try:
                return max(1, min(default_ttl, int((datetime.fromisoformat(expired_at.replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds() - 120)))
            except ValueError:
                return default_ttl
        return default_ttl