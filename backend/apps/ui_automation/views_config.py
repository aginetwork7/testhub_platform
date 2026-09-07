from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import subprocess
import platform
import os
import logging
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse, urlunparse
import requests

logger = logging.getLogger(__name__)


class AIModelParametersSerializer(serializers.Serializer):
    max_tokens = serializers.IntegerField(min_value=1, required=False)
    temperature = serializers.FloatField(min_value=0, max_value=2, required=False)
    top_p = serializers.FloatField(min_value=0, max_value=1, required=False)

class EnvironmentConfigViewSet(viewsets.ViewSet):
    """
    UI自动化环境配置视图集
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def check_environment(self, request):
        """
        检测环境状态 (系统浏览器和Playwright浏览器)
        """

        # 1. 检测系统浏览器 (Selenium常用)
        system_browsers_list = ['chrome', 'firefox', 'edge'] # Safari not on Windows usually
        if platform.system() == 'Darwin':
             system_browsers_list.append('safari')
             
        system_results = []

        is_windows = platform.system() == 'Windows'

        for browser in system_browsers_list:
            installed = False
            version = None
            install_cmd = ""
            
            if browser == 'chrome':
                if is_windows:
                    paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
                    ]
                    for p in paths:
                        if os.path.exists(p):
                            installed = True
                            break
                    install_cmd = "请下载 Chrome 安装包安装"
                elif platform.system() == 'Darwin':  # macOS
                    if os.path.exists('/Applications/Google Chrome.app'):
                        installed = True
                    install_cmd = "brew install --cask google-chrome"
                else:  # Linux
                    chrome_paths = [
                        '/usr/bin/google-chrome',
                        '/usr/bin/google-chrome-stable',
                        '/usr/bin/chromium-browser',
                        '/usr/bin/chromium',
                        '/opt/google/chrome/google-chrome',
                        '/snap/bin/chromium'
                    ]
                    for path in chrome_paths:
                        if os.path.exists(path):
                            installed = True
                            break
                    install_cmd = "sudo dnf install chromium 或 sudo dnf install google-chrome-stable"
                    
            elif browser == 'firefox':
                if is_windows:
                    paths = [
                        r"C:\Program Files\Mozilla Firefox\firefox.exe",
                        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
                    ]
                    for p in paths:
                        if os.path.exists(p):
                            installed = True
                            break
                    install_cmd = "请下载 Firefox 安装包安装"
                elif platform.system() == 'Darwin':  # macOS
                    if os.path.exists('/Applications/Firefox.app'):
                        installed = True
                    install_cmd = "brew install --cask firefox"
                else:  # Linux
                    firefox_paths = [
                        '/usr/bin/firefox',
                        '/usr/bin/firefox-esr'
                    ]
                    for path in firefox_paths:
                        if os.path.exists(path):
                            installed = True
                            break
                    install_cmd = "sudo dnf install firefox"
                    
            elif browser == 'safari':
                if not is_windows and os.path.exists('/Applications/Safari.app'):
                    installed = True
                install_cmd = "系统自带"
                
            elif browser == 'edge':
                if is_windows:
                    paths = [
                         r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
                    ]
                    for p in paths:
                        if os.path.exists(p):
                            installed = True
                            break
                    install_cmd = "请下载 Edge 安装包安装"
                elif platform.system() == 'Darwin':  # macOS
                    if os.path.exists('/Applications/Microsoft Edge.app'):
                        installed = True
                    install_cmd = "brew install --cask microsoft-edge"
                else:  # Linux
                    edge_paths = [
                        '/usr/bin/microsoft-edge',
                        '/usr/bin/microsoft-edge-stable',
                        '/opt/microsoft/msedge/msedge'
                    ]
                    for path in edge_paths:
                        if os.path.exists(path):
                            installed = True
                            break
                    install_cmd = "从微软官网下载 Edge Linux 版本安装包"

            system_results.append({
                'name': browser,
                'installed': installed,
                'version': version, # Version check omitted for simplicity/performance
                'install_cmd': install_cmd
            })

        # 2. 检测Playwright浏览器
        playwright_browsers_list = ['chromium', 'firefox', 'webkit']
        playwright_results = []
        
        # Playwright 缓存路径
        if is_windows:
            playwright_cache_dir = os.path.join(os.environ.get('LOCALAPPDATA'), 'ms-playwright')
        elif platform.system() == 'Darwin':  # macOS
            playwright_cache_dir = os.path.expanduser('~/Library/Caches/ms-playwright')
        else:  # Linux
            playwright_cache_dir = os.path.expanduser('~/.cache/ms-playwright')
        
        # 调试信息：打印缓存路径
        print(f"Playwright cache dir: {playwright_cache_dir}")

        for browser in playwright_browsers_list:
            installed = False
            version = None
            install_cmd = f"playwright install {browser}"
            
            # 检查缓存目录中是否有对应的浏览器文件夹
            if os.path.exists(playwright_cache_dir):
                for dirname in os.listdir(playwright_cache_dir):
                    # 匹配规则: chromium-123456, firefox-1234, webkit-1234
                    # 注意: 有时候是 chromium-vxxxx
                    if dirname.startswith(browser + '-'):
                        installed = True
                        version = dirname.split('-')[-1]
                        break
            
            playwright_results.append({
                'name': browser,
                'installed': installed,
                'version': version,
                'install_cmd': install_cmd
            })

        return Response({
            'os': platform.system(),
            'system_browsers': system_results,
            'playwright_browsers': playwright_results
        })

    @action(detail=False, methods=['post'])
    def install_driver(self, request):
        """
        安装浏览器驱动
        """
        browser = request.data.get('browser')
        if not browser:
            return Response({'error': 'Browser name is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 使用当前 Python 环境执行模块安装命令
            import sys
            subprocess.run([sys.executable, '-m', 'playwright', 'install', browser], check=True)
            return Response({'message': f'Successfully installed driver for {browser}'})
        except subprocess.CalledProcessError as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import requests
from apps.ai_testing.models import AITestModelConfig, AITestPromptConfig

class AIIntelligentModeConfigViewSet(viewsets.ViewSet):
    """
    AI智能模式配置视图集 (Browser-use) - 使用ModelViewSet支持标准CRUD
    """
    permission_classes = [IsAuthenticated]
    BROWSER_USE_ROLES = [
        'planner_text', 'planner_vision', 'executor_text', 'executor_vision',
        'hermes_agent',
    ]
    queryset = AITestModelConfig.objects.filter(role__in=BROWSER_USE_ROLES)

    @staticmethod
    def _validated_model_parameters(data: Mapping[str, Any]) -> dict[str, Any]:
        serializer = AIModelParametersSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @staticmethod
    def _running_in_docker():
        return os.path.exists('/.dockerenv') or os.getenv('IN_DOCKER', '').lower() == 'true'

    def _resolve_base_url(self, provider, base_url):
        normalized = str(base_url or '').strip()
        if normalized:
            normalized = normalized.rstrip('/')
            if normalized.endswith('/chat/completions'):
                normalized = normalized[:-len('/chat/completions')]

            if provider in {'gemini', 'google_gemini'}:
                return normalized

            parsed = urlparse(normalized)
            hostname = parsed.hostname
            if self._running_in_docker() and hostname in {'127.0.0.1', 'localhost'}:
                netloc = parsed.netloc.replace(hostname, 'host.docker.internal')
                parsed = parsed._replace(netloc=netloc)
                normalized = urlunparse(parsed)

            if not normalized.endswith('/v1'):
                normalized += '/v1'
            return normalized

        if provider == 'openai':
            return 'https://api.openai.com/v1'
        if provider == 'siliconflow':
            return 'https://api.siliconflow.cn/v1'
        if provider == 'deepseek':
            return 'https://api.deepseek.com'
        if provider == 'anthropic':
            return 'https://api.anthropic.com'
        if provider in {'gemini', 'google_gemini'}:
            return 'https://generativelanguage.googleapis.com/v1beta/openai'
        if provider == 'other':
            return ''
        return ''

    def _build_auth_key_url(self, normalized_base_url):
        parsed = urlparse(str(normalized_base_url or '').strip())
        if not parsed.scheme or not parsed.netloc:
            return ''
        return urlunparse((parsed.scheme, parsed.netloc, '/api/auth/key', '', '', ''))

    def _read_api_key_file(self):
        file_path = str(os.getenv('HERMES_API_KEY_FILE') or os.getenv('API_KEY_FILE') or '').strip()
        if not file_path:
            return ''

        try:
            return Path(file_path).read_text(encoding='utf-8').strip()
        except OSError as error:
            logger.warning(f"AI智能模式 - 读取 Hermes API key 文件失败: {error}")
            return ''

    def _resolve_api_key(self, role, base_url, api_key):
        explicit_api_key = str(api_key or '').strip()
        if role != 'hermes_agent' and explicit_api_key:
            return explicit_api_key

        if explicit_api_key:
            return explicit_api_key

        file_api_key = self._read_api_key_file()
        if file_api_key:
            return file_api_key

        auth_key_url = self._build_auth_key_url(base_url)
        if auth_key_url:
            try:
                response = requests.get(auth_key_url, timeout=(10, 30))
                response.raise_for_status()
                payload = response.json()
                dynamic_api_key = str(payload.get('api_key', '') or '').strip()
                if dynamic_api_key:
                    return dynamic_api_key
            except (requests.RequestException, ValueError) as error:
                logger.warning(f"AI智能模式 - 获取 Hermes API key 失败: {error}")

        return explicit_api_key

    def _build_test_payload(
        self,
        role: str,
        model_name: str,
        max_tokens: int = 120,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> dict[str, Any]:
        model_name_lower = str(model_name or '').lower()
        is_reasoning_model = model_name_lower.startswith(('gpt-5', 'o1', 'o3', 'o4'))
        if role == 'hermes_agent':
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            'You are Hermes. Return only compact JSON with keys '
                            'success, summary, logs.'
                        )
                    },
                    {
                        "role": "user",
                        "content": '请返回一个Hermes连接自检结果。'
                    }
                ]
            }
        else:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Hi"}],
            }

        token_parameter = 'max_completion_tokens' if is_reasoning_model else 'max_tokens'
        payload[token_parameter] = max_tokens
        if not is_reasoning_model:
            payload['temperature'] = 1.0 if 'kimi' in model_name_lower else temperature
            payload['top_p'] = top_p
        return payload

    def _extract_test_message(self, role, response):
        try:
            response_json = response.json()
        except ValueError:
            return '连接成功，但响应不是JSON格式。'

        if role != 'hermes_agent':
            return '连接成功'

        content = (
            response_json.get('choices', [{}])[0]
            .get('message', {})
            .get('content', '')
        )

        if not content:
            return 'Hermes 连接成功，但未返回可读内容。'

        normalized = content.strip()
        if normalized.startswith('```'):
            normalized = normalized.strip('`')
            if normalized.startswith('json'):
                normalized = normalized[4:].strip()

        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            return f'Hermes 连接成功，原始响应: {content[:200]}'

        summary = parsed.get('summary') or parsed.get('message') or 'Hermes 连接成功'
        logs = parsed.get('logs') or []
        if isinstance(logs, list) and logs:
            return f'{summary} 首条日志: {logs[0]}'
        return summary

    def list(self, request):
        """
        获取所有AI智能模式配置列表
        """
        configs = self.queryset.order_by('-created_at')
        serializer_data = [{
            'id': config.id,
            'name': config.name,
            'model_type': config.model_type,
            'role': config.role,
            'model_name': config.model_name,
            'base_url': config.base_url,
            'max_tokens': config.max_tokens,
            'temperature': config.temperature,
            'top_p': config.top_p,
            'is_active': config.is_active,
            'api_key_length': len(config.api_key) if config.api_key else 0,  # 返回API Key长度用于生成掩码
            'created_at': config.created_at,
            'updated_at': config.updated_at
        } for config in configs]
        return Response(serializer_data)

    def create(self, request):
        """
        创建新的AI智能模式配置
        """
        data = request.data
        user = request.user
        model_parameters = self._validated_model_parameters(data)

        # 验证必填字段
        role = data.get('role', 'executor_text')
        required_fields = ['name', 'model_type', 'model_name']
        if role != 'hermes_agent':
            required_fields.append('api_key')
        for field in required_fields:
            if not data.get(field):
                return Response(
                    {'error': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 验证role字段
        if role not in self.BROWSER_USE_ROLES:
            return Response(
                {'error': f'role must be one of {self.BROWSER_USE_ROLES}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 如果创建时启用，先禁用同一role的其他配置
        if data.get('is_active', True):
            AITestModelConfig.objects.filter(role=role, is_active=True).update(is_active=False)

        # 创建新配置
        config = AITestModelConfig.objects.create(
            name=data['name'],
            model_type=data['model_type'],
            role=role,
            model_name=data['model_name'],
            api_key=data.get('api_key', ''),
            base_url=data.get('base_url', ''),
            **model_parameters,
            is_active=data.get('is_active', True),
            created_by=user
        )

        return Response({
            'id': config.id,
            'name': config.name,
            'model_type': config.model_type,
            'model_name': config.model_name,
            'base_url': config.base_url,
            'max_tokens': config.max_tokens,
            'temperature': config.temperature,
            'top_p': config.top_p,
            'is_active': config.is_active,
            'created_at': config.created_at
        }, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        """
        获取单个配置详情
        """
        try:
            config = self.queryset.get(pk=pk)
            return Response({
                'id': config.id,
                'name': config.name,
                'model_type': config.model_type,
                'model_name': config.model_name,
                'base_url': config.base_url,
                'max_tokens': config.max_tokens,
                'temperature': config.temperature,
                'top_p': config.top_p,
                'is_active': config.is_active,
                'created_at': config.created_at,
                'updated_at': config.updated_at
            })
        except AITestModelConfig.DoesNotExist:
            return Response(
                {'error': 'Config not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    def update(self, request, pk=None):
        """
        更新配置 (PUT)
        """
        try:
            config = self.queryset.get(pk=pk)
            data = request.data
            model_parameters = self._validated_model_parameters(data)
            new_role = data.get('role', config.role)
            if new_role not in self.BROWSER_USE_ROLES:
                return Response(
                    {'error': f'role must be one of {self.BROWSER_USE_ROLES}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 如果启用此配置，先禁用同一role的其他配置
            new_is_active = data.get('is_active', config.is_active)
            disabled_config_names = []
            if new_is_active:
                # 查找同一role下将被禁用的配置
                active_configs = AITestModelConfig.objects.filter(role=new_role, is_active=True).exclude(pk=pk)
                disabled_config_names = [c.name for c in active_configs]
                active_configs.update(is_active=False)

            # 更新字段
            if 'name' in data:
                config.name = data['name']
            if 'model_type' in data:
                config.model_type = data['model_type']
            if 'role' in data:
                config.role = new_role
            if 'model_name' in data:
                config.model_name = data['model_name']
            if 'api_key' in data and data['api_key']:
                config.api_key = data['api_key']
            if 'base_url' in data:
                config.base_url = data['base_url']
            for field, value in model_parameters.items():
                setattr(config, field, value)
            if 'is_active' in data:
                config.is_active = data['is_active']

            config.save()

            response_data = {
                'id': config.id,
                'name': config.name,
                'model_type': config.model_type,
                'role': config.role,
                'model_name': config.model_name,
                'base_url': config.base_url,
                'max_tokens': config.max_tokens,
                'temperature': config.temperature,
                'top_p': config.top_p,
                'is_active': config.is_active,
                'created_at': config.created_at,
                'updated_at': config.updated_at
            }

            # 如果禁用了其他配置,返回被禁用的配置名称
            if disabled_config_names:
                response_data['disabled_configs'] = disabled_config_names

            return Response(response_data)
        except AITestModelConfig.DoesNotExist:
            return Response(
                {'error': 'Config not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def partial_update(self, request, pk=None):
        """
        部分更新配置 (PATCH)
        """
        return self.update(request, pk)

    def destroy(self, request, pk=None):
        """
        删除配置
        """
        try:
            config = self.queryset.get(pk=pk)
            config.delete()
            return Response(
                {'message': 'Config deleted successfully'},
                status=status.HTTP_204_NO_CONTENT
            )
        except AITestModelConfig.DoesNotExist:
            return Response(
                {'error': 'Config not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['post'], url_path='test_connection')
    def test_connection_preview(self, request):
        """
        测试模型连接 (在保存前测试，不保存配置)
        """
        provider = request.data.get('provider')
        base_url = request.data.get('base_url')
        api_key = request.data.get('api_key')
        model_name = request.data.get('model_name')
        role = request.data.get('role', 'executor_text')
        model_parameters = {
            'max_tokens': 120,
            'temperature': 0.7,
            'top_p': 0.9,
            **self._validated_model_parameters(request.data),
        }

        if role != 'hermes_agent' and not api_key:
            return Response(
                {'error': 'API Key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if role not in self.BROWSER_USE_ROLES:
            return Response(
                {'error': f'role must be one of {self.BROWSER_USE_ROLES}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        base_url = self._resolve_base_url(provider, base_url)
        api_key = self._resolve_api_key(role, base_url, api_key)
        if not base_url:
             return Response(
                 {'error': 'Base URL is required for this provider'},
                 status=status.HTTP_400_BAD_REQUEST
             )
        if not api_key:
            return Response(
                {'error': 'API Key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 尝试调用 chat completions 接口 (OpenAI Compatible)
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            data = self._build_test_payload(role, model_name, **model_parameters)

            logger.info(f"AI智能模式预览 - 发送POST请求到: {url}, role={role}")
            # 增加超时时间：连接超时60秒，读取超时900秒
            response = requests.post(url, headers=headers, json=data, timeout=(60, 900))

            logger.info(f"AI智能模式预览 - 收到响应: status_code={response.status_code}")

            if response.status_code == 200:
                return Response({'message': self._extract_test_message(role, response)})
            else:
                logger.error(f"AI智能模式 - API调用返回错误: Status={response.status_code}, Body={response.text}")
                return Response(
                    {'error': f'连接失败: {response.status_code} - {response.text}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except requests.exceptions.Timeout as e:
            logger.error(f"AI智能模式 - API连接测试超时: {repr(e)}")
            return Response(
                {'error': '连接测试超时: 请检查网络连接或API地址是否正确'},
                status=status.HTTP_408_REQUEST_TIMEOUT
            )
        except Exception as e:
            logger.error(f"AI智能模式 - API连接测试异常: {repr(e)}")
            return Response(
                {'error': f'连接异常: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """
        测试已保存配置的连接
        """
        try:
            config = self.queryset.get(pk=pk)
        except AITestModelConfig.DoesNotExist:
            return Response(
                {'error': 'Config not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        logger.info(f"=== AI智能模式 - 开始测试模型连接 ===")
        logger.info(f"模型类型: {config.model_type}")
        logger.info(f"模型名称: {config.model_name}")
        logger.info(f"API URL: {config.base_url}")
        logger.info(f"API Key前缀: {config.api_key[:10]}..." if len(config.api_key) > 10 else f"API Key: {config.api_key}")

        base_url = self._resolve_base_url(config.model_type, config.base_url)
        api_key = self._resolve_api_key(config.role, base_url, config.api_key)
        if not base_url:
            return Response(
                {'error': 'Base URL is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not api_key:
            return Response(
                {'error': 'API Key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            data = self._build_test_payload(
                config.role,
                config.model_name,
                config.max_tokens,
                config.temperature,
                config.top_p,
            )

            logger.info(f"AI智能模式 - 发送POST请求到: {url}, role={config.role}")
            # 增加超时时间：连接超时60秒，读取超时900秒
            response = requests.post(url, headers=headers, json=data, timeout=(60, 900))

            logger.info(f"AI智能模式 - 收到响应: status_code={response.status_code}")

            if response.status_code == 200:
                logger.info("AI智能模式 - API连接测试成功")
                return Response({'message': self._extract_test_message(config.role, response)})
            else:
                logger.error(f"AI智能模式 - API调用返回错误: Status={response.status_code}, Body={response.text}")
                return Response(
                    {'error': f'连接失败: {response.status_code} - {response.text}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except requests.exceptions.Timeout as e:
            logger.error(f"AI智能模式 - API连接测试超时: {repr(e)}")
            return Response(
                {'error': '连接测试超时: 请检查网络连接或API地址是否正确'},
                status=status.HTTP_408_REQUEST_TIMEOUT
            )
        except Exception as e:
            logger.error(f"AI智能模式 - API连接测试异常: {repr(e)}")
            return Response(
                {'error': f'连接异常: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AIModePromptConfigViewSet(viewsets.ViewSet):
    """
    AI智能模式提示词配置视图集
    """
    permission_classes = [IsAuthenticated]
    BROWSER_USE_PROMPT_TYPES = ['planner_text', 'planner_vision', 'executor_text', 'executor_vision', 'hermes_agent']

    def _get_queryset(self):
        return AITestPromptConfig.objects.filter(prompt_type__in=self.BROWSER_USE_PROMPT_TYPES)

    def list(self, request):
        configs = self._get_queryset().order_by('-created_at')
        data = [{
            'id': c.id,
            'name': c.name,
            'prompt_type': c.prompt_type,
            'prompt_type_display': c.get_prompt_type_display(),
            'content': c.content,
            'is_active': c.is_active,
            'created_by_name': c.created_by.username if c.created_by else '',
            'created_at': c.created_at,
            'updated_at': c.updated_at,
        } for c in configs]
        return Response(data)

    def create(self, request):
        data = request.data
        for field in ['name', 'prompt_type', 'content']:
            if not data.get(field):
                return Response({'error': f'{field} is required'}, status=status.HTTP_400_BAD_REQUEST)

        prompt_type = data['prompt_type']
        if prompt_type not in self.BROWSER_USE_PROMPT_TYPES:
            return Response({'error': f'prompt_type must be one of {self.BROWSER_USE_PROMPT_TYPES}'}, status=status.HTTP_400_BAD_REQUEST)

        is_active = data.get('is_active', True)
        if is_active:
            AITestPromptConfig.objects.filter(prompt_type=prompt_type, is_active=True).update(is_active=False)

        config = AITestPromptConfig.objects.create(
            name=data['name'],
            prompt_type=prompt_type,
            content=data['content'],
            is_active=is_active,
            created_by=request.user
        )
        return Response({
            'id': config.id,
            'name': config.name,
            'prompt_type': config.prompt_type,
            'prompt_type_display': config.get_prompt_type_display(),
            'content': config.content,
            'is_active': config.is_active,
            'created_at': config.created_at,
        }, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        try:
            config = self._get_queryset().get(pk=pk)
        except AITestPromptConfig.DoesNotExist:
            return Response({'error': 'Config not found'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        new_is_active = data.get('is_active', config.is_active)
        if new_is_active and not config.is_active:
            AITestPromptConfig.objects.filter(prompt_type=config.prompt_type, is_active=True).exclude(pk=pk).update(is_active=False)

        if 'name' in data:
            config.name = data['name']
        if 'content' in data:
            config.content = data['content']
        if 'is_active' in data:
            config.is_active = data['is_active']
        config.save()

        return Response({
            'id': config.id,
            'name': config.name,
            'prompt_type': config.prompt_type,
            'prompt_type_display': config.get_prompt_type_display(),
            'content': config.content,
            'is_active': config.is_active,
            'created_at': config.created_at,
            'updated_at': config.updated_at,
        })

    def partial_update(self, request, pk=None):
        return self.update(request, pk)

    def destroy(self, request, pk=None):
        try:
            config = self._get_queryset().get(pk=pk)
            config.delete()
            return Response({'message': 'Config deleted'}, status=status.HTTP_204_NO_CONTENT)
        except AITestPromptConfig.DoesNotExist:
            return Response({'error': 'Config not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def load_defaults(self, request):
        """加载默认提示词"""
        from django.conf import settings
        defaults = {}
        for prompt_type, filename in [
            ('planner_text', 'browser_use_text.md'),
            ('planner_vision', 'browser_use_vision.md'),
            ('executor_text', 'browser_use_text.md'),
            ('executor_vision', 'browser_use_vision.md'),
            ('hermes_agent', 'hermes_agent.md'),
        ]:
            filepath = os.path.join(settings.BASE_DIR, 'docs', filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    defaults[prompt_type] = f.read()
            except FileNotFoundError:
                defaults[prompt_type] = f'# {prompt_type} 默认提示词\n\n请配置提示词内容。'
        return Response({'defaults': defaults})
