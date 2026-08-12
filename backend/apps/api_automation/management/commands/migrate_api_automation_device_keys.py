from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from dotenv import dotenv_values

from apps.api_automation.models import ApiAutomationConfiguration, ApiAutomationProject


class Command(BaseCommand):
    help = '将历史 .env.* 中的事件设备私钥迁入页面环境配置。'

    def add_arguments(self, parser: Any) -> None:
        asset_root = Path(__file__).resolve().parents[2] / 'test_assets' / 'config' / 'environments'
        parser.add_argument('--project', required=True, type=int, help='API 自动化项目 ID。')
        parser.add_argument('--env-dir', default=str(asset_root), help='历史 .env.* 文件目录。')
        parser.add_argument('--overwrite', action='store_true', help='覆盖页面已配置的设备私钥。')
        parser.add_argument('--dry-run', action='store_true', help='仅显示待迁移环境，不写入数据库。')

    def handle(self, *args: Any, **options: Any) -> None:
        if not ApiAutomationProject.objects.filter(id=options['project']).exists():
            raise CommandError(f'项目不存在: {options["project"]}')
        env_directory = Path(options['env_dir']).expanduser().resolve()
        migrated_count = 0
        skipped_count = 0
        for configuration in ApiAutomationConfiguration.objects.filter(project_id=options['project']).order_by('id'):
            values = dotenv_values(env_directory / f'.env.{configuration.environment}')
            source_keys = {
                'main': values.get('MAIN_KEY') or '',
                'backup': values.get('BACKUP_KEY') or '',
            }
            targets = {
                device: key
                for device, key in source_keys.items()
                if key and (options['overwrite'] or not configuration.get_event_device_key(device))
            }
            if not targets:
                skipped_count += 1
                continue
            self.stdout.write(f'迁移环境设备私钥: {configuration.name}')
            if options['dry_run']:
                continue
            configuration.set_event_device_keys(
                main_device_key=targets.get('main'),
                backup_device_key=targets.get('backup'),
            )
            configuration.save(update_fields=['event_device_keys_encrypted'])
            migrated_count += 1
        self.stdout.write(self.style.SUCCESS(f'已迁移 {migrated_count} 个环境，跳过 {skipped_count} 个环境。'))