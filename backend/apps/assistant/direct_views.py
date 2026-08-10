from __future__ import annotations

import hashlib
import json
import logging
import re

import requests
from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.shortcuts import render
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AgentModelConfig, AssistantMessage, AssistantSession, ChatMessage
from .serializers import (
    AssistantMessageSerializer,
    AssistantSessionCreateSerializer,
    AssistantSessionSerializer,
    ChatMessageSerializer,
)
from .tools import (
    execute_tool_call,
    format_tool_result_for_user,
    get_tool_contract_prompt,
    parse_tool_call_from_model_output,
    parse_tool_call_from_request_contract,
)


logger = logging.getLogger(__name__)
CHAT_CACHE_TTL_SECONDS = 300


def parse_request_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'false', '0', 'off', 'no'}:
            return False
        if normalized in {'true', '1', 'on', 'yes'}:
            return True
    return bool(value)


def build_openai_chat_url(config):
    base_url = config.base_url.rstrip('/')
    if base_url.endswith('/chat/completions'):
        return base_url
    if config.model_type in {'gemini', 'google_gemini'}:
        return f'{base_url}/chat/completions'
    if re.search(r'/v\d+$', base_url):
        return f'{base_url}/chat/completions'
    return f'{base_url}/v1/chat/completions'


def chat_token_parameter(model_name):
    normalized = str(model_name or '').lower()
    return 'max_completion_tokens' if normalized.startswith(('gpt-5', 'o1', 'o3', 'o4')) else 'max_tokens'


def build_chat_cache_key(config, messages, thinking_mode):
    payload = {
        'config_id': config.id,
        'model_name': config.model_name,
        'thinking_mode': thinking_mode,
        'tool_contract_version': 'v1',
        'messages': messages,
    }
    serialized = json.dumps(payload, ensure_ascii=True, separators=(',', ':'), sort_keys=True)
    return f'assistant:chat:{hashlib.sha256(serialized.encode("utf-8")).hexdigest()}'


def sanitize_model_output(content, thinking_mode):
    text = str(content or '')
    if thinking_mode:
        return text
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<think>.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<thinking>.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    return text.replace('</think>', '').replace('</thinking>', '').strip()


