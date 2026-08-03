from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from apps.api_automation.device_cli_skill import DeviceCliSkill, DeviceCliSkillError


class ResponseStub:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class SessionStub:
    def __init__(self) -> None:
        self.post_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def post(self, url: str, **kwargs):
        self.post_calls.append({'url': url, **kwargs})
        if url.endswith('/auth/login'):
            return ResponseStub({'token': 'admin-token', 'expiredAt': time.time() + 900})
        return ResponseStub({
            'status': 'PASSED',
            'exit_code': 0,
            'duration_ms': 12.5,
            'stdout': 'active\n',
            'stderr': '',
        })

    def get(self, url: str, **kwargs):
        self.get_calls.append({'url': url, **kwargs})
        return ResponseStub({
            'cmd': "expect -c 'spawn ssh device@example.test; interact'",
        })


class DeviceCliSkillTests(SimpleTestCase):
    def setUp(self) -> None:
        self.configuration = SimpleNamespace(
            id=17,
            base_url='https://test-api.example/agi7/api',
            timeout_seconds=30,
            auth_profiles={
                'admin': {
                    'email': 'admin@example.test',
                    'password': 'password',
                    'password_v2': 'password',
                    'login_path': '/auth/login',
                    'password_mode': 'plain',
                },
            },
            runtime_settings={
                'device_cli': {
                    'enabled': True,
                    'command_templates': {
                        'service_status': 'systemctl is-active {service}',
                    },
                },
            },
        )

    def test_execute_uses_cached_token_and_registered_command_template(self) -> None:
        session = SessionStub()
        skill = DeviceCliSkill(session=session)

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value='cached-token'), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ), override_settings(
            DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001',
            DEVICE_CLI_RUNNER_TOKEN='runner-token',
        ):
            result = skill.execute(
                self.configuration,
                device_id='ainvr_5000',
                operation='service_status',
                arguments={'service': 'camera-agent'},
            )

        self.assertEqual(result['status'], 'PASSED')
        self.assertEqual(session.get_calls[0]['headers']['Authorization'], 'Bearer cached-token')
        self.assertEqual(session.post_calls[0]['json']['remote_command'], 'systemctl is-active camera-agent')
        self.assertEqual(session.post_calls[0]['headers']['Authorization'], 'Bearer runner-token')

    def test_execute_logs_in_and_caches_token_on_cache_miss(self) -> None:
        session = SessionStub()
        skill = DeviceCliSkill(session=session)

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value=None), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ) as cache_set, override_settings(DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001'):
            skill.execute(
                self.configuration,
                device_id='ainvr_5000',
                operation='service_status',
                arguments={'service': 'camera-agent'},
            )

        self.assertEqual(session.post_calls[0]['url'], 'https://test-api.example/agi7/api/auth/login')
        self.assertEqual(session.post_calls[0]['json']['password_v2'], 'password')
        self.assertEqual(session.get_calls[0]['headers']['Authorization'], 'Bearer admin-token')
        cache_set.assert_called_once()

    def test_unregistered_operation_is_rejected(self) -> None:
        skill = DeviceCliSkill(session=SessionStub())

        with self.assertRaisesRegex(DeviceCliSkillError, '未注册'):
            skill.execute(
                self.configuration,
                device_id='ainvr_5000',
                operation='arbitrary_shell',
                arguments={},
            )

    def test_direct_command_is_allowed_when_not_blacklisted(self) -> None:
        session = SessionStub()
        skill = DeviceCliSkill(session=session)

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value='cached-token'), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ), override_settings(DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001'):
            result = skill.execute(
                self.configuration,
                device_id='ainvr_5000',
                command='journalctl -u camera-agent -n 20 --no-pager',
                arguments={},
            )

        self.assertEqual(result['operation'], 'custom_command')
        self.assertEqual(session.post_calls[0]['json']['remote_command'], 'journalctl -u camera-agent -n 20 --no-pager')

    def test_device_id_only_runs_fixed_connection_validation(self) -> None:
        session = SessionStub()
        skill = DeviceCliSkill(session=session)

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value='cached-token'), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ), override_settings(DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001'):
            result = skill.execute(self.configuration, device_id='ainvr_5000')

        self.assertEqual(result['operation'], 'connection_check')
        self.assertEqual(session.post_calls[0]['json']['remote_command'], 'true')

    def test_default_blacklist_rejects_reboot_command(self) -> None:
        skill = DeviceCliSkill(session=SessionStub())

        with self.assertRaisesRegex(DeviceCliSkillError, '黑名单'):
            skill.execute(
                self.configuration,
                device_id='ainvr_5000',
                command='reboot now',
            )

    def test_blacklisted_direct_command_is_rejected(self) -> None:
        skill = DeviceCliSkill(session=SessionStub())
        self.configuration.runtime_settings['device_cli']['command_blacklist'] = [r'(^|\s)reboot(\s|$)']

        with self.assertRaisesRegex(DeviceCliSkillError, '黑名单'):
            skill.execute(
                self.configuration,
                device_id='ainvr_5000',
                command='reboot now',
                arguments={},
            )

    def test_closed_remote_ssh_returns_actionable_error(self) -> None:
        session = SessionStub()
        session.get = lambda *_args, **_kwargs: ResponseStub({'isOpen': False, 'cmd': ''})
        skill = DeviceCliSkill(session=session)
        self.configuration.runtime_settings['device_cli']['auto_enable_remote_ssh'] = False

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value='cached-token'), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ), override_settings(DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001'), self.assertRaisesRegex(
            DeviceCliSkillError,
            '未开启 remote SSH',
        ):
            skill.execute(self.configuration, device_id='nvr_5003')

    def test_closed_remote_ssh_is_enabled_and_retried(self) -> None:
        session = SessionStub()
        responses = [
            ResponseStub({'isOpen': False, 'cmd': ''}),
            ResponseStub({'isOpen': True, 'cmd': "expect -c 'spawn ssh device@example.test; interact'"}),
        ]
        session.get = lambda *_args, **_kwargs: responses.pop(0)
        skill = DeviceCliSkill(session=session)

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value='cached-token'), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ), patch('apps.api_automation.device_cli_skill.time.sleep'), override_settings(
            DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001'
        ):
            result = skill.execute(self.configuration, device_id='nvr_5003')

        self.assertEqual(result['status'], 'PASSED')
        enable_call = next(call for call in session.post_calls if call['url'].endswith('/remote_ssh/config'))
        self.assertEqual(enable_call['json'], {'devId': 'nvr_5003', 'targetVersion': '', 'open': True})

    def test_remote_ssh_runner_error_retries_connection(self) -> None:
        session = SessionStub()
        session.get = lambda *_args, **_kwargs: ResponseStub({'isOpen': True, 'cmd': "expect -c 'spawn ssh device@example.test; interact'"})
        runner_results = [
            ResponseStub({'status': 'ERROR', 'error_type': 'remote_ssh', 'stderr': 'not ready'}),
            ResponseStub({'status': 'PASSED', 'exit_code': 0, 'duration_ms': 1, 'stdout': '', 'stderr': ''}),
        ]
        session.post = lambda url, **kwargs: runner_results.pop(0) if url.endswith('/v1/device-cli/runs') else ResponseStub({'token': 'admin-token'})
        skill = DeviceCliSkill(session=session)

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value='cached-token'), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ), patch('apps.api_automation.device_cli_skill.time.sleep'), override_settings(
            DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001'
        ):
            result = skill.execute(self.configuration, device_id='nvr_5003')

        self.assertEqual(result['status'], 'PASSED')

    def test_existing_remote_ssh_session_continues_to_poll_cmd(self) -> None:
        session = SessionStub()
        related_response = type('RelatedResponse', (), {
            'json': lambda _self: {'name': 'code.related_exist', 'message': 'Remote Ssh Is Not Released For Dev_id Nvr_5003'},
        })()
        related_error = requests.HTTPError(response=related_response)
        session.post = lambda url, **_kwargs: (_ for _ in ()).throw(related_error) if url.endswith('/remote_ssh/config') else ResponseStub({
            'status': 'PASSED', 'exit_code': 0, 'duration_ms': 1, 'stdout': '', 'stderr': '',
        })
        responses = [
            ResponseStub({'isOpen': False, 'cmd': ''}),
            ResponseStub({'isOpen': True, 'cmd': "expect -c 'spawn ssh device@example.test; interact'"}),
        ]
        session.get = lambda *_args, **_kwargs: responses.pop(0)
        skill = DeviceCliSkill(session=session)

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value='cached-token'), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ), patch('apps.api_automation.device_cli_skill.time.sleep'), override_settings(
            DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001'
        ):
            result = skill.execute(self.configuration, device_id='nvr_5003')

        self.assertEqual(result['status'], 'PASSED')

    @patch.dict('os.environ', {'DEVICE_ADMIN_EMAIL': 'admin@example.test', 'DEVICE_ADMIN_PASSWORD': 'password'})
    def test_login_resolves_complete_environment_variable_references(self) -> None:
        session = SessionStub()
        skill = DeviceCliSkill(session=session)
        self.configuration.auth_profiles['admin'].update({
            'email': '${DEVICE_ADMIN_EMAIL}',
            'password': '${DEVICE_ADMIN_PASSWORD}',
            'password_v2': '${DEVICE_ADMIN_PASSWORD}',
            'password_mode': 'plain',
        })

        with patch('apps.api_automation.device_cli_skill.cache.get', return_value=None), patch(
            'apps.api_automation.device_cli_skill.cache.set'
        ), override_settings(DEVICE_CLI_RUNNER_URL='http://device-cli-runner:19001'):
            skill.execute(
                self.configuration,
                device_id='ainvr_5000',
                operation='service_status',
                arguments={'service': 'camera-agent'},
            )

        self.assertEqual(session.post_calls[0]['json']['email'], 'admin@example.test')
        self.assertEqual(session.post_calls[0]['json']['password_v2'], 'password')

    def test_network_password_uses_environment_argon2_configuration(self) -> None:
        self.configuration.auth_profiles['admin']['password_mode'] = 'argon2_network'
        self.configuration.runtime_settings['security'] = {
            'password': {
                'fixed_salt': 'fixed-test-salt',
                'argon2': {
                    'first_stage': {'time_cost': 1, 'memory_cost': 8, 'parallelism': 1, 'hash_len': 16},
                    'second_stage': {'time_cost': 1, 'memory_cost': 8, 'parallelism': 1, 'hash_len': 32},
                },
            },
        }

        encoded = DeviceCliSkill._network_password(
            'admin@example.test',
            'password',
            self.configuration,
            self.configuration.auth_profiles['admin'],
        )

        self.assertNotEqual(encoded, 'password')
        self.assertEqual(len(encoded), 64)