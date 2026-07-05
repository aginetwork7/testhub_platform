from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render
from django.http import StreamingHttpResponse
import requests
import json
import logging
import re
from .models import AssistantSession, AssistantMessage, ChatMessage, DifyConfig
from .serializers import (
    AssistantSessionSerializer, 
    AssistantSessionCreateSerializer,
    AssistantMessageSerializer,
    ChatMessageSerializer
)
from .tools import (
    execute_tool_call,
    format_tool_result_for_user,
    get_tool_contract_prompt,
    parse_tool_call_from_request_contract,
    parse_tool_call_from_model_output,
)


logger = logging.getLogger(__name__)


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


def build_dify_inputs(thinking_mode):
    return {
        'thinking_mode': bool(thinking_mode),
    }


def sanitize_model_output(content, thinking_mode):
    text = str(content or '')
    if thinking_mode:
        return text

    # Strip common reasoning blocks used by thinking-capable models.
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # Handle streaming/incomplete tail where </think> may not have arrived yet.
    text = re.sub(r'<think>.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<thinking>.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = text.replace('</think>', '')
    text = text.replace('</thinking>', '')

    # Keep only final-answer part for common reasoning templates.
    markers = [
        r'final\s*answer\s*[:：]',
        r'最终答案\s*[:：]',
        r'answer\s*[:：]',
        r'结论\s*[:：]',
    ]
    for marker in markers:
        matched = re.search(marker, text, flags=re.IGNORECASE)
        if matched:
            text = text[matched.end():]
            break

    # Remove common reasoning prefaces produced by thinking-enabled models.
    text = re.sub(r"(?is)^\s*here'?s\s+a\s+thinking\s+process\s*:\s*", '', text)

    paragraphs = [segment.strip() for segment in re.split(r'\n\s*\n+', text) if segment.strip()]
    target = paragraphs[-1] if paragraphs else text.strip()

    lines = [line.strip() for line in target.splitlines() if line.strip()]
    cleaned_lines = []
    for line in lines:
        if re.match(r'^[-*]\s+', line):
            continue
        if re.match(r'^\d+[\.)]\s+', line):
            continue
        if re.match(r'^\[.*\]$', line):
            continue
        cleaned_lines.append(line)

    answer = cleaned_lines[-1] if cleaned_lines else (lines[-1] if lines else target)
    answer = re.sub(r'^(final\s*answer|answer|最终答案|结论)\s*[:：]\s*', '', answer, flags=re.IGNORECASE)
    answer = answer.strip().strip('"').strip("'").strip()

    return answer


def build_user_query(message, thinking_mode):
    query = str(message or '').strip()
    tool_contract_prompt = get_tool_contract_prompt()
    if thinking_mode:
        return f"{tool_contract_prompt}\n\n用户问题：{query}"
    return (
        f'{tool_contract_prompt}\n\n'
        '请直接给出最终答案，不要输出思考过程、推理过程、Chain of Thought、'
        '<think> 标签或中间分析。\n\n'
        f'用户问题：{query}'
    )


def safe_json_loads(value):
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)

    try:
        return json.loads(text)
    except Exception:
        return None


def parse_structured_answer(value):
    payload = value
    if isinstance(value, str):
        payload = safe_json_loads(value)

    if not isinstance(payload, dict):
        return {
            'matched': False,
            'text': '',
            'reasoning_content': '',
            'usage': None,
        }

    base = payload
    if isinstance(payload.get('data'), dict):
        base = payload.get('data')

    text = str(
        base.get('text')
        or base.get('answer')
        or base.get('content')
        or ''
    )
    reasoning_content = str(
        base.get('reasoning_content')
        or base.get('thinking')
        or base.get('reasoning')
        or ''
    )
    usage = base.get('usage') if isinstance(base.get('usage'), dict) else None

    matched = any(key in base for key in ['text', 'reasoning_content', 'usage'])
    return {
        'matched': matched,
        'text': text,
        'reasoning_content': reasoning_content,
        'usage': usage,
    }


def _to_int(value):
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        return int(value)
    except Exception:
        return None


def normalize_usage(usage):
    if not isinstance(usage, dict):
        return None

    prompt_tokens = _to_int(
        usage.get('prompt_tokens')
        or usage.get('input_tokens')
        or usage.get('prompt_token_count')
    )
    completion_tokens = _to_int(
        usage.get('completion_tokens')
        or usage.get('output_tokens')
        or usage.get('answer_tokens')
        or usage.get('completion_token_count')
    )
    total_tokens = _to_int(
        usage.get('total_tokens')
        or usage.get('total_token_count')
        or usage.get('tokens')
    )

    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        return None

    return {
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': total_tokens,
    }


def extract_usage(payload):
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get('usage'),
        payload.get('token_usage'),
        payload.get('metadata', {}).get('usage') if isinstance(payload.get('metadata'), dict) else None,
        payload.get('data', {}).get('usage') if isinstance(payload.get('data'), dict) else None,
        payload.get('result', {}).get('usage') if isinstance(payload.get('result'), dict) else None,
    ]

    for candidate in candidates:
        normalized = normalize_usage(candidate)
        if normalized:
            return normalized
    return None


class AssistantSessionViewSet(viewsets.ModelViewSet):
    """智能助手会话视图集"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AssistantSessionCreateSerializer
        return AssistantSessionSerializer
    
    def get_queryset(self):
        return AssistantSession.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def add_message(self, request, pk=None):
        """添加消息到会话"""
        session = self.get_object()
        serializer = AssistantMessageSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save(session=session)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """获取会话的聊天消息"""
        session = self.get_object()
        messages = session.chat_messages.all()
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)


class ChatViewSet(viewsets.ViewSet):
    """聊天功能ViewSet"""
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _sse_payload(data):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def _extract_text_by_paths(event_payload, paths):
        if not isinstance(event_payload, dict):
            return ''

        for path in paths:
            current = event_payload
            matched = True
            for key in path:
                if not isinstance(current, dict) or key not in current:
                    matched = False
                    break
                current = current.get(key)

            if not matched or current is None:
                continue

            if isinstance(current, str):
                return current
            return str(current)

        return ''

    @classmethod
    def _extract_stream_chunk(cls, event_payload):
        if not isinstance(event_payload, dict):
            return ''
        return cls._extract_text_by_paths(
            event_payload,
            [
                ('answer',),
                ('message',),
                ('text',),
                ('delta',),
                ('content',),
                ('data', 'answer'),
                ('data', 'message'),
                ('data', 'text'),
                ('data', 'delta'),
                ('data', 'content'),
                ('output', 'answer'),
                ('result', 'answer'),
            ],
        )

    @classmethod
    def _extract_stream_thinking(cls, event_payload):
        if not isinstance(event_payload, dict):
            return ''
        return cls._extract_text_by_paths(
            event_payload,
            [
                ('thought',),
                ('thinking',),
                ('reasoning',),
                ('reasoning_content',),
                ('data', 'thought'),
                ('data', 'thinking'),
                ('data', 'reasoning'),
                ('data', 'reasoning_content'),
            ],
        )
    
    @action(detail=False, methods=['post'])
    def send_message(self, request):
        """发送消息到Dify API"""
        session_id = request.data.get('session_id')
        message = request.data.get('message')
        tool_call_payload = request.data.get('tool_call')
        thinking_mode = parse_request_bool(request.data.get('thinking_mode'), default=True)
        
        if not session_id or not message:
            return Response(
                {'error': 'session_id和message都是必填项'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 获取会话
        try:
            session = AssistantSession.objects.get(
                session_id=session_id,
                user=request.user
            )
        except AssistantSession.DoesNotExist:
            return Response(
                {'error': '会话不存在'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 获取Dify配置
        dify_config = DifyConfig.get_active_config()
        if not dify_config:
            return Response(
                {'error': '未配置Dify API，请先在配置中心配置'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 保存用户消息
        user_message = ChatMessage.objects.create(
            session=session,
            role='user',
            content=message,
            conversation_id=session.conversation_id
        )

        request_tool_contract = parse_tool_call_from_request_contract(
            str(message or ''),
            tool_call_payload=tool_call_payload,
        )
        tool_call = request_tool_contract.tool_call if request_tool_contract.matched else None
        if tool_call is not None:
            tool_result = execute_tool_call(tool_call, request.user)
            assistant_content = format_tool_result_for_user(tool_result)
            assistant_message = ChatMessage.objects.create(
                session=session,
                role='assistant',
                content=assistant_content,
                conversation_id=session.conversation_id,
                message_id=None,
            )
            return Response({
                'user_message': ChatMessageSerializer(user_message).data,
                'assistant_message': ChatMessageSerializer(assistant_message).data,
                'conversation_id': session.conversation_id,
                'usage': None,
                'tool_call': {
                    'name': tool_call.name,
                    'args': tool_call.args,
                },
                'tool_result': tool_result,
                'tool_contract_status': request_tool_contract.status,
                'tool_contract_error': {
                    'code': request_tool_contract.error_code,
                    'message': request_tool_contract.error_message,
                } if request_tool_contract.error_code else None,
            })
        
        try:
            # 调用Dify API
            headers = {
                'Authorization': f'Bearer {dify_config.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'inputs': build_dify_inputs(thinking_mode),
                'query': build_user_query(message, thinking_mode),
                'user': str(request.user.id),
                'response_mode': 'blocking'
            }
            
            # 如果有conversation_id，添加到请求中以保持会话连续性
            if session.conversation_id:
                payload['conversation_id'] = session.conversation_id
            
            # 去除URL末尾的斜杠
            api_url = dify_config.api_url.rstrip('/')
            
            response = requests.post(
                f'{api_url}/chat-messages',
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # 更新会话的conversation_id
                if 'conversation_id' in data and not session.conversation_id:
                    session.conversation_id = data['conversation_id']
                    session.save()
                
                # 保存助手回复
                structured = parse_structured_answer(data.get('answer', ''))
                raw_text = structured['text'] if structured.get('matched') else data.get('answer', '')
                model_tool_contract = parse_tool_call_from_model_output(raw_text)
                model_tool_call = model_tool_contract.tool_call if model_tool_contract.matched else None
                tool_result = None
                if model_tool_call is not None:
                    tool_result = execute_tool_call(model_tool_call, request.user)
                    assistant_content = format_tool_result_for_user(tool_result)
                else:
                    assistant_content = sanitize_model_output(raw_text, thinking_mode)
                usage = normalize_usage(structured.get('usage')) or extract_usage(data)
                assistant_message = ChatMessage.objects.create(
                    session=session,
                    role='assistant',
                    content=assistant_content,
                    conversation_id=data.get('conversation_id'),
                    message_id=data.get('message_id')
                )
                
                return Response({
                    'user_message': ChatMessageSerializer(user_message).data,
                    'assistant_message': ChatMessageSerializer(assistant_message).data,
                    'conversation_id': data.get('conversation_id'),
                    'usage': usage,
                    'tool_call': {
                        'name': model_tool_call.name,
                        'args': model_tool_call.args,
                    } if model_tool_call is not None else None,
                    'tool_result': tool_result,
                    'tool_contract_status': model_tool_contract.status,
                    'tool_contract_error': {
                        'code': model_tool_contract.error_code,
                        'message': model_tool_contract.error_message,
                    } if model_tool_contract.error_code else None,
                })
            else:
                return Response({
                    'error': f'Dify API错误: {response.status_code}',
                    'detail': response.text
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except requests.exceptions.Timeout:
            return Response({
                'error': 'API请求超时'
            }, status=status.HTTP_408_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return Response({
                'error': f'API请求失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def send_message_stream(self, request):
        """发送消息到Dify API（流式返回）"""
        session_id = request.data.get('session_id')
        message = request.data.get('message')
        tool_call_payload = request.data.get('tool_call')
        thinking_mode = parse_request_bool(request.data.get('thinking_mode'), default=True)

        if not session_id or not message:
            return Response(
                {'error': 'session_id和message都是必填项'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            session = AssistantSession.objects.get(
                session_id=session_id,
                user=request.user
            )
        except AssistantSession.DoesNotExist:
            return Response(
                {'error': '会话不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        dify_config = DifyConfig.get_active_config()
        if not dify_config:
            return Response(
                {'error': '未配置Dify API，请先在配置中心配置'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_message = ChatMessage.objects.create(
            session=session,
            role='user',
            content=message,
            conversation_id=session.conversation_id
        )

        request_tool_contract = parse_tool_call_from_request_contract(
            str(message or ''),
            tool_call_payload=tool_call_payload,
        )
        tool_call = request_tool_contract.tool_call if request_tool_contract.matched else None
        if tool_call is not None:
            tool_result = execute_tool_call(tool_call, request.user)
            assistant_content = format_tool_result_for_user(tool_result)

            def local_tool_stream():
                yield self._sse_payload({
                    'type': 'start',
                    'user_message': ChatMessageSerializer(user_message).data,
                })
                yield self._sse_payload({'type': 'replace', 'content': assistant_content})

                assistant_message = ChatMessage.objects.create(
                    session=session,
                    role='assistant',
                    content=assistant_content,
                    conversation_id=session.conversation_id,
                    message_id=None,
                )
                yield self._sse_payload({
                    'type': 'done',
                    'assistant_message': ChatMessageSerializer(assistant_message).data,
                    'conversation_id': session.conversation_id,
                    'usage': None,
                    'tool_call': {
                        'name': tool_call.name,
                        'args': tool_call.args,
                    },
                    'tool_result': tool_result,
                    'tool_contract_status': request_tool_contract.status,
                    'tool_contract_error': {
                        'code': request_tool_contract.error_code,
                        'message': request_tool_contract.error_message,
                    } if request_tool_contract.error_code else None,
                })

            stream_response = StreamingHttpResponse(local_tool_stream(), content_type='text/event-stream')
            stream_response['Cache-Control'] = 'no-cache'
            stream_response['X-Accel-Buffering'] = 'no'
            return stream_response

        headers = {
            'Authorization': f'Bearer {dify_config.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
        }

        payload = {
            'inputs': build_dify_inputs(thinking_mode),
            'query': build_user_query(message, thinking_mode),
            'user': str(request.user.id),
            'response_mode': 'streaming'
        }
        if session.conversation_id:
            payload['conversation_id'] = session.conversation_id

        api_url = dify_config.api_url.rstrip('/')

        try:
            upstream_response = requests.post(
                f'{api_url}/chat-messages',
                headers=headers,
                json=payload,
                timeout=(10, 300),
                stream=True,
            )
        except requests.exceptions.Timeout:
            return Response({'error': 'API请求超时'}, status=status.HTTP_408_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            return Response({'error': f'API请求失败: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if upstream_response.status_code != 200:
            detail = upstream_response.text
            upstream_response.close()
            return Response(
                {
                    'error': f'Dify API错误: {upstream_response.status_code}',
                    'detail': detail,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        def event_stream():
            assistant_content = ''
            display_content = ''
            conversation_id = session.conversation_id
            message_id = None
            usage = None

            def process_event_payload(event_payload):
                nonlocal assistant_content, display_content, conversation_id, message_id, usage

                event_type = str(event_payload.get('event') or '').strip()
                usage = extract_usage(event_payload) or usage

                if event_type in {'message', 'agent_message', 'text_chunk'}:
                    chunk = self._extract_stream_chunk(event_payload)
                    structured = parse_structured_answer(chunk)
                    if structured.get('matched'):
                        usage = normalize_usage(structured.get('usage')) or usage
                        chunk = structured.get('text')
                        if not chunk and thinking_mode and structured.get('reasoning_content'):
                            return {'type': 'thinking', 'content': structured.get('reasoning_content')}

                    if chunk:
                        assistant_content += chunk
                        sanitized = sanitize_model_output(assistant_content, thinking_mode)

                        if sanitized.startswith(display_content):
                            delta = sanitized[len(display_content):]
                            display_content = sanitized
                            if delta:
                                return {'type': 'chunk', 'content': delta}
                            return None

                        display_content = sanitized
                        return {'type': 'replace', 'content': sanitized}

                    conversation_id = event_payload.get('conversation_id') or conversation_id
                    message_id = event_payload.get('message_id') or message_id
                    return None

                if event_type in {'message_replace', 'agent_message_replace'}:
                    replaced_text = self._extract_stream_chunk(event_payload)
                    structured = parse_structured_answer(replaced_text)
                    if structured.get('matched'):
                        usage = normalize_usage(structured.get('usage')) or usage
                        replaced_text = structured.get('text')
                        if not replaced_text and thinking_mode and structured.get('reasoning_content'):
                            return {'type': 'thinking', 'content': structured.get('reasoning_content')}

                    if replaced_text:
                        assistant_content = replaced_text
                        display_content = sanitize_model_output(assistant_content, thinking_mode)
                        conversation_id = event_payload.get('conversation_id') or conversation_id
                        message_id = event_payload.get('message_id') or message_id
                        return {'type': 'replace', 'content': display_content}
                    return None

                if event_type in {'agent_thought', 'thought'}:
                    if not thinking_mode:
                        return None
                    thinking_chunk = self._extract_stream_thinking(event_payload)
                    if thinking_chunk:
                        return {'type': 'thinking', 'content': thinking_chunk}
                    return None

                if event_type in {'message_end', 'agent_message_end'}:
                    conversation_id = event_payload.get('conversation_id') or conversation_id
                    message_id = event_payload.get('message_id') or message_id
                    usage = extract_usage(event_payload) or usage

                    if not assistant_content:
                        fallback_text = self._extract_stream_chunk(event_payload)
                        if fallback_text:
                            assistant_content = fallback_text
                            display_content = sanitize_model_output(assistant_content, thinking_mode)
                            return {'type': 'replace', 'content': display_content}
                    return None

                if event_type == 'error':
                    error_message = str(event_payload.get('message') or 'Dify stream error')
                    return {'type': 'error', 'error': error_message}

                return None

            yield self._sse_payload({
                'type': 'start',
                'user_message': ChatMessageSerializer(user_message).data,
            })

            try:
                current_event_name = ''
                data_lines = []

                def flush_sse_event():
                    nonlocal current_event_name, data_lines
                    if not data_lines:
                        current_event_name = ''
                        return None

                    raw_payload = '\n'.join(data_lines).strip()
                    current_name = current_event_name
                    current_event_name = ''
                    data_lines = []

                    if not raw_payload:
                        return None
                    if raw_payload == '[DONE]':
                        return 'done_sentinel'

                    try:
                        event_payload = json.loads(raw_payload)
                    except json.JSONDecodeError:
                        logger.warning('Dify stream payload parse failed: %s', raw_payload)
                        return None

                    if current_name and isinstance(event_payload, dict) and not event_payload.get('event'):
                        event_payload['event'] = current_name

                    if not isinstance(event_payload, dict):
                        return None

                    processed = process_event_payload(event_payload)
                    return processed

                for raw_line in upstream_response.iter_lines(decode_unicode=True):
                    if raw_line is None:
                        continue

                    line = str(raw_line)
                    if line == '':
                        processed = flush_sse_event()
                        if processed == 'done_sentinel':
                            break
                        if isinstance(processed, dict):
                            yield self._sse_payload(processed)
                            if processed.get('type') == 'error':
                                return
                        continue

                    if line.startswith('event:'):
                        current_event_name = line[6:].strip()
                        continue
                    if line.startswith('data:'):
                        data_lines.append(line[5:].lstrip())
                        continue

                processed = flush_sse_event()
                if processed == 'done_sentinel':
                    pass
                elif isinstance(processed, dict):
                    yield self._sse_payload(processed)
                    if processed.get('type') == 'error':
                        return

                model_tool_contract = parse_tool_call_from_model_output(assistant_content)
                model_tool_call = model_tool_contract.tool_call if model_tool_contract.matched else None
                tool_result = None
                if model_tool_call is not None:
                    tool_result = execute_tool_call(model_tool_call, request.user)
                    assistant_content = format_tool_result_for_user(tool_result)
                    display_content = assistant_content
                    yield self._sse_payload({'type': 'replace', 'content': display_content})
                else:
                    assistant_content = sanitize_model_output(assistant_content, thinking_mode)

                if conversation_id and session.conversation_id != conversation_id:
                    session.conversation_id = conversation_id
                    session.save(update_fields=['conversation_id', 'updated_at'])

                assistant_message = ChatMessage.objects.create(
                    session=session,
                    role='assistant',
                    content=assistant_content,
                    conversation_id=conversation_id,
                    message_id=message_id
                )

                yield self._sse_payload({
                    'type': 'done',
                    'assistant_message': ChatMessageSerializer(assistant_message).data,
                    'conversation_id': conversation_id,
                    'usage': usage,
                    'tool_call': {
                        'name': model_tool_call.name,
                        'args': model_tool_call.args,
                    } if model_tool_call is not None else None,
                    'tool_result': tool_result,
                    'tool_contract_status': model_tool_contract.status,
                    'tool_contract_error': {
                        'code': model_tool_contract.error_code,
                        'message': model_tool_contract.error_message,
                    } if model_tool_contract.error_code else None,
                })
            except Exception as exc:
                logger.error('send_message_stream failed: %s', exc, exc_info=True)
                yield self._sse_payload({'type': 'error', 'error': f'流式响应失败: {exc}'})
            finally:
                upstream_response.close()

        stream_response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        stream_response['Cache-Control'] = 'no-cache'
        stream_response['X-Accel-Buffering'] = 'no'
        return stream_response


def assistant_view(request):
    """智能助手页面视图 - 用于iframe内嵌"""
    return render(request, 'assistant/assistant.html')
