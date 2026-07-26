from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import ApiAutomationCase, ApiAutomationEndpoint, ApiAutomationProject


HTTP_METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}


@dataclass
class EndpointCoverage:
    endpoint: ApiAutomationEndpoint
    case_node_ids: set[str] = field(default_factory=set)
    source_files: set[str] = field(default_factory=set)


def collect_covered_endpoint_keys(
    project: ApiAutomationProject,
    source_root: Path | None = None,
) -> set[str]:
    return set(collect_endpoint_coverage(project, source_root))


def collect_endpoint_coverage(
    project: ApiAutomationProject,
    source_root: Path | None = None,
) -> dict[str, EndpointCoverage]:
    endpoints = list(ApiAutomationEndpoint.objects.filter(project=project).only('key', 'path', 'methods'))
    endpoint_by_key = {endpoint.key: endpoint for endpoint in endpoints}
    endpoints_by_path: dict[str, list[ApiAutomationEndpoint]] = {}
    for endpoint in endpoints:
        endpoints_by_path.setdefault(endpoint.path, []).append(endpoint)

    tests_root = source_root or Path(__file__).resolve().parent / 'test_assets' / 'tests'
    if not tests_root.is_dir():
        return {}

    cases_by_file_and_class: dict[tuple[str, str], set[str]] = defaultdict(set)
    cases_by_file_and_function: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for case in ApiAutomationCase.objects.filter(suite__project=project).only(
        'source_path', 'source_class', 'source_function', 'node_id'
    ):
        cases_by_file_and_class[(case.source_path, case.source_class)].add(case.node_id)
        cases_by_file_and_function[(case.source_path, case.source_class, case.source_function)].add(case.node_id)

    coverage = {endpoint.key: EndpointCoverage(endpoint=endpoint) for endpoint in endpoints}
    for test_file in tests_root.rglob('test_*.py'):
        try:
            tree = ast.parse(test_file.read_text(encoding='utf-8'), filename=str(test_file))
        except (OSError, SyntaxError):
            continue
        source_path = test_file.relative_to(tests_root).as_posix()
        _CoverageVisitor(
            source_path=source_path,
            source_file_name=test_file.name,
            endpoint_by_key=endpoint_by_key,
            endpoints_by_path=endpoints_by_path,
            cases_by_file_and_class=cases_by_file_and_class,
            cases_by_file_and_function=cases_by_file_and_function,
            coverage=coverage,
        ).visit(tree)
    return coverage


class _CoverageVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        source_path: str,
        source_file_name: str,
        endpoint_by_key: dict[str, ApiAutomationEndpoint],
        endpoints_by_path: dict[str, list[ApiAutomationEndpoint]],
        cases_by_file_and_class: dict[tuple[str, str], set[str]],
        cases_by_file_and_function: dict[tuple[str, str, str], set[str]],
        coverage: dict[str, EndpointCoverage],
    ) -> None:
        self.source_path = source_path
        self.source_file_name = source_file_name
        self.endpoint_by_key = endpoint_by_key
        self.endpoints_by_path = endpoints_by_path
        self.cases_by_file_and_class = cases_by_file_and_class
        self.cases_by_file_and_function = cases_by_file_and_function
        self.coverage = coverage
        self.class_name = ''
        self.function_name = ''

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        previous_class, previous_function = self.class_name, self.function_name
        self.class_name, self.function_name = node.name, ''
        self.generic_visit(node)
        self.class_name, self.function_name = previous_class, previous_function

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        previous_function = self.function_name
        self.function_name = node.name
        self.generic_visit(node)
        self.function_name = previous_function

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> Any:
        endpoint_value, method = _api_instance_call(node)
        if endpoint_value:
            for endpoint in self._matching_endpoints(endpoint_value, method):
                matching_cases = self._matching_cases()
                if matching_cases:
                    entry = self.coverage[endpoint.key]
                    entry.case_node_ids.update(matching_cases)
                    entry.source_files.add(self.source_file_name)
        self.generic_visit(node)

    def _matching_endpoints(self, endpoint_value: str, method: str | None) -> list[ApiAutomationEndpoint]:
        endpoint = self.endpoint_by_key.get(endpoint_value)
        if endpoint is not None:
            return [endpoint]
        return [
            candidate
            for candidate in self.endpoints_by_path.get(endpoint_value, [])
            if method is None or method in {str(item).upper() for item in candidate.methods}
        ]

    def _matching_cases(self) -> set[str]:
        if self.function_name.startswith('test_'):
            return self.cases_by_file_and_function.get(
                (self.source_path, self.class_name, self.function_name),
                set(),
            )
        if self.class_name:
            return self.cases_by_file_and_class.get((self.source_path, self.class_name), set())
        matched_cases: set[str] = set()
        for (case_source_path, _), case_node_ids in self.cases_by_file_and_class.items():
            if case_source_path == self.source_path:
                matched_cases.update(case_node_ids)
        return matched_cases


def _api_instance_call(call: ast.Call) -> tuple[str | None, str | None]:
    if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
        return None, None
    if call.func.value.id != 'api_instance':
        return None, None
    function_name = call.func.attr
    if function_name == 'send':
        endpoint = _keyword_string(call, {'endpoint_path', 'url'})
        if endpoint is None and call.args:
            endpoint = _literal_string(call.args[0])
        method = _keyword_string(call, {'method'})
        if method is None and len(call.args) > 1:
            method = _literal_string(call.args[1])
        return endpoint, method.upper() if method and method.upper() in HTTP_METHODS else None
    if function_name.upper() in HTTP_METHODS and call.args:
        return _literal_string(call.args[0]), function_name.upper()
    return None, None


def _keyword_string(call: ast.Call, names: set[str]) -> str | None:
    for keyword in call.keywords:
        if keyword.arg in names:
            return _literal_string(keyword.value)
    return None


def _literal_string(node: ast.AST) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None