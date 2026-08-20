from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from dotenv import dotenv_values

from apps.api_automation.models import ApiAutomationConfiguration


class Command(BaseCommand):
    help = '从 TestHub 原生 API 自动化 config.yaml 与 .env.* 文件同步所有运行环境配置。'

    def add_arguments(self, parser: Any) -> None:
        asset_root = Path(__file__).resolve().parents[2] / 'test_assets' / 'config'
        parser.add_argument('--config', default=str(asset_root / 'config.yaml'), help='多环境 YAML 配置文件。')
        parser.add_argument('--env-dir', default=str(asset_root / 'environments'), help='.env.* 文件目录。')
        parser.add_argument('--owner', help='配置创建人用户名或邮箱。')
        parser.add_argument('--dry-run', action='store_true', help='仅输出待同步环境，不写入数据库。')

    def handle(self, *args: Any, **options: Any) -> None:
        config_path = Path(options['config']).expanduser().resolve()
        env_directory = Path(options['env_dir']).expanduser().resolve()
        try:
            configuration = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
        except (OSError, yaml.YAMLError) as error:
            raise CommandError(f'读取多环境配置失败: {error}') from error
        default_settings = configuration.get('default', {})
        environments = {
            name: self._deep_merge(default_settings, value)
            for name, value in configuration.items()
            if name != 'default' and isinstance(value, dict)
        }
        if not environments:
            raise CommandError('配置中没有可同步的环境。')
        owner = self._resolve_owner(options['owner'])
        self.stdout.write(f'发现环境: {", ".join(environments)}')
        if options['dry_run']:
            return
        for environment, settings in environments.items():
            env_values = self._load_env_values(env_directory, environment)
            runtime_settings = settings.copy()
            default_role = settings.get('api', {}).get('roles', {}).get('default_role', 'dealer').lower()
            variables = {key: value for key, value in env_values.items() if value is not None}
            variables.update({
                'data_endpoints': variables.get('DATA_ENDPOINTS', {}),
                'model_images': variables.get('MODEL_IMAGES', {}),
            })
            variables.pop('default_role', None)
            excluded_roles = {'dealerdingkang', 'customerdingkang'} if environment == 'test-2' else set()
            auth_profiles = self._auth_profiles(settings, env_values, default_role, excluded_roles)
            payment_config = self._payment_config(settings)
            model_profiles = settings.get('models', {})
            defaults = {
                'name': f'{environment} 环境',
                'base_url': settings.get('api', {}).get('base_url', ''),
                'websocket_url': settings.get('websocket', {}).get('url', ''),
                'variables': variables,
                'auth_profiles': auth_profiles,
                'payment_config': payment_config,
                'model_profiles': model_profiles,
                'runtime_settings': runtime_settings,
                'timeout_seconds': settings.get('api', {}).get('timeout', 30),
                'max_workers': settings.get('test', {}).get('max_workers', 1) or 1,
                'is_default': environment == settings.get('env'),
                'created_by': owner,
            }
            config_instance = ApiAutomationConfiguration.objects.filter(environment=environment).order_by('id').first()
            created = config_instance is None
            if config_instance is None:
                config_instance = ApiAutomationConfiguration.objects.create(environment=environment, **defaults)
            else:
                for field, value in defaults.items():
                    setattr(config_instance, field, value)
                config_instance.save()
            self._migrate_device_keys(config_instance, env_values)
            self.stdout.write(f"{'创建' if created else '更新'}环境: {config_instance.environment}")
        default_environment = next((name for name, value in environments.items() if value.get('env') == name), None)
        if default_environment:
            ApiAutomationConfiguration.objects.exclude(environment=default_environment).update(is_default=False)

    def _load_env_values(self, env_directory: Path, environment: str) -> dict[str, str | None]:
        env_path = env_directory / f'.env.{environment}'
        return dict(dotenv_values(env_path)) if env_path.is_file() else {}

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = base.copy()
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _auth_profiles(
        self,
        settings: dict[str, Any],
        env_values: dict[str, str | None],
        default_role: str,
        excluded_roles: set[str],
    ) -> dict[str, Any]:
        auth_config = settings.get('auth', {})
        api_auth = settings.get('api', {}).get('auth', {})
        environment_mapping = {
            'admin': ('ADMIN_NAME', 'ADMIN_PASSWORD'),
            'distributors': ('DISTRIBUTORS_NAME', 'DISTRIBUTORS_PASSWORD'),
            'dealer': ('DEALER_NAME', 'DEALER_PASSWORD'),
            'customer': ('CUSTOMER_NAME', 'CUSTOMER_PASSWORD'),
            'dealer_admin': ('DEALER_ADMIN_NAME', 'DEALER_ADMIN_PASSWORD'),
            'dealer_rep': ('DEALER_REP_NAME', 'DEALER_REP_PASSWORD'),
            'technician': ('TECHNICIAN_NAME', 'TECHNICIAN_PASSWORD'),
            'scheduler': ('SCHEDULER_NAME', 'SCHEDULER_PASSWORD'),
            'dispatcher': ('DISPATCHER_NAME', 'DISPATCHER_PASSWORD'),
            'inspector': ('INSPECTOR_NAME', 'INSPECTOR_PASSWORD'),
            'operator': ('OPERATOR_NAME', 'OPERATOR_PASSWORD'),
            'org_admin': ('ORG_ADMIN_NAME', 'ORG_ADMIN_PASSWORD'),
            'site_manager': ('SITE_MANAGER_NAME', 'SITE_MANAGER_PASSWORD'),
            'dealerdingkang': ('DEALERDINGKANG_NAME', 'DEALERDINGKANG_PASSWORD'),
            'customerdingkang': ('CUSTOMERDINGKANG_NAME', 'CUSTOMERDINGKANG_PASSWORD'),
        }
        profiles: dict[str, Any] = {}
        for name, user in auth_config.get('users', {}).items():
            if not isinstance(user, dict):
                continue
            if name.lower() in excluded_roles:
                continue
            username_key, password_key = environment_mapping.get(name.lower(), ('', ''))
            profiles[name.lower()] = {
                'username': env_values.get(username_key) or user.get('username', ''),
                'password': env_values.get(password_key) or user.get('password', ''),
                'role': user.get('role', name.upper()),
                'login_path': api_auth.get('token_path', '/auth/login'),
                'password_mode': 'argon2_network',
                'token_path': api_auth.get('token_key', 'token'),
                'authorization_header': api_auth.get('header_name', 'Authorization'),
                'token_prefix': api_auth.get('header_prefix', 'Bearer '),
                'apply_token_prefix': False,
                'organization_path': 'user.organization.id',
                'is_default_role': name.lower() == default_role,
            }
        return profiles

    def _payment_config(self, settings: dict[str, Any]) -> dict[str, Any]:
        stripe = settings.get('security', {}).get('stripe', {})
        return {
            'mock_base_url': stripe.get('api_url', ''),
            'headers': {'X-Admin-Token': stripe.get('api_token', '')},
            'stripe_api_key': stripe.get('api_key', ''),
            'webhook_mode': 'stripe_cli',
        }

    def _migrate_device_keys(
        self,
        configuration: ApiAutomationConfiguration,
        env_values: dict[str, str | None],
    ) -> None:
        main_device_key = env_values.get('MAIN_KEY') or ''
        backup_device_key = env_values.get('BACKUP_KEY') or ''
        if not main_device_key and not backup_device_key:
            return
        configuration.set_event_device_keys(
            main_device_key=main_device_key if main_device_key and not configuration.get_event_device_key('main') else None,
            backup_device_key=backup_device_key if backup_device_key and not configuration.get_event_device_key('backup') else None,
        )
        configuration.save(update_fields=['event_device_keys_encrypted'])

    def _resolve_owner(self, owner_identifier: str | None):
        if not owner_identifier:
            return None
        user_model = get_user_model()
        owner = user_model.objects.filter(username=owner_identifier).first() or user_model.objects.filter(email=owner_identifier).first()
        if owner is None:
            raise CommandError(f'未找到用户: {owner_identifier}')
        return owner