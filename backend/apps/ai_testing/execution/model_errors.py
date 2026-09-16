"""Classify model-provider failures that deserve a retry or a failover rather than a plan rejection."""

from __future__ import annotations

import asyncio
import re

_TRANSPORT_ERROR_NAMES = {'ReadTimeout', 'ConnectTimeout', 'ConnectError', 'RemoteProtocolError', 'TransportError', 'PoolTimeout', 'ReadError'}


def is_transient_llm_error(error: BaseException) -> bool:
    """Provider overload, rate limiting and transport failures are transient; contract rejections are not."""
    if isinstance(error, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    name = type(error).__name__
    text = str(error)
    if name == 'LLMClientError':
        if re.search(r'返回错误\s*(?:408|409|425|429|5\d\d)\b', text) or re.search(r'\b(?:429|50[0-9]|52[0-9])\b', text):
            return True
        return bool(re.search(r'timeout|timed out|temporarily|unavailable|overloaded|rate limit|high demand|connection', text, re.I))
    return name in _TRANSPORT_ERROR_NAMES
