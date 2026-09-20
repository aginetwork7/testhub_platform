"""Check that a run's environment is configured for AI testing before the browser starts.

``resolve_browser_login`` returns None when an environment has no ``ai_testing_browser`` block, and the
bootstrap used to take that as "nothing to do" and carry on. Every step then ran against ``about:blank``,
every selector missed, and the run failed after several minutes of replanning with nothing in the logs
pointing at the cause — one production run took a long time to trace back to a missing config block.

An environment that was never configured for AI testing is an expected state, not a product defect, so the
failure is reported as an environment problem and says exactly which fields to add.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Values that are almost certainly a mistake in web_url: the browser needs the site a person would open,
# not the API root. A production environment really was configured as '.../agi7/api'. This is a heuristic,
# so it is reported as advice alongside a real failure and never blocks a run on its own.
_SUSPICIOUS_WEB_URL_SUFFIXES = ('/api', '/api/', '/v1', '/v1/')


def _mapping(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _runtime_settings(configuration: Any) -> Mapping:
    return _mapping(getattr(configuration, 'runtime_settings', {}))


def web_url_looks_like_an_api_root(web_url: str) -> bool:
    normalized = str(web_url or '').strip().rstrip()
    return bool(normalized) and normalized.endswith(_SUSPICIOUS_WEB_URL_SUFFIXES)


def steps_need_data_factory(steps: list[dict] | None) -> bool:
    return any(
        isinstance(step, Mapping) and step.get('executor') == 'data_factory'
        for step in steps or []
    )


def steps_need_target_device(steps: list[dict] | None, task_description: str = '') -> bool:
    """Whether anything in this run depends on the environment's configured test device.

    Checked per run rather than always: a case about dark mode must not fail because the environment has no
    camera configured.
    """
    from apps.ai_testing.execution.environment_resources import refers_to_target_device

    haystack = [str(task_description or '')]
    for step in steps or []:
        if isinstance(step, Mapping):
            haystack.append(str(step.get('description') or ''))
            haystack.append(str(step.get('intent') or ''))
    return any(refers_to_target_device(text, []) for text in haystack if text)


def collect_environment_problems(
    configuration: Any,
    steps: list[dict] | None = None,
    task_description: str = '',
) -> list[str]:
    """Everything that would stop this run from reaching the product, in the order worth fixing."""
    from apps.core.browser_auth import BrowserAuthenticationConfigurationError, resolve_browser_login

    problems: list[str] = []
    if configuration is None:
        return ['未选择运行环境；AI 智能测试的浏览器用例必须指定一个已配置的运行环境。']

    settings = _mapping(_runtime_settings(configuration).get('ai_testing_browser'))
    web_url = str(getattr(configuration, 'web_url', '') or '').strip()

    if not settings:
        problems.append(
            '该运行环境未配置 AI 测试浏览器登录（runtime_settings.ai_testing_browser 缺失）。'
            '若需在此环境运行 AI 智能测试，请补充 login_path 与 auth_profile，'
            '并确保环境的 web_url 与 auth_profiles 已填写。'
        )
    elif not str(settings.get('login_path') or '').strip():
        problems.append('runtime_settings.ai_testing_browser.login_path 为空，无法确定登录页地址。')

    if not web_url:
        problems.append('运行环境的 web_url 为空，浏览器无从打开被测站点。')

    if settings:
        try:
            login = resolve_browser_login(configuration)
        except BrowserAuthenticationConfigurationError as error:
            problems.append(f'浏览器登录配置不完整：{error}')
        else:
            if login is None and not problems:
                problems.append('浏览器登录配置不完整，未能解析出可用的登录地址与账号。')

    if steps_need_data_factory(steps) and not _mapping(_runtime_settings(configuration).get('ai_testing_data_factory')):
        problems.append(
            '本次计划包含 data_factory 步骤，但该运行环境未配置 runtime_settings.ai_testing_data_factory。'
        )

    if steps_need_target_device(steps, task_description):
        main_device = _mapping(_mapping(_mapping(_runtime_settings(configuration).get('api')).get('edge')).get('main_device'))
        if not main_device:
            problems.append(
                '本次用例涉及默认测试设备，但该运行环境未配置 runtime_settings.api.edge.main_device。'
            )

    if problems and web_url_looks_like_an_api_root(web_url):
        # Advice, not a separate failure: it is the most common way a configured environment is still wrong.
        problems.append(
            f'另外请确认 web_url（{web_url}）是否填成了接口地址；浏览器用例需要的是站点首页地址。'
        )
    return problems


def describe_environment_problems(configuration: Any, problems: list[str]) -> str:
    name = str(getattr(configuration, 'name', '') or getattr(configuration, 'id', '') or '未知')
    lines = '\n'.join(f'  - {problem}' for problem in problems)
    return f'被测环境不可用：运行环境「{name}」未就绪，本次执行未开始浏览器。\n{lines}'
