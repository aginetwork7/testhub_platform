from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

from backend.log_config import get_logger

from .contracts import LLMCallContext, ModelConfig
from .exceptions import LLMClientError

logger = get_logger(__name__)

ContentCallback = Callable[[str], Awaitable[None]]


class OpenAICompatibleClient:
    """Shared transport for OpenAI-compatible chat completion APIs."""

    MAX_CONTINUATIONS = 5

    @staticmethod
    def build_request_payload(
        config: ModelConfig,
        messages: list[dict[str, Any]],
        max_tokens: int,
        stream: bool,
        response_format: dict[str, Any] | None = None,
        enable_thinking: bool | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            'model': config.model_name,
            'messages': messages,
            'stream': stream,
        }
        model_name = str(config.model_name or '').lower()
        is_reasoning_model = model_name.startswith(('gpt-5', 'o1', 'o3', 'o4'))
        token_parameter = 'max_completion_tokens' if is_reasoning_model else 'max_tokens'
        data[token_parameter] = max_tokens

        if not is_reasoning_model:
            data['temperature'] = 1.0 if 'kimi' in model_name else config.temperature
            data['top_p'] = config.top_p

        if config.model_type == 'qwen':
            data['chat_template_kwargs'] = {'enable_thinking': bool(enable_thinking)}
        if response_format is not None and not stream:
            data['response_format'] = response_format
        if tools and not stream:
            data['tools'] = tools
        if tool_choice is not None and tools and not stream:
            data['tool_choice'] = tool_choice
        return data

    @staticmethod
    def build_chat_completions_url(config: ModelConfig) -> str:
        base_url = config.base_url.rstrip('/')
        if base_url.endswith('/chat/completions'):
            return base_url
        if config.model_type in {'gemini', 'google_gemini'}:
            return f'{base_url}/chat/completions'
        if re.search(r'/v(\d+)/?$', base_url):
            return f'{base_url}/chat/completions'
        return f'{base_url}/v1/chat/completions'

    @staticmethod
    def _timeout() -> httpx.Timeout:
        return httpx.Timeout(connect=60.0, read=900.0, write=60.0, pool=60.0)

    @classmethod
    async def complete(
        cls,
        config: ModelConfig,
        messages: list[dict[str, Any]],
        context: LLMCallContext,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        enable_thinking: bool | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any | None = None,
    ) -> dict[str, Any]:
        actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        payload = cls.build_request_payload(
            config=config,
            messages=messages,
            max_tokens=actual_max_tokens,
            stream=False,
            response_format=response_format,
            enable_thinking=enable_thinking,
            tools=tools,
            tool_choice=tool_choice,
        )
        url = cls.build_chat_completions_url(config)
        prefix = context.log_prefix()
        logger.info(
            f'{prefix} LLM request model={config.model_name} url={url} '
            f'max_tokens={actual_max_tokens} temperature={config.temperature} top_p={config.top_p}'
        )

        try:
            async with httpx.AsyncClient(timeout=cls._timeout(), http2=False) as client:
                response = await client.post(url, headers=cls._headers(config), json=payload)
                response.raise_for_status()
                result = response.json()
        except httpx.HTTPStatusError as error:
            message = f'{config.get_model_type_display()} API返回错误 {error.response.status_code}: {error.response.text}'
            logger.error(f'{prefix} {message}')
            raise LLMClientError(message) from error
        except httpx.TimeoutException as error:
            message = f'{config.get_model_type_display()} API请求超时，请稍后再试或检查网络连接'
            logger.error(f'{prefix} {message}: {error!r}')
            raise LLMClientError(message) from error
        except (httpx.RequestError, ValueError) as error:
            message = f'{config.get_model_type_display()} API调用失败: {str(error) or repr(error)}'
            logger.error(f'{prefix} {message}')
            raise LLMClientError(message) from error

        logger.info(f'{prefix} LLM response status={response.status_code} body={str(result)[:200]}')
        return result

    @classmethod
    async def stream(
        cls,
        config: ModelConfig,
        messages: list[dict[str, Any]],
        context: LLMCallContext,
        callback: ContentCallback | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        url = cls.build_chat_completions_url(config)
        current_messages = list(messages)
        continuation_count = 0
        prefix = context.log_prefix()

        while continuation_count <= cls.MAX_CONTINUATIONS:
            payload = cls.build_request_payload(
                config=config,
                messages=current_messages,
                max_tokens=actual_max_tokens,
                stream=True,
            )
            logger.info(
                f'{prefix} Streaming LLM request attempt={continuation_count + 1} '
                f'messages={len(current_messages)}'
            )
            chunk_content_buffer = ''
            finish_reason = None

            try:
                async with httpx.AsyncClient(timeout=cls._timeout(), http2=False) as client:
                    async with client.stream(
                        'POST', url, headers=cls._headers(config), json=payload
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip() or not line.startswith('data:'):
                                continue
                            data_str = line[6:] if line.startswith('data: ') else line[5:]
                            if data_str.strip() == '[DONE]':
                                break
                            try:
                                chunk_data = json.loads(data_str)
                            except json.JSONDecodeError as error:
                                logger.warning(f'{prefix} Invalid streaming JSON: {error}')
                                continue
                            cls._raise_stream_error(chunk_data)
                            choices = chunk_data.get('choices') or []
                            if not choices:
                                continue
                            choice = choices[0]
                            finish_reason = choice.get('finish_reason')
                            content = choice.get('delta', {}).get('content', '')
                            if content:
                                chunk_content_buffer += content
                                if callback:
                                    await callback(content)
                                yield content
            except httpx.HTTPError as error:
                logger.error(f'{prefix} Streaming LLM request failed: {error!r}')
                raise LLMClientError(
                    f'{config.get_model_type_display()} 流式API调用失败: {str(error) or repr(error)}'
                ) from error

            if finish_reason != 'length':
                logger.info(f'{prefix} Streaming LLM response completed finish_reason={finish_reason}')
                break

            continuation_count += 1
            logger.warning(f'{prefix} Streaming LLM response truncated; continuing attempt={continuation_count}')
            if current_messages[-1]['role'] == 'assistant':
                current_messages[-1]['content'] += chunk_content_buffer
            else:
                current_messages.append({'role': 'assistant', 'content': chunk_content_buffer})
            if current_messages[-1]['role'] != 'user':
                current_messages.append({
                    'role': 'user',
                    'content': '请继续输出剩余的内容，不要重复已输出的部分，紧接着上文继续。',
                })

    @staticmethod
    def _headers(config: ModelConfig) -> dict[str, str]:
        return {
            'Authorization': f'Bearer {config.api_key}',
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _raise_stream_error(chunk_data: dict[str, Any]) -> None:
        if 'status' in chunk_data and chunk_data.get('status') != '200':
            raise LLMClientError(f"API错误: {chunk_data.get('msg', 'Unknown error')}")
        if 'error' in chunk_data:
            error_info = chunk_data['error']
            message = error_info.get('message', str(error_info)) if isinstance(error_info, dict) else str(error_info)
            raise LLMClientError(f'API错误: {message}')