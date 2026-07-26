from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '根据 TestHub 自有 Swagger/OpenAPI 文件生成 HTTP 响应 JSON Schema。'

    def add_arguments(self, parser: Any) -> None:
        asset_root = Path(__file__).resolve().parents[2] / 'test_assets'
        parser.add_argument('--spec', default=str(asset_root / 'config' / 'schemas' / 'swagger.json'))
        parser.add_argument('--output', default=str(asset_root / 'config' / 'schemas' / 'http_response_schemas.json'))
        parser.add_argument('--check', action='store_true', help='仅检查生成文件是否与当前 Swagger 一致。')

    def handle(self, *args: Any, **options: Any) -> None:
        specification_path = Path(options['spec']).expanduser().resolve()
        output_path = Path(options['output']).expanduser().resolve()
        specification = self._load_specification(specification_path)
        document = self._generate_document(specification, specification_path)

        if options['check']:
            current = self._load_document(output_path)
            if current == document:
                self.stdout.write(self.style.SUCCESS(f'HTTP 响应 Schema 已是最新状态: {output_path}'))
                return
            raise CommandError(f'HTTP 响应 Schema 需要更新: {output_path}')

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f"已生成 {document['schema_count']} 条 HTTP 响应 Schema: {output_path}"))
        self.stdout.write(f"未定义响应 Schema: {document['missing_schema_count']} 条")

    def _load_specification(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise CommandError(f'Swagger/OpenAPI 文件不存在: {path}')
        try:
            content = path.read_text(encoding='utf-8')
            specification = yaml.safe_load(content) if path.suffix in {'.yaml', '.yml'} else json.loads(content)
        except (json.JSONDecodeError, yaml.YAMLError) as error:
            raise CommandError(f'Swagger/OpenAPI 文件格式无效: {error}') from error
        if not isinstance(specification, dict) or not isinstance(specification.get('paths'), dict):
            raise CommandError('Swagger/OpenAPI 文件缺少 paths 对象。')
        return specification

    def _load_document(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise CommandError(f'现有 HTTP 响应 Schema 文件不是合法 JSON: {error}') from error

    def _generate_document(self, specification: dict[str, Any], specification_path: Path) -> dict[str, Any]:
        schemas: dict[str, dict[str, Any]] = {}
        missing_schema_count = 0
        for path, operations in specification['paths'].items():
            if not isinstance(operations, dict):
                continue
            for method, operation in operations.items():
                if method.lower() not in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'} or not isinstance(operation, dict):
                    continue
                for status_code, response in operation.get('responses', {}).items():
                    if not isinstance(response, dict) or 'schema' not in response:
                        missing_schema_count += 1
                        continue
                    key = f'{method.upper()} {path} {status_code}'
                    schemas[key] = self._convert_schema(specification, response['schema'], set())
        source_hash = hashlib.sha256(specification_path.read_bytes()).hexdigest()
        return {
            'format_version': 1,
            'source': specification_path.name,
            'source_hash': source_hash,
            'schema_count': len(schemas),
            'missing_schema_count': missing_schema_count,
            'schemas': schemas,
        }

    def _convert_schema(self, specification: dict[str, Any], schema: Any, resolving: set[str]) -> dict[str, Any]:
        if not isinstance(schema, dict):
            return {}
        reference = schema.get('$ref')
        if isinstance(reference, str):
            if reference in resolving:
                return {}
            resolved = self._resolve_reference(specification, reference)
            return self._convert_schema(specification, resolved, resolving | {reference})
        converted = {
            key: value
            for key, value in schema.items()
            if key in {'type', 'format', 'enum', 'minimum', 'maximum', 'minLength', 'maxLength', 'pattern', 'minItems', 'maxItems', 'additionalProperties'}
        }
        if isinstance(schema.get('properties'), dict):
            converted['type'] = converted.get('type', 'object')
            converted['properties'] = {
                name: self._convert_schema(specification, value, resolving)
                for name, value in schema['properties'].items()
            }
        if isinstance(schema.get('required'), list):
            converted['required'] = schema['required']
        if 'items' in schema:
            converted['type'] = converted.get('type', 'array')
            converted['items'] = self._convert_schema(specification, schema['items'], resolving)
        if isinstance(schema.get('allOf'), list):
            merged: dict[str, Any] = {}
            for item in schema['allOf']:
                converted_item = self._convert_schema(specification, item, resolving)
                merged.update(converted_item)
                if 'properties' in converted_item:
                    merged.setdefault('properties', {}).update(converted_item['properties'])
                if 'required' in converted_item:
                    merged['required'] = sorted(set(merged.get('required', [])) | set(converted_item['required']))
            converted.update(merged)
        return converted or {'type': 'object'}

    def _resolve_reference(self, specification: dict[str, Any], reference: str) -> dict[str, Any]:
        if not reference.startswith('#/'):
            return {}
        current: Any = specification
        for part in reference[2:].split('/'):
            if not isinstance(current, dict):
                return {}
            current = current.get(part.replace('~1', '/').replace('~0', '~'))
        return current if isinstance(current, dict) else {}