class AssistantSessionViewSet(viewsets.ModelViewSet):
    permission_classes = []

    def get_queryset(self):
        return AssistantSession.objects.filter(user=self.request.user).order_by('-updated_at')

    def get_serializer_class(self):
        return AssistantSessionCreateSerializer if self.action == 'create' else AssistantSessionSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def add_message(self, request, pk=None):
        session = self.get_object()
        serializer = AssistantMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(session=session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        session = self.get_object()
        return Response(ChatMessageSerializer(session.chat_messages.all(), many=True).data)


class ChatViewSet(viewsets.ViewSet):
    @staticmethod
    def _sse_payload(data):
        return f'data: {json.dumps(data, ensure_ascii=False)}\n\n'

    @action(detail=False, methods=['post'])
    def send_message_stream(self, request):
        session_id = request.data.get('session_id')
        message = request.data.get('message')
        tool_call_payload = request.data.get('tool_call')
        thinking_mode = parse_request_bool(request.data.get('thinking_mode'), default=True)
        if not session_id or not message:
            return Response({'error': 'session_id和message都是必填项'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            session = AssistantSession.objects.get(session_id=session_id, user=request.user)
        except AssistantSession.DoesNotExist:
            return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)

        chat_config = AgentModelConfig.objects.filter(role='chat', is_active=True).order_by('id').first()
        if not chat_config:
            return Response({'error': '未配置激活的 Chat 模型，请先在 AI Agent配置 中配置'}, status=status.HTTP_400_BAD_REQUEST)

        user_message = ChatMessage.objects.create(session=session, role='user', content=message)
        request_tool_contract = parse_tool_call_from_request_contract(str(message), tool_call_payload=tool_call_payload)
        request_tool_call = request_tool_contract.tool_call if request_tool_contract.matched else None
        if request_tool_call:
            tool_result = execute_tool_call(request_tool_call, request.user)
            assistant_content = format_tool_result_for_user(tool_result)

            def local_tool_stream():
                yield self._sse_payload({'type': 'start', 'user_message': ChatMessageSerializer(user_message).data})
                yield self._sse_payload({'type': 'replace', 'content': assistant_content})
                assistant_message = ChatMessage.objects.create(session=session, role='assistant', content=assistant_content)
                yield self._sse_payload({
                    'type': 'done',
                    'assistant_message': ChatMessageSerializer(assistant_message).data,
                    'usage': None,
                    'tool_call': {'name': request_tool_call.name, 'args': request_tool_call.args},
                    'tool_result': tool_result,
                    'tool_contract_status': request_tool_contract.status,
                    'tool_contract_error': None,
                })

            return self._stream_response(local_tool_stream())

        history = list(ChatMessage.objects.filter(session=session).order_by('-created_at')[:20])
        system_prompt = f'You are a professional software testing assistant. Answer clearly and concisely.\n\n{get_tool_contract_prompt()}'
        if not thinking_mode:
            system_prompt += '\n\nDo not reveal chain-of-thought or reasoning. Return only the final answer.'
        model_messages = [
            {'role': 'system', 'content': system_prompt},
            *[{'role': item.role, 'content': item.content} for item in reversed(history)],
        ]
        cache_key = build_chat_cache_key(chat_config, model_messages, thinking_mode)
        cached_response = cache.get(cache_key)

        def model_stream():
            yield self._sse_payload({'type': 'start', 'user_message': ChatMessageSerializer(user_message).data})
            if cached_response:
                if thinking_mode and cached_response.get('thinking'):
                    yield self._sse_payload({'type': 'thinking', 'content': cached_response['thinking']})
                assistant_content = cached_response['content']
                assistant_message = ChatMessage.objects.create(session=session, role='assistant', content=assistant_content)
                yield self._sse_payload({'type': 'replace', 'content': assistant_content})
                yield self._sse_payload({
                    'type': 'done', 'assistant_message': ChatMessageSerializer(assistant_message).data,
                    'usage': cached_response.get('usage'),
                    'tool_call': None, 'tool_result': None, 'tool_contract_status': 'cache_hit', 'tool_contract_error': None,
                })
                return

            payload = {
                'model': chat_config.model_name,
                'messages': model_messages,
                'stream': True,
                'stream_options': {'include_usage': True},
                'temperature': chat_config.temperature,
                'top_p': chat_config.top_p,
            }
            payload[chat_token_parameter(chat_config.model_name)] = chat_config.max_tokens
            try:
                upstream_response = requests.post(
                    build_openai_chat_url(chat_config),
                    headers={'Authorization': f'Bearer {chat_config.api_key}', 'Content-Type': 'application/json', 'Accept': 'text/event-stream'},
                    json=payload, timeout=(10, 300), stream=True,
                )
                upstream_response.raise_for_status()
            except requests.exceptions.RequestException as error:
                logger.error('Chat model request failed: %s', error, exc_info=True)
                yield self._sse_payload({'type': 'error', 'error': f'Chat 模型请求失败: {error}'})
                return

            assistant_content = ''
            thinking_content = ''
            usage = None
            try:
                for raw_line in upstream_response.iter_lines(decode_unicode=True):
                    if not raw_line or not str(raw_line).startswith('data:'):
                        continue
                    raw_payload = str(raw_line)[5:].strip()
                    if raw_payload == '[DONE]':
                        break
                    try:
                        chunk = json.loads(raw_payload)
                        choices = chunk.get('choices') or []
                        delta = choices[0].get('delta') or {} if choices else {}
                    except (AttributeError, TypeError, json.JSONDecodeError) as error:
                        logger.warning('Chat model SSE chunk parse failed: %s', error)
                        continue
                    usage = chunk.get('usage') or usage
                    reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
                    content = delta.get('content') or ''
                    if thinking_mode and reasoning:
                        thinking_content += reasoning
                        yield self._sse_payload({'type': 'thinking', 'content': reasoning})
                    if content:
                        assistant_content += content
                        yield self._sse_payload({'type': 'chunk', 'content': content})
            finally:
                upstream_response.close()

            assistant_content = sanitize_model_output(assistant_content, thinking_mode)
            model_tool_contract = parse_tool_call_from_model_output(assistant_content)
            model_tool_call = model_tool_contract.tool_call if model_tool_contract.matched else None
            tool_result = None
            if model_tool_call:
                tool_result = execute_tool_call(model_tool_call, request.user)
                assistant_content = format_tool_result_for_user(tool_result)
                yield self._sse_payload({'type': 'replace', 'content': assistant_content})
            else:
                cache.set(cache_key, {'content': assistant_content, 'thinking': thinking_content, 'usage': usage}, CHAT_CACHE_TTL_SECONDS)

            assistant_message = ChatMessage.objects.create(session=session, role='assistant', content=assistant_content)
            yield self._sse_payload({
                'type': 'done',
                'assistant_message': ChatMessageSerializer(assistant_message).data,
                'usage': usage,
                'tool_call': {'name': model_tool_call.name, 'args': model_tool_call.args} if model_tool_call else None,
                'tool_result': tool_result,
                'tool_contract_status': model_tool_contract.status if model_tool_call else None,
                'tool_contract_error': {
                    'code': model_tool_contract.error_code,
                    'message': model_tool_contract.error_message,
                } if model_tool_call and model_tool_contract.error_code else None,
            })

        return self._stream_response(model_stream())

    @staticmethod
    def _stream_response(event_stream):
        response = StreamingHttpResponse(event_stream, content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


def assistant_view(request):
    return render(request, 'assistant/assistant.html')