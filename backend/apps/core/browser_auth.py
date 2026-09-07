"""Resolve browser-login inputs from a global environment configuration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urljoin


class BrowserAuthenticationConfigurationError(ValueError):
    """Raised when an environment cannot provide browser authentication."""


@dataclass(frozen=True)
class BrowserLoginConfiguration:
    """A browser form login resolved from a configured environment role."""

    login_url: str
    username: str
    password: str


def resolve_browser_login(configuration: Any) -> BrowserLoginConfiguration | None:
    """Resolve the configured browser login without depending on a test product."""
    if configuration is None:
        return None
    runtime_settings = getattr(configuration, 'runtime_settings', {})
    settings = runtime_settings.get('ai_testing_browser', {}) if isinstance(runtime_settings, Mapping) else {}
    if not isinstance(settings, Mapping):
        raise BrowserAuthenticationConfigurationError('ai_testing_browser must be an object.')
    login_path = str(settings.get('login_path') or '').strip()
    if not login_path:
        return None
    web_url = str(getattr(configuration, 'web_url', '') or '').strip()
    if not web_url:
        raise BrowserAuthenticationConfigurationError('Browser login requires environment web_url.')
    profiles = getattr(configuration, 'auth_profiles', {})
    if not isinstance(profiles, Mapping):
        raise BrowserAuthenticationConfigurationError('Browser login requires auth_profiles.')
    profile_name = str(settings.get('auth_profile') or '').strip().lower()
    if not profile_name:
        profile_name = next(
            (
                str(name).lower()
                for name, profile in profiles.items()
                if isinstance(profile, Mapping) and profile.get('is_default_role')
            ),
            '',
        )
    profile = profiles.get(profile_name)
    if not isinstance(profile, Mapping):
        raise BrowserAuthenticationConfigurationError('Browser login auth_profile is not configured.')
    username = _resolve_secret(profile.get('username') or profile.get('email'))
    password = _resolve_secret(profile.get('password'))
    if not username or not password:
        raise BrowserAuthenticationConfigurationError('Browser login credentials are incomplete.')
    login_url = login_path if login_path.startswith(('http://', 'https://')) else urljoin(
        f'{web_url.rstrip("/")}/', login_path.lstrip('/'),
    )
    return BrowserLoginConfiguration(login_url=login_url, username=username, password=password)


def _resolve_secret(value: object) -> str:
    normalized = str(value or '').strip()
    match = re.fullmatch(r'\$\{([A-Z][A-Z0-9_]*)\}', normalized)
    return str(os.getenv(match.group(1), '')).strip() if match else normalized