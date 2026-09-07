from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any, Protocol

from apps.ai_testing.execution.capabilities import allowed_browser_actions, validate_browser_action


BrowserActionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
BrowserObservationHandler = Callable[[], Awaitable[dict[str, Any]]]
BrowserCapabilitiesProvider = Callable[[], list[str]]
MCP_PROTOCOL_VERSION = '2025-06-18'


class MCPTransport(Protocol):
    async def send(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Send one MCP JSON-RPC message and return its response, if any."""


class BrowserMCPToolAdapter:
    """MCP-compatible tool registry for server-owned browser execution."""

    def __init__(
        self,
        allowed_capabilities: list[str] | BrowserCapabilitiesProvider,
        action_handler: BrowserActionHandler | None = None,
        observation_handler: BrowserObservationHandler | None = None,
    ) -> None:
        self._allowed_capabilities = allowed_capabilities
        self._action_handler = action_handler
        self._observation_handler = observation_handler

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        if self._observation_handler is not None:
            tools.append({
                'name': 'browser.observe',
                'description': 'Capture the current server-owned Playwright page observation.',
                'inputSchema': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {},
                },
            })
        if self._action_handler is not None:
            tools.append({
                'name': 'browser.act',
                'description': 'Execute one validated browser instruction against the current Playwright page.',
                'inputSchema': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['instruction'],
                    'properties': {
                        'instruction': {
                            'type': 'object',
                            'required': ['action'],
                            'properties': {
                                'action': {
                                    'type': 'string',
                                    'enum': allowed_browser_actions(self._current_capabilities()),
                                },
                            },
                        },
                    },
                },
            })
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == 'browser.observe' and self._observation_handler is not None:
            if arguments:
                raise ValueError('browser.observe does not accept arguments.')
            observation = await self._observation_handler()
            return {
                'content': [{'type': 'text', 'text': 'Page observation captured.'}],
                'structuredContent': observation,
                'isError': False,
            }
        if name != 'browser.act' or self._action_handler is None:
            raise ValueError(f'Unknown MCP tool: {name}.')
        instruction = arguments.get('instruction') if isinstance(arguments, dict) else None
        if not isinstance(instruction, dict):
            raise ValueError('browser.act requires an instruction object.')
        action = str(instruction.get('action') or '').strip()
        validate_browser_action(action, self._current_capabilities())
        if instruction.get('loc'):
            raise ValueError('browser.act does not accept coordinate locators.')

        output = await self._action_handler(deepcopy(instruction))
        return {
            'content': [{'type': 'text', 'text': 'Browser instruction completed.'}],
            'structuredContent': output or {},
            'isError': False,
        }

    def _current_capabilities(self) -> list[str]:
        capabilities = self._allowed_capabilities() if callable(self._allowed_capabilities) else self._allowed_capabilities
        if not isinstance(capabilities, list):
            raise ValueError('Browser capability provider must return a list.')
        return list(capabilities)


class MCPJsonRpcDispatcher:
    """Dispatch MCP JSON-RPC requests to a session-bound browser tool registry."""

    def __init__(self, tools: BrowserMCPToolAdapter) -> None:
        self._tools = tools
        self._initialize_requested = False
        self._initialized = False

    async def dispatch(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get('id')
        if message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
            return self._error(request_id, -32600, 'Invalid Request')

        method = message['method']
        params = message.get('params', {})
        if method == 'notifications/initialized':
            if self._initialize_requested:
                self._initialized = True
            return None
        if 'id' not in message:
            return None
        if not isinstance(params, dict):
            return self._error(request_id, -32602, 'Invalid params')

        try:
            if method == 'initialize':
                self._initialize_requested = True
                result = {
                    'protocolVersion': MCP_PROTOCOL_VERSION,
                    'capabilities': {'tools': {'listChanged': False}},
                    'serverInfo': {'name': 'testhub-browser', 'version': '1.0'},
                }
            elif method == 'tools/list':
                if not self._initialized:
                    return self._error(request_id, -32002, 'Server not initialized')
                result = {'tools': self._tools.list_tools()}
            elif method == 'tools/call':
                if not self._initialized:
                    return self._error(request_id, -32002, 'Server not initialized')
                name = params.get('name')
                arguments = params.get('arguments', {})
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    return self._error(request_id, -32602, 'Invalid params')
                result = await self._tools.call_tool(name, arguments)
            else:
                return self._error(request_id, -32601, 'Method not found')
        except ValueError as exc:
            return self._error(request_id, -32602, str(exc))

        return {'jsonrpc': '2.0', 'id': request_id, 'result': result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            'jsonrpc': '2.0',
            'id': request_id,
            'error': {'code': code, 'message': message},
        }


class MCPInProcessTransport:
    """Transport MCP messages to a dispatcher in the current process."""

    def __init__(self, dispatcher: MCPJsonRpcDispatcher) -> None:
        self._dispatcher = dispatcher

    async def send(self, message: dict[str, Any]) -> dict[str, Any] | None:
        return await self._dispatcher.dispatch(deepcopy(message))


class MCPInProcessClient:
    """MCP client using an in-process JSON-RPC dispatcher as its transport."""

    def __init__(self, transport: MCPTransport) -> None:
        self._transport = transport
        self._next_request_id = 1
        self._initialized = False

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_initialized()
        return await self._request('tools/call', {'name': name, 'arguments': arguments})

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        await self._request('initialize', {
            'protocolVersion': MCP_PROTOCOL_VERSION,
            'capabilities': {},
            'clientInfo': {'name': 'testhub-runner', 'version': '1.0'},
        })
        await self._transport.send({
            'jsonrpc': '2.0',
            'method': 'notifications/initialized',
        })
        self._initialized = True

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_request_id
        self._next_request_id += 1
        response = await self._transport.send({
            'jsonrpc': '2.0',
            'id': request_id,
            'method': method,
            'params': params,
        })
        if response is None:
            raise RuntimeError(f'MCP request {method} returned no response.')
        error = response.get('error')
        if isinstance(error, dict):
            raise ValueError(str(error.get('message') or 'MCP request failed.'))
        result = response.get('result')
        if not isinstance(result, dict):
            raise RuntimeError(f'MCP request {method} returned an invalid result.')
        return result