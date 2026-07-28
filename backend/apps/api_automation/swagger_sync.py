from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from django.core.management import call_command
from django.db import transaction

from .models import ApiAutomationEndpoint, ApiAutomationProject


class SwaggerSyncError(ValueError):
    """Raised when a remote Swagger document cannot be synchronized."""


class SwaggerTokenExpiredError(SwaggerSyncError):
    code = 'SWAGGER_TOKEN_EXPIRED_OR_INVALID'


class SwaggerTokenPermissionError(SwaggerSyncError):
    code = 'SWAGGER_TOKEN_PERMISSION_DENIED'


class SwaggerSourceNotFoundError(SwaggerSyncError):
    code = 'SWAGGER_SOURCE_NOT_FOUND'


ASSET_ROOT = Path(__file__).resolve().parent / 'test_assets'
SWAGGER_PATH = ASSET_ROOT / 'config' / 'schemas' / 'swagger.json'
AWS_ACCESS_KEY_PATTERN = re.compile(rb'AKIA[0-9A-Z]{16}')


def synchronize_remote_swagger(
    project: ApiAutomationProject,
    source_url: str,
    timeout_seconds: int,
    access_token: str = '',
) -> dict[str, Any]:
    raw_document = _redact_sensitive_markers(
        _download_swagger(source_url, timeout_seconds, access_token)
    )
    specification = _parse_swagger(raw_document)
    _write_swagger_atomically(raw_document)

    paths_output = io.StringIO()
    schemas_output = io.StringIO()
    call_command('generate_api_automation_paths', stdout=paths_output)
    call_command('generate_api_automation_schemas', stdout=schemas_output)

    catalog = _synchronize_endpoint_catalog(project, specification)
    return {
        'source_url': source_url,
        'source_hash': hashlib.sha256(raw_document).hexdigest(),
        'catalog': catalog,
        'paths_output': paths_output.getvalue(),
        'schemas_output': schemas_output.getvalue(),
    }


def _download_swagger(source_url: str, timeout_seconds: int, access_token: str = '') -> bytes:
    parsed_url = urlparse(source_url)
    if parsed_url.scheme not in {'http', 'https'} or not parsed_url.netloc:
        raise SwaggerSyncError('Swagger 下载地址必须是有效的 HTTP 或 HTTPS URL。')

    try:
        headers = {'Accept': 'application/json'}
        if access_token.strip():
            headers['Authorization'] = f'Bearer {access_token.strip()}'
        response = requests.get(
            source_url,
            headers=headers,
            timeout=max(1, timeout_seconds),
        )
        if response.status_code == 401:
            raise SwaggerTokenExpiredError('GitHub token 已过期或无效，请更新部署环境中的 API_AUTOMATION_SWAGGER_TOKEN。')
        if response.status_code == 403:
            raise SwaggerTokenPermissionError('GitHub token 无权下载 Swagger，请检查 Contents: Read-only 权限和组织 SSO 授权。')
        if response.status_code == 404 and access_token.strip():
            raise SwaggerSourceNotFoundError('GitHub 未找到 Swagger 文件，请检查下载地址、分支和仓库访问权限。')
        response.raise_for_status()
    except requests.RequestException as error:
        raise SwaggerSyncError(f'Swagger 下载失败: {error}') from error

    if not response.content:
        raise SwaggerSyncError('Swagger 下载内容为空。')
    return response.content


def _parse_swagger(raw_document: bytes) -> dict[str, Any]:
    try:
        specification = json.loads(raw_document.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SwaggerSyncError(f'Swagger 原始数据不是有效的 UTF-8 JSON: {error}') from error

    if not isinstance(specification, dict) or not isinstance(specification.get('paths'), dict):
        raise SwaggerSyncError('Swagger 原始数据缺少 paths 对象。')
    return specification


def _redact_sensitive_markers(raw_document: bytes) -> bytes:
    return AWS_ACCESS_KEY_PATTERN.sub(b'REDACTED_AWS_ACCESS_KEY', raw_document)


def _write_swagger_atomically(raw_document: bytes) -> None:
    SWAGGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=SWAGGER_PATH.parent, delete=False) as temporary_file:
            temporary_file.write(raw_document)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, SWAGGER_PATH)
        os.chmod(SWAGGER_PATH, 0o644)
    except OSError as error:
        raise SwaggerSyncError(f'Swagger 文件写入失败: {error}') from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _synchronize_endpoint_catalog(
    project: ApiAutomationProject,
    specification: dict[str, Any],
) -> dict[str, int]:
    endpoint_definitions = _build_endpoint_definitions(specification)
    created_count = 0
    updated_count = 0

    with transaction.atomic():
        for key, definition in endpoint_definitions.items():
            _, created = ApiAutomationEndpoint.objects.update_or_create(
                project=project,
                key=key,
                defaults=definition,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        deleted_count, _ = ApiAutomationEndpoint.objects.filter(project=project).exclude(
            key__in=endpoint_definitions
        ).delete()

    return {
        'total': len(endpoint_definitions),
        'created': created_count,
        'updated': updated_count,
        'deleted': deleted_count,
    }


def _build_endpoint_definitions(specification: dict[str, Any]) -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    http_methods = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}

    for path, operations in specification['paths'].items():
        if not isinstance(path, str) or not isinstance(operations, dict):
            continue
        key = '_'.join(segment.strip('{}') for segment in path.split('/') if segment)
        if not key:
            continue
        if key in definitions and definitions[key]['path'] != path:
            raise SwaggerSyncError(f'接口别名冲突: {key} 同时对应多个路径。')

        http_operations = [
            operation
            for method, operation in operations.items()
            if method.lower() in http_methods and isinstance(operation, dict)
        ]
        definitions[key] = {
            'path': path,
            'methods': [method.upper() for method in operations if method.lower() in http_methods],
            'tags': sorted({tag for operation in http_operations for tag in operation.get('tags', [])}),
            'summary': next((operation.get('summary', '') for operation in http_operations if operation.get('summary')), ''),
            'description': next((operation.get('description', '') for operation in http_operations if operation.get('description')), ''),
            'deprecated': any(operation.get('deprecated', False) for operation in http_operations),
        }
    return definitions