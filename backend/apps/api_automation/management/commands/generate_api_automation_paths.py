from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '根据 TestHub API 自动化测试资产中的 OpenAPI/Swagger 文件生成接口别名表。'

    def add_arguments(self, parser: Any) -> None:
        asset_root = Path(__file__).resolve().parents[2] / 'test_assets'
        parser.add_argument(
            '--spec',
            default=str(asset_root / 'config' / 'schemas' / 'swagger.json'),
            help='OpenAPI/Swagger JSON 或 YAML 文件路径。',
        )
        parser.add_argument(
            '--output',
            default=str(asset_root / 'config' / 'api_paths.json'),
            help='生成的接口别名 JSON 文件路径。',
        )
        parser.add_argument('--check', action='store_true', help='仅检查生成结果是否与当前别名表一致。')

    def handle(self, *args: Any, **options: Any) -> None:
        specification_path = Path(options['spec']).expanduser().resolve()
        output_path = Path(options['output']).expanduser().resolve()
        specification = self._load_specification(specification_path)
        aliases = self._generate_aliases(specification)
        current_aliases = self._load_existing_aliases(output_path)

        if options['check']:
            if aliases == current_aliases:
                self.stdout.write(self.style.SUCCESS(f'接口别名表已是最新状态: {output_path}'))
                return
            raise CommandError(
                f'接口别名表需要更新: {output_path}。运行不带 --check 的命令生成最新文件。'
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(aliases, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        self.stdout.write(self.style.SUCCESS(f'已生成 {len(aliases)} 条接口别名: {output_path}'))
        self.stdout.write('请运行 python manage.py import_pyapitest_cases 同步数据库接口目录和用例元数据。')

    def _load_specification(self, specification_path: Path) -> dict[str, Any]:
        if not specification_path.is_file():
            raise CommandError(f'OpenAPI/Swagger 文件不存在: {specification_path}')
        try:
            content = specification_path.read_text(encoding='utf-8')
            specification = yaml.safe_load(content) if specification_path.suffix in {'.yaml', '.yml'} else json.loads(content)
        except (json.JSONDecodeError, yaml.YAMLError) as error:
            raise CommandError(f'OpenAPI/Swagger 文件格式无效: {error}') from error
        if not isinstance(specification, dict) or not isinstance(specification.get('paths'), dict):
            raise CommandError('OpenAPI/Swagger 文件缺少 paths 对象。')
        return specification

    def _generate_aliases(self, specification: dict[str, Any]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for path in sorted(specification['paths']):
            alias = '_'.join(segment.strip('{}') for segment in path.split('/') if segment)
            if not alias:
                continue
            existing_path = aliases.get(alias)
            if existing_path and existing_path != path:
                raise CommandError(f'接口别名冲突: {alias} 同时对应 {existing_path} 和 {path}')
            aliases[alias] = path
        return aliases

    def _load_existing_aliases(self, output_path: Path) -> dict[str, str]:
        if not output_path.is_file():
            return {}
        try:
            aliases = json.loads(output_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise CommandError(f'现有接口别名表不是合法 JSON: {output_path}: {error}') from error
        if not isinstance(aliases, dict):
            raise CommandError(f'现有接口别名表必须是对象: {output_path}')
        return aliases