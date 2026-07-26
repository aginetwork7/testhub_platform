from __future__ import annotations

import ast
import hashlib
import json
import textwrap
from datetime import date
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.api_automation.models import (
    ApiAutomationCase,
    ApiAutomationCoverageSnapshot,
    ApiAutomationEndpoint,
    ApiAutomationProject,
    ApiAutomationStep,
    ApiAutomationSuite,
)
from apps.api_automation.coverage import collect_covered_endpoint_keys


@dataclass(frozen=True)
class ImportedStep:
    name: str
    step_type: str
    request_data: dict[str, Any]
    assertions: list[dict[str, Any]]
    code: str
    is_executable: bool


@dataclass(frozen=True)
class ImportedCase:
    name: str
    source_path: str
    source_class: str
    source_function: str
    node_id: str
    description: str
    priority: str
    markers: list[str]
    parameter_sets: list[dict[str, Any]]
    capabilities: list[str]
    module_imports: str
    module_support_code: str
    class_support_code: str
    support_code: str
    source_code: str
    setup_code: str
    teardown_code: str
    is_skipped: bool
    skip_reason: str
    source_hash: str
    steps: list[ImportedStep]


class Command(BaseCommand):
    help = '静态导入 pyapitest 的测试用例到 API 自动化测试模块，不执行也不修改来源代码。'

    def add_arguments(self, parser: Any) -> None:
        default_source = Path(__file__).resolve().parents[2] / 'test_assets' / 'tests'
        parser.add_argument(
            '--source',
            default=str(default_source),
            help='TestHub API 自动化测试资产目录，默认使用 apps/api_automation/test_assets/tests。',
        )
        parser.add_argument('--project-name', default='PyApiTest 项目', help='TestHub 中的 API 自动化项目名称。')
        parser.add_argument('--owner', help='项目负责人用户名或邮箱。')
        parser.add_argument('--dry-run', action='store_true', help='仅解析并输出统计，不写入数据库。')
        parser.add_argument('--prune', action='store_true', help='删除该项目中已不在来源目录的用例。')

    def handle(self, *args: Any, **options: Any) -> None:
        source_root = Path(options['source']).expanduser().resolve()
        if not source_root.is_dir():
            raise CommandError(f'测试来源目录不存在: {source_root}')

        source_files = sorted(source_root.rglob('test_*.py'))
        if not source_files:
            raise CommandError(f'未找到 test_*.py 文件: {source_root}')

        self._endpoint_paths = self._load_endpoint_paths(source_root)
        self._endpoint_metadata = self._load_endpoint_metadata(source_root)
        self._websocket_params = self._load_websocket_params(source_root)
        imported_cases = [
            case
            for source_file in source_files
            for case in self._extract_cases(source_root=source_root, source_file=source_file)
        ]
        self.stdout.write(
            f'已解析 {len(source_files)} 个文件、{len(imported_cases)} 个测试用例，来源: {source_root}'
        )

        if options['dry_run']:
            self._print_summary(imported_cases)
            return

        owner = self._resolve_owner(options['owner'])
        with transaction.atomic():
            project = self._upsert_project(name=options['project_name'], owner=owner)
            self._persist_endpoints(project=project)
            imported_node_ids = self._persist_cases(project=project, cases=imported_cases)
            self._persist_coverage_snapshots(project=project, source_root=source_root)
            if options['prune']:
                self._prune_cases(project=project, imported_node_ids=imported_node_ids)

        self._print_summary(imported_cases)
        self.stdout.write(self.style.SUCCESS(f'导入完成，项目 ID: {project.id}'))

    def _resolve_owner(self, owner_identifier: str | None):
        user_model = get_user_model()
        if owner_identifier:
            owner = user_model.objects.filter(username=owner_identifier).first()
            if owner is None:
                owner = user_model.objects.filter(email=owner_identifier).first()
            if owner is None:
                raise CommandError(f'未找到用户: {owner_identifier}')
            return owner

        owner = user_model.objects.filter(is_superuser=True).order_by('id').first()
        if owner is None:
            owner = user_model.objects.order_by('id').first()
        if owner is None:
            raise CommandError('当前系统没有可用用户，请先创建用户或通过 --owner 指定负责人。')
        return owner

    def _upsert_project(self, name: str, owner: Any) -> ApiAutomationProject:
        project, created = ApiAutomationProject.objects.update_or_create(
            name=name,
            defaults={
                'description': '由 import_pyapitest_cases 命令导入并由 TestHub 统一管理的 API 自动化测试资产。',
                'status': 'active',
                'owner': owner,
                'websocket_params': self._websocket_params,
            },
        )
        if not project.members.filter(id=owner.id).exists():
            project.members.add(owner)
        self.stdout.write(f"{'创建' if created else '更新'}项目: {project.name}")
        return project

    def _load_endpoint_paths(self, source_root: Path) -> dict[str, str]:
        endpoint_file = source_root.parent / 'config' / 'api_paths.json'
        if not endpoint_file.is_file():
            self.stdout.write(self.style.WARNING(f'未找到接口别名表，跳过接口目录导入: {endpoint_file}'))
            return {}
        try:
            endpoint_paths = json.loads(endpoint_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise CommandError(f'接口别名表不是合法 JSON: {endpoint_file}: {error}') from error
        if not isinstance(endpoint_paths, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in endpoint_paths.items()
        ):
            raise CommandError(f'接口别名表必须是 string -> string 映射: {endpoint_file}')
        return endpoint_paths

    def _persist_endpoints(self, project: ApiAutomationProject) -> None:
        for key, path in self._endpoint_paths.items():
            metadata = self._endpoint_metadata.get(path, {})
            ApiAutomationEndpoint.objects.update_or_create(
                project=project,
                key=key,
                defaults={
                    'path': path,
                    'description': metadata.get('description', ''),
                    'methods': metadata.get('methods', []),
                    'tags': metadata.get('tags', []),
                    'summary': metadata.get('summary', ''),
                    'deprecated': metadata.get('deprecated', False),
                },
            )
        self.stdout.write(f'导入接口目录: {len(self._endpoint_paths)} 条')

    def _load_endpoint_metadata(self, source_root: Path) -> dict[str, dict[str, Any]]:
        specification_path = source_root.parent / 'config' / 'schemas' / 'swagger.json'
        if not specification_path.is_file():
            return {}
        try:
            specification = json.loads(specification_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise CommandError(f'Swagger 文件不是合法 JSON: {specification_path}: {error}') from error
        metadata: dict[str, dict[str, Any]] = {}
        for path, operations in specification.get('paths', {}).items():
            if not isinstance(operations, dict):
                continue
            http_operations = [
                operation for method, operation in operations.items()
                if method.lower() in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'} and isinstance(operation, dict)
            ]
            metadata[path] = {
                'methods': [method.upper() for method in operations if method.lower() in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}],
                'tags': sorted({tag for operation in http_operations for tag in operation.get('tags', [])}),
                'summary': next((operation.get('summary', '') for operation in http_operations if operation.get('summary')), ''),
                'description': next((operation.get('description', '') for operation in http_operations if operation.get('description')), ''),
                'deprecated': any(operation.get('deprecated', False) for operation in http_operations),
            }
        return metadata

    def _persist_coverage_snapshots(self, project: ApiAutomationProject, source_root: Path) -> None:
        total_endpoints = ApiAutomationEndpoint.objects.filter(project=project).count()
        covered_aliases = collect_covered_endpoint_keys(project, source_root)
        covered_endpoints = len(covered_aliases)
        coverage_rate = round((covered_endpoints / total_endpoints * 100) if total_endpoints else 0, 2)
        today = timezone.localdate()
        week_start = today.fromordinal(today.toordinal() - today.weekday())
        month_start = date(today.year, today.month, 1)
        for period, snapshot_date in (('WEEKLY', week_start), ('MONTHLY', month_start)):
            ApiAutomationCoverageSnapshot.objects.update_or_create(
                project=project,
                period=period,
                snapshot_date=snapshot_date,
                defaults={
                    'total_endpoints': total_endpoints,
                    'covered_endpoints': covered_endpoints,
                    'coverage_rate': coverage_rate,
                },
            )

    def _load_websocket_params(self, source_root: Path) -> dict[str, Any]:
        parameter_file = source_root.parent / 'src' / 'data' / 'params.py'
        if not parameter_file.is_file():
            self.stdout.write(self.style.WARNING(f'未找到 WebSocket 参数文件: {parameter_file}'))
            return {}
        source_tree = ast.parse(parameter_file.read_text(encoding='utf-8'), filename=str(parameter_file))
        for node in source_tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'WEBSOCKET_PARAMS' for target in node.targets):
                try:
                    params = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError) as error:
                    raise CommandError(f'WebSocket 参数不是静态数据: {parameter_file}: {error}') from error
                if isinstance(params, dict):
                    self.stdout.write(f'导入 WebSocket 参数: {len(params)} 组')
                    return params
        return {}

    def _persist_cases(
        self,
        project: ApiAutomationProject,
        cases: Iterable[ImportedCase],
    ) -> set[str]:
        suite_cache: dict[str, ApiAutomationSuite] = {}
        imported_node_ids: set[str] = set()

        for imported_case in cases:
            suite = self._get_or_create_suite(
                project=project,
                source_path=str(Path(imported_case.source_path).parent),
                suite_cache=suite_cache,
            )
            case, created = ApiAutomationCase.objects.update_or_create(
                node_id=imported_case.node_id,
                defaults={
                    'suite': suite,
                    'name': imported_case.name,
                    'description': imported_case.description,
                    'source_path': imported_case.source_path,
                    'source_class': imported_case.source_class,
                    'source_function': imported_case.source_function,
                    'priority': imported_case.priority,
                    'markers': imported_case.markers,
                    'parameter_sets': imported_case.parameter_sets,
                    'capabilities': imported_case.capabilities,
                    'module_imports': imported_case.module_imports,
                    'module_support_code': imported_case.module_support_code,
                    'class_support_code': imported_case.class_support_code,
                    'support_code': imported_case.support_code,
                    'source_code': imported_case.source_code,
                    'setup_code': imported_case.setup_code,
                    'teardown_code': imported_case.teardown_code,
                    'execution_mode': self._execution_mode(imported_case),
                    'is_skipped': imported_case.is_skipped,
                    'skip_reason': imported_case.skip_reason,
                    'source_hash': imported_case.source_hash,
                },
            )
            self._replace_steps(case=case, steps=imported_case.steps)
            imported_node_ids.add(case.node_id)
            self.stdout.write(f"{'创建' if created else '更新'}用例: {case.node_id}")

        return imported_node_ids

    def _get_or_create_suite(
        self,
        project: ApiAutomationProject,
        source_path: str,
        suite_cache: dict[str, ApiAutomationSuite],
    ) -> ApiAutomationSuite:
        normalized_path = Path(source_path).as_posix()
        cached_suite = suite_cache.get(normalized_path)
        if cached_suite is not None:
            return cached_suite

        parent = None
        current_parts: list[str] = []
        for part in Path(normalized_path).parts:
            current_parts.append(part)
            current_path = Path(*current_parts).as_posix()
            current_suite = suite_cache.get(current_path)
            if current_suite is None:
                current_suite, _ = ApiAutomationSuite.objects.get_or_create(
                    project=project,
                    source_path=current_path,
                    defaults={
                        'name': part,
                        'parent': parent,
                    },
                )
                suite_cache[current_path] = current_suite
            parent = current_suite

        if parent is None:
            raise CommandError(f'无法为来源路径创建套件: {source_path}')
        return parent

    def _replace_steps(self, case: ApiAutomationCase, steps: list[ImportedStep]) -> None:
        case.steps.all().delete()
        ApiAutomationStep.objects.bulk_create(
            [
                ApiAutomationStep(
                    case=case,
                    order=index,
                    name=step.name,
                    step_type=step.step_type,
                    request_data=step.request_data,
                    assertions=step.assertions,
                    code=step.code,
                    is_executable=step.is_executable,
                )
                for index, step in enumerate(steps, start=1)
            ]
        )

    def _prune_cases(self, project: ApiAutomationProject, imported_node_ids: set[str]) -> None:
        stale_cases = ApiAutomationCase.objects.filter(suite__project=project).exclude(node_id__in=imported_node_ids)
        deleted_count, _ = stale_cases.delete()
        if deleted_count:
            self.stdout.write(f'删除来源中已不存在的用例及关联记录: {deleted_count}')

    def _extract_cases(self, source_root: Path, source_file: Path) -> list[ImportedCase]:
        source_text = source_file.read_text(encoding='utf-8')
        source_tree = ast.parse(source_text, filename=str(source_file))
        source_path = source_file.relative_to(source_root).as_posix()
        module_imports = self._extract_module_imports(source_text, source_tree)
        module_support_code = self._extract_module_support_code(source_text, source_tree)
        imported_cases: list[ImportedCase] = []

        for class_node in source_tree.body:
            if not isinstance(class_node, ast.ClassDef) or not class_node.name.startswith('Test'):
                continue

            setup_code = self._extract_lifecycle_code(source_text, class_node, ('setup_class', 'setup_method'))
            teardown_code = self._extract_lifecycle_code(source_text, class_node, ('teardown_method', 'teardown_class'))
            for function_node in class_node.body:
                if not isinstance(function_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not function_node.name.startswith('test_'):
                    continue
                imported_cases.append(
                    self._extract_case(
                        source_text=source_text,
                        source_path=source_path,
                        class_name=class_node.name,
                        class_node=class_node,
                        function_node=function_node,
                        setup_code=setup_code,
                        teardown_code=teardown_code,
                        module_imports=module_imports,
                        module_support_code=module_support_code,
                    )
                )
        return imported_cases

    def _extract_lifecycle_code(
        self,
        source_text: str,
        class_node: ast.ClassDef,
        method_names: tuple[str, ...],
    ) -> str:
        snippets = [
            self._source_with_decorators(source_text, node)
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in method_names
        ]
        return '\n\n'.join(snippet for snippet in snippets if snippet)

    def _extract_module_imports(self, source_text: str, source_tree: ast.Module) -> str:
        return '\n'.join(
            ast.get_source_segment(source_text, node) or ''
            for node in source_tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        )

    def _extract_module_support_code(self, source_text: str, source_tree: ast.Module) -> str:
        return '\n\n'.join(
            self._source_with_decorators(source_text, node)
            for node in source_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('test_')
        )

    def _extract_case(
        self,
        source_text: str,
        source_path: str,
        class_name: str,
        class_node: ast.ClassDef,
        function_node: ast.FunctionDef | ast.AsyncFunctionDef,
        setup_code: str,
        teardown_code: str,
        module_imports: str,
        module_support_code: str,
    ) -> ImportedCase:
        markers, parameter_sets, is_skipped, skip_reason = self._extract_decorators(function_node)
        source_code = self._source_with_decorators(source_text, function_node)
        node_id = f'{source_path}::{class_name}::{function_node.name}'
        return ImportedCase(
            name=function_node.name,
            source_path=source_path,
            source_class=class_name,
            source_function=function_node.name,
            node_id=node_id,
            description=ast.get_docstring(function_node) or '',
            priority=self._resolve_priority(markers),
            markers=markers,
            parameter_sets=parameter_sets,
            capabilities=self._extract_capabilities(function_node, class_node),
            module_imports=module_imports,
            module_support_code=module_support_code,
            class_support_code=self._extract_support_code(source_text, class_node),
            support_code='\n\n'.join(filter(None, [module_support_code, self._extract_support_code(source_text, class_node)])),
            source_code=source_code,
            setup_code=setup_code,
            teardown_code=teardown_code,
            is_skipped=is_skipped,
            skip_reason=skip_reason,
            source_hash=hashlib.sha256(source_code.encode('utf-8')).hexdigest(),
            steps=self._extract_steps(source_text, function_node),
        )

    def _extract_support_code(self, source_text: str, class_node: ast.ClassDef) -> str:
        lifecycle_methods = {'setup_class', 'setup_method', 'teardown_method', 'teardown_class'}
        attributes = [
            ast.get_source_segment(source_text, node) or ''
            for node in class_node.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
        ]
        helpers = [
            textwrap.dedent(self._source_with_decorators(source_text, node))
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith('test_')
            and node.name not in lifecycle_methods
        ]
        return '\n\n'.join(filter(None, [*attributes, *helpers]))

    def _source_with_decorators(
        self,
        source_text: str,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> str:
        lines = source_text.splitlines(keepends=True)
        decorator_lines = [decorator.lineno for decorator in node.decorator_list]
        start_line = min([node.lineno, *decorator_lines]) - 1
        end_line = node.end_lineno or node.lineno
        return ''.join(lines[start_line:end_line])

    def _extract_decorators(
        self,
        function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> tuple[list[str], list[dict[str, Any]], bool, str]:
        markers: list[str] = []
        parameter_sets: list[dict[str, Any]] = []
        is_skipped = False
        skip_reason = ''
        for decorator in function_node.decorator_list:
            marker_name = self._marker_name(decorator)
            if marker_name is None:
                continue
            markers.append(marker_name)
            if marker_name == 'parametrize' and isinstance(decorator, ast.Call):
                parameter_sets.extend(self._extract_parameter_sets(decorator))
            if marker_name == 'skip':
                is_skipped = True
                if isinstance(decorator, ast.Call) and decorator.args:
                    skip_reason = self._node_value(decorator.args[0])
        return sorted(set(markers)), parameter_sets, is_skipped, skip_reason

    def _marker_name(self, decorator: ast.expr) -> str | None:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if not isinstance(target, ast.Attribute):
            return None
        if not isinstance(target.value, ast.Attribute) or not isinstance(target.value.value, ast.Name):
            return None
        if target.value.value.id != 'pytest' or target.value.attr != 'mark':
            return None
        return target.attr

    def _extract_parameter_sets(self, decorator: ast.Call) -> list[dict[str, Any]]:
        if len(decorator.args) < 2:
            return []
        names = self._node_value(decorator.args[0])
        values = self._literal_value(decorator.args[1])
        if not isinstance(names, str) or not isinstance(values, (list, tuple)):
            return []
        parameter_names = [name.strip() for name in names.split(',')]
        parameter_sets: list[dict[str, Any]] = []
        for value in values:
            value_list = list(value) if isinstance(value, tuple) else [value]
            if len(parameter_names) == len(value_list):
                parameter_sets.append(dict(zip(parameter_names, value_list, strict=True)))
        return parameter_sets

    def _extract_steps(
        self,
        source_text: str,
        function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[ImportedStep]:
        request_steps: list[ImportedStep] = []
        pending_assertions: list[dict[str, Any]] = []
        calls = sorted(
            (node for node in ast.walk(function_node) if isinstance(node, ast.Call)),
            key=lambda node: (node.lineno, node.col_offset),
        )
        for call in calls:
            call_name = self._call_name(call)
            if call_name.startswith('Assertions.'):
                pending_assertions.append(
                    {
                        'type': call_name.removeprefix('Assertions.'),
                        'arguments': [self._node_value(argument) for argument in call.args],
                    }
                )
                continue
            if call_name == 'api_instance.login':
                role = self._node_value(call.args[0]) if call.args else ''
                request_steps.append(
                    ImportedStep(
                        name='api_instance.login',
                        step_type='AUTHENTICATE',
                        request_data={'role': role},
                        assertions=[],
                        code=ast.get_source_segment(source_text, call) or '',
                        is_executable=isinstance(role, str),
                    )
                )
            elif call_name.startswith('api_instance.'):
                step_type = 'WEBSOCKET_REQUEST' if '.ws_' in call_name else 'HTTP_REQUEST'
                request_data = self._extract_request_data(call, call_name)
                request_steps.append(
                    ImportedStep(
                        name=call_name,
                        step_type=step_type,
                        request_data=request_data,
                        assertions=[],
                        code=ast.get_source_segment(source_text, call) or '',
                        is_executable=self._is_static_request(request_data),
                    )
                )
            elif call_name.endswith('.send_request'):
                payload = self._node_value(call.args[0]) if call.args else {}
                request_steps.append(
                    ImportedStep(
                        name=call_name,
                        step_type='WEBSOCKET_REQUEST',
                        request_data={'payload': payload},
                        assertions=[],
                        code=ast.get_source_segment(source_text, call) or '',
                        is_executable=isinstance(payload, dict),
                    )
                )
            elif call_name.endswith('.call_model'):
                model_type = self._node_value(call.args[1]) if len(call.args) > 1 else 'default'
                request_steps.append(
                    ImportedStep(
                        name=call_name,
                        step_type='MODEL_REQUEST',
                        request_data={'profile': model_type, 'payload': {}},
                        assertions=[],
                        code=ast.get_source_segment(source_text, call) or '',
                        is_executable=False,
                    )
                )
            elif call_name.startswith('StripePaymentService.'):
                action = call_name.removeprefix('StripePaymentService.')
                endpoint = 'admin/clear' if action == 'clear_mock_data' else f'admin/{action}'
                request_steps.append(
                    ImportedStep(
                        name=call_name,
                        step_type='PAYMENT_ACTION',
                        request_data={'endpoint': endpoint, 'payload': {}},
                        assertions=[],
                        code=ast.get_source_segment(source_text, call) or '',
                        is_executable=action == 'clear_mock_data',
                    )
                )

        if request_steps and pending_assertions:
            final_step = request_steps[-1]
            request_steps[-1] = ImportedStep(
                name=final_step.name,
                step_type=final_step.step_type,
                request_data=final_step.request_data,
                assertions=pending_assertions,
                code=final_step.code,
                is_executable=final_step.is_executable,
            )
        return request_steps

    def _extract_capabilities(
        self,
        function_node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_node: ast.ClassDef,
    ) -> list[str]:
        source = ast.unparse(function_node)
        class_source = ast.unparse(class_node)
        capabilities: set[str] = set()
        if 'api_instance.login(' in source or 'api_instance.get_token(' in source or 'api_instance.login(' in class_source:
            capabilities.add('authentication')
        if 'create_websocket_client(' in source or '.send_request(' in source or 'create_websocket_client(' in class_source:
            capabilities.add('websocket')
        if 'StripePaymentService(' in source or '.pay(' in source or 'PaymentIntent' in source or 'StripePaymentService(' in class_source:
            capabilities.add('payment')
        if 'ModelHandler(' in source or '.call_model(' in source or 'ModelHandler(' in class_source or '.call_model(' in class_source:
            capabilities.add('model')
        if any(isinstance(node, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith)) for node in ast.walk(function_node)):
            capabilities.add('dynamic_flow')
        return sorted(capabilities)

    def _extract_request_data(self, call: ast.Call, call_name: str) -> dict[str, Any]:
        keyword_values = {keyword.arg: self._node_value(keyword.value) for keyword in call.keywords if keyword.arg}
        client_method = call_name.removeprefix('api_instance.')
        endpoint = keyword_values.get('endpoint_path', keyword_values.get('url', self._node_value(call.args[0]) if call.args else ''))
        method = keyword_values.get('method', self._node_value(call.args[1]) if len(call.args) > 1 else '')
        if not method and client_method in {'get', 'post', 'put', 'patch', 'delete'}:
            method = client_method.upper()
        endpoint_path = self._endpoint_paths.get(endpoint, '') if isinstance(endpoint, str) else ''
        consumed_keywords = {'endpoint_path', 'url', 'method', 'params', 'headers', 'data', 'json', 'files', 'is_valid', 'timeout'}
        request_data: dict[str, Any] = {
            'client_method': client_method,
            'method': method,
            'endpoint': endpoint,
            'endpoint_path': endpoint_path,
            'params': keyword_values.get('params', {}),
            'headers': keyword_values.get('headers', {}),
            'body': keyword_values.get('data', keyword_values.get('json', {})),
            'path_params': {
                key: value
                for key, value in keyword_values.items()
                if key not in consumed_keywords
            },
        }
        return request_data

    def _is_static_request(self, request_data: dict[str, Any]) -> bool:
        return (
            isinstance(request_data['method'], str)
            and isinstance(request_data['endpoint'], str)
            and not self._has_dynamic_expression(request_data.get('path_params', {}))
            and not self._has_dynamic_expression(request_data.get('params', {}))
            and not self._has_dynamic_expression(request_data.get('headers', {}))
            and not self._has_dynamic_expression(request_data.get('body', {}))
        )

    def _has_dynamic_expression(self, value: Any) -> bool:
        if isinstance(value, dict):
            if set(value) == {'expression'}:
                return True
            return any(self._has_dynamic_expression(item) for item in value.values())
        if isinstance(value, list):
            return any(self._has_dynamic_expression(item) for item in value)
        return False

    def _call_name(self, call: ast.Call) -> str:
        return self._expression_name(call.func)

    def _expression_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = self._expression_name(node.value)
            return f'{prefix}.{node.attr}' if prefix else node.attr
        return ''

    def _node_value(self, node: ast.AST) -> Any:
        value = self._literal_value(node)
        if value is not None:
            return value
        return {'expression': ast.unparse(node)}

    def _literal_value(self, node: ast.AST) -> Any:
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            return None

    def _resolve_priority(self, markers: list[str]) -> str:
        for priority in ('P0', 'P1', 'P2'):
            if priority in markers:
                return priority
        return 'P2'

    def _execution_mode(self, imported_case: ImportedCase) -> str:
        if 'websocket' in imported_case.capabilities:
            return 'CODE'
        if not imported_case.steps or imported_case.parameter_sets or imported_case.setup_code or imported_case.teardown_code:
            return 'CODE'
        if any(not step.is_executable for step in imported_case.steps):
            return 'CODE'
        supported_assertions = {'assert_status_code'}
        if any(
            assertion.get('type') not in supported_assertions
            for step in imported_case.steps
            for assertion in step.assertions
        ):
            return 'CODE'
        return 'STRUCTURED'

    def _print_summary(self, cases: list[ImportedCase]) -> None:
        structured_step_count = sum(len(case.steps) for case in cases)
        skipped_case_count = sum(case.is_skipped for case in cases)
        self.stdout.write(f'测试用例: {len(cases)}')
        self.stdout.write(f'静态提取请求步骤: {structured_step_count}')
        self.stdout.write(f'标记为跳过的用例: {skipped_case_count}')