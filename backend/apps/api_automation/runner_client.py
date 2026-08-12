from __future__ import annotations

import os
from typing import Any

import requests

from .models import ApiAutomationCase, ApiAutomationConfiguration, ApiAutomationRun


def is_configured() -> bool:
    return bool(os.environ.get('API_AUTOMATION_RUNNER_URL'))


def _authorization_headers() -> dict[str, str]:
    token = os.environ.get('API_AUTOMATION_RUNNER_TOKEN', '')
    return {'Authorization': f'Bearer {token}'} if token else {}


def _default_role(configuration: ApiAutomationConfiguration) -> str:
    profiles = configuration.auth_profiles if isinstance(configuration.auth_profiles, dict) else {}
    configured_role = next(
        (
            role
            for role, profile in profiles.items()
            if isinstance(profile, dict) and profile.get('is_default_role')
        ),
        '',
    )
    if configured_role:
        return configured_role
    legacy_role = configuration.variables.get('default_role') if isinstance(configuration.variables, dict) else ''
    return str(legacy_role or 'dealer')


def execute_case(run: ApiAutomationRun, case: ApiAutomationCase, configuration: ApiAutomationConfiguration) -> dict[str, Any]:
    response = requests.post(
        f"{os.environ['API_AUTOMATION_RUNNER_URL'].rstrip('/')}/v1/runs",
        headers=_authorization_headers(),
        json={
            'run_id': run.id,
            'timeout_seconds': configuration.timeout_seconds,
            'configuration': {
                'base_url': configuration.base_url,
                'websocket_url': configuration.websocket_url,
                'variables': configuration.variables,
                'auth_profiles': configuration.auth_profiles,
                'payment_config': configuration.payment_config,
                'model_profiles': configuration.model_profiles,
                'runtime_settings': configuration.runtime_settings,
                'endpoint_paths': {
                    endpoint.key: endpoint.path
                    for endpoint in case.suite.project.endpoints.all()
                },
                'websocket_params': case.suite.project.websocket_params,
                'websocket_schemas': case.suite.project.websocket_schemas,
                'data_endpoints': configuration.variables.get('data_endpoints', {}),
                'model_images': configuration.variables.get('model_images', {}),
                'default_role': _default_role(configuration),
            },
            'case': {
                'id': case.id,
                'node_id': case.node_id,
                'execution_mode': case.execution_mode,
                'source_class': case.source_class,
                'module_imports': case.module_imports,
                'module_support_code': case.module_support_code,
                'class_support_code': case.class_support_code,
                'setup_code': case.setup_code,
                'teardown_code': case.teardown_code,
                'source_code': case.source_code,
                'steps': [
                    {
                        'step_type': step.step_type,
                        'request_data': step.request_data,
                        'assertions': step.assertions,
                        'is_executable': step.is_executable,
                    }
                    for step in case.steps.all()
                ],
            },
        },
        timeout=configuration.timeout_seconds + 15,
    )
    response.raise_for_status()
    return response.json()


def generate_run_report(run: ApiAutomationRun) -> dict[str, Any]:
    response = requests.post(
        f"{os.environ['API_AUTOMATION_RUNNER_URL'].rstrip('/')}/v1/reports",
        headers=_authorization_headers(),
        json={'run_id': run.id},
        timeout=105,
    )
    response.raise_for_status()
    return response.json()