import asyncio
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
import requests

from backend.config_loader import config_loader
from apps.ai_testing.models import AITestModelConfig, AITestPromptConfig

logger = logging.getLogger('django')

load_dotenv()


class HermesAgent:
    @staticmethod
    def _running_in_docker():
        return os.path.exists('/.dockerenv') or os.getenv('IN_DOCKER', '').lower() == 'true'

    @classmethod
    def _normalize_base_url(cls, raw_base_url):
        normalized = str(raw_base_url or '').strip()
        if not normalized:
            return ''

        normalized = normalized.rstrip('/')
        if normalized.endswith('/chat/completions'):
            normalized = normalized[:-len('/chat/completions')]

        parsed = urlparse(normalized)
        hostname = parsed.hostname
        if cls._running_in_docker() and hostname in {'127.0.0.1', 'localhost'}:
            netloc = parsed.netloc.replace(hostname, 'host.docker.internal')
            parsed = parsed._replace(netloc=netloc)
            normalized = urlunparse(parsed)

        if not normalized.endswith('/v1'):
            normalized += '/v1'

        return normalized

    @classmethod
    def _build_auth_key_url(cls, normalized_base_url):
        parsed = urlparse(str(normalized_base_url or '').strip())
        if not parsed.scheme or not parsed.netloc:
            return ''
        return urlunparse((parsed.scheme, parsed.netloc, '/api/auth/key', '', '', ''))

    @staticmethod
    def _read_api_key_file(file_path):
        normalized_path = str(file_path or '').strip()
        if not normalized_path:
            return None

        try:
            content = Path(normalized_path).read_text(encoding='utf-8').strip()
        except OSError as error:
            logger.warning(f"⚠️ Failed to read Hermes API key file {normalized_path}: {error}")
            return None

        return content or None

    @classmethod
    def _fetch_dynamic_api_key(cls, normalized_base_url):
        auth_key_url = cls._build_auth_key_url(normalized_base_url)
        if not auth_key_url:
            return None

        try:
            response = requests.get(auth_key_url, timeout=(10, 30))
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            logger.warning(f"⚠️ Failed to fetch Hermes API key from auth endpoint: {error}")
            return None

        api_key = str(payload.get('api_key', '') or '').strip()
        return api_key or None

    def __init__(self, execution_mode='hermes', enable_gif=False, case_name=None):
        self.execution_mode = execution_mode
        self.enable_gif = enable_gif
        self.case_name = case_name or 'Adhoc Task'

        config_obj = AITestModelConfig.objects.filter(role='hermes_agent', is_active=True).first()
        if config_obj is None:
            raise ValueError('No active AI Testing Hermes model is configured')
        self.request_timeout = float(config_loader.get('ai.hermes.request_timeout', 900))
        self.max_retries = int(config_loader.get('ai.hermes.max_retries', 1))
        self.base_url = self._normalize_base_url(config_obj.base_url)
        self.model_name = config_obj.model_name
        self.provider = config_obj.model_type
        self.max_tokens = config_obj.max_tokens
        self.temperature = config_obj.temperature
        self.top_p = config_obj.top_p
        self.api_key = config_obj.api_key

        if not self.api_key:
            raise ValueError('The active AI Testing Hermes model has no API key')

        if not self.base_url:
            raise ValueError('The active AI Testing Hermes model has no base URL')

        model_name_lower = self.model_name.lower()
        is_reasoning_model = model_name_lower.startswith(('gpt-5', 'o1', 'o3', 'o4'))
        if is_reasoning_model:
            llm_parameters = {'max_completion_tokens': self.max_tokens}
        else:
            llm_parameters = {
                'temperature': 1.0 if 'kimi' in model_name_lower else self.temperature,
                'top_p': self.top_p,
                'extra_body': {'max_tokens': self.max_tokens},
            }

        self.llm = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            **llm_parameters,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
        )

    def _load_prompt_content(self):
        db_config = AITestPromptConfig.get_active_config('hermes_agent')
        if not db_config or not db_config.content.strip():
            raise ValueError('No active AI Testing Hermes prompt is configured')
        logger.info(f"📝 Loaded Hermes prompt from dedicated AI Testing configuration: {db_config.name}")
        return db_config.content

    async def _emit_callback(self, callback, payload):
        if not callback:
            return
        if asyncio.iscoroutinefunction(callback):
            await callback(payload)
        else:
            callback(payload)

    def _normalize_success_value(self, value):
        if isinstance(value, bool):
            return value

        normalized = str(value or '').strip().lower()
        if normalized in {'true', '1', 'yes', 'ok', 'completed', 'success', 'successful'}:
            return True
        if normalized in {'false', '0', 'no', 'failed', 'failure', 'error'}:
            return False
        return None

    def _normalize_logs(self, logs, fallback_text):
        if isinstance(logs, str):
            logs = [logs]

        if not isinstance(logs, list):
            logs = []

        normalized_logs = [str(log_line).strip() for log_line in logs if str(log_line).strip()]
        if normalized_logs:
            return normalized_logs

        fallback = str(fallback_text or '').strip()
        return [fallback] if fallback else []

    def _normalize_task_results(self, payload, planned_tasks):
        if not isinstance(payload, dict):
            return []

        raw_results = (
            payload.get('task_results')
            or payload.get('step_results')
            or payload.get('steps')
            or payload.get('results')
        )
        if not isinstance(raw_results, list):
            return []

        max_task_id = len(planned_tasks or [])
        normalized_results = []
        for index, item in enumerate(raw_results, start=1):
            if not isinstance(item, dict):
                continue

            raw_task_id = item.get('task_id', item.get('id', item.get('step_id', index)))
            try:
                task_id = int(raw_task_id)
            except (TypeError, ValueError):
                continue

            if max_task_id and not 1 <= task_id <= max_task_id:
                continue

            raw_status = item.get('status', item.get('result'))
            normalized_status = str(raw_status or '').strip().lower()
            if normalized_status not in {'completed', 'failed', 'skipped'}:
                success_value = self._normalize_success_value(item.get('success', raw_status))
                if success_value is True:
                    normalized_status = 'completed'
                elif success_value is False:
                    normalized_status = 'failed'
                else:
                    continue

            log_lines = self._normalize_logs(
                item.get('logs', item.get('log', item.get('message'))),
                item.get('summary', item.get('description', '')),
            )
            normalized_results.append(
                {
                    'task_id': task_id,
                    'status': normalized_status,
                    'summary': str(item.get('summary', '') or '').strip(),
                    'logs': log_lines,
                }
            )

        return normalized_results

    def _extract_structured_steps(self, task_description):
        normalized_text = str(task_description or '').replace('\r\n', '\n').replace('\r', '\n').strip()
        if not normalized_text:
            return []

        numbered_steps = []
        plain_lines = []
        pattern = re.compile(r'^\s*(\d+(?:\.\d+)*)[\.\s、:：-]+(.*)$')

        for raw_line in normalized_text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            match = pattern.match(line)
            if match:
                description = match.group(2).strip()
                if description:
                    numbered_steps.append(description)
            else:
                plain_lines.append(line)

        if numbered_steps:
            return numbered_steps
        if plain_lines:
            return plain_lines
        return [normalized_text]

    def _fallback_result(self, content):
        lowered = str(content or '').lower()
        success_markers = ['"success": true', 'success=true', '执行成功', '任务完成', 'completed successfully']
        failed_markers = ['"success": false', 'success=false', '执行失败', '任务失败', 'failed']
        normalized_logs = self._normalize_logs(content, content)

        if any(marker in lowered for marker in failed_markers):
            return {
                'success': False,
                'summary': str(content).strip(),
                'logs': normalized_logs,
                'task_results': [],
            }
        if any(marker in lowered for marker in success_markers):
            return {
                'success': True,
                'summary': str(content).strip(),
                'logs': normalized_logs,
                'task_results': [],
            }
        return {
            'success': True,
            'summary': str(content).strip(),
            'logs': normalized_logs,
            'task_results': [],
        }

    def _parse_response(self, content, planned_tasks=None):
        if not content:
            return {
                'success': False,
                'summary': 'Hermes returned empty content.',
                'logs': ['Hermes returned empty content.'],
                'task_results': [],
            }

        cleaned = str(content).strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
            if not match:
                return self._fallback_result(cleaned)

            payload = json.loads(match.group(1))
            success = self._normalize_success_value(payload.get('success'))
            task_results = self._normalize_task_results(payload, planned_tasks)

            if success is None and task_results:
                success = not any(item['status'] == 'failed' for item in task_results)
            if success is None:
                success = False

            summary = str(
                payload.get('summary')
                or payload.get('message')
                or payload.get('error')
                or ''
            ).strip()
            normalized_logs = self._normalize_logs(payload.get('logs'), summary or cleaned)
            if not summary and normalized_logs:
                summary = normalized_logs[-1]

            return {
                'success': success,
                'summary': summary or cleaned,
                'logs': normalized_logs,
                'task_results': task_results,
            }
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._fallback_result(cleaned)

    async def analyze_task(self, task_description):
        steps = self._extract_structured_steps(task_description)
        if not steps:
            steps = [str(task_description).strip()] if str(task_description or '').strip() else []
        return [
            {'id': index + 1, 'description': step, 'status': 'pending'}
            for index, step in enumerate(steps)
        ]

    async def run_task(self, task_description, planned_tasks=None, callback=None, should_stop=None):
        if should_stop:
            do_stop = await should_stop() if asyncio.iscoroutinefunction(should_stop) else should_stop()
            if do_stop:
                raise KeyboardInterrupt('User requested stop')

        await self._emit_callback(callback, {'type': 'log', 'content': '\n[Hermes]\n开始向 Hermes 发送任务...\n'})
        prompt_content = await asyncio.to_thread(self._load_prompt_content)

        messages = [
            SystemMessage(content=prompt_content),
            HumanMessage(content=str(task_description or '').strip()),
        ]

        response = await asyncio.wait_for(self.llm.ainvoke(messages), timeout=self.request_timeout)
        content = response.content if hasattr(response, 'content') else str(response)
        parsed_result = self._parse_response(content, planned_tasks)
        success = parsed_result['success']
        summary = parsed_result['summary']
        logs = parsed_result['logs']
        task_results = parsed_result['task_results']

        for log_line in logs:
            await self._emit_callback(callback, {'type': 'log', 'content': f'{log_line}\n'})

        if planned_tasks:
            emitted_task_ids = set()
            for task_result in task_results:
                task_id = task_result['task_id']
                emitted_task_ids.add(task_id)
                for task_log in task_result['logs']:
                    await self._emit_callback(
                        callback,
                        {'type': 'log', 'content': f'[Hermes][Task {task_id}] {task_log}\n'},
                    )
                await self._emit_callback(
                    callback,
                    {'task_id': task_id, 'status': task_result['status']},
                )

            if not emitted_task_ids:
                final_status = 'completed' if success else 'failed'
                for task in planned_tasks:
                    task_id = task.get('id')
                    if task_id is None:
                        continue
                    await self._emit_callback(callback, {'task_id': int(task_id), 'status': final_status})

        await self._emit_callback(
            callback,
            {
                'type': 'log',
                'content': f"\n[Hermes]\n任务{'完成' if success else '失败'}: {summary}\n",
            },
        )

        return {
            'success': success,
            'summary': summary,
            'logs': logs,
            'steps': task_results,
        }

    async def run_full_process(self, task_description, analysis_callback=None, step_callback=None, should_stop=None):
        planned_tasks = await self.analyze_task(task_description)
        if analysis_callback:
            if asyncio.iscoroutinefunction(analysis_callback):
                await analysis_callback(planned_tasks)
            else:
                analysis_callback(planned_tasks)

        return await self.run_task(task_description, planned_tasks, step_callback, should_stop)