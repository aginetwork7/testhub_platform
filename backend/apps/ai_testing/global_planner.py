from __future__ import annotations

import json
import re
from typing import Any

from asgiref.sync import sync_to_async


class GlobalPlanError(ValueError):
    """Raised when a global test plan cannot be generated or validated."""


class VisualStepReplanner:
    """Planner-side visual replanning from executor evidence."""

    async def create_actions(self, step_description: str, evidence: dict[str, Any]) -> list[dict[str, Any]]:
        config = await self._get_active_model_config()
        if config is None:
            raise GlobalPlanError('未配置可用的 Planner Vision 模型。')

        from apps.requirement_analysis.models import AIModelService

        visible_text = str(evidence.get('visible_text') or '')[:600]
        messages: list[dict[str, Any]] = [
            {
                'role': 'system',
                'content': (
                    'Return only one JSON object: {"actions":[...]}. No prose. '
                    'Actions allowed: click, wait, assert, assert_text_contains, assert_url_contains. '
                    'A click needs selector or loc="(x,y)". '
                    'For camera lists use {"action":"assert","assert_kind":"camera_list","expected":"true"}. '
                    'For live streams use {"action":"assert","assert_kind":"stream_active","expected":"true"}. '
                    'When opening Cameras from an icon-only sidebar, return two actions: '
                    'click the sidebar icon with loc, then {"action":"assert","assert_kind":"site_list","expected":"true"}. '
                    'Do not click a Cameras text menu item unless it is actually visible in the screenshot. '
                    'Each navigation sequence must be followed by an assertion.'
                ),
            },
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': (
                            f'Step: {step_description}\n'
                            f'URL: {evidence.get("url", "")}\n'
                            f'Failure: {str(evidence.get("error", ""))[:300]}\n'
                            f'Visible text:\n{visible_text}'
                        ),
                    },
                ],
            },
        ]
        screenshot = evidence.get('screenshot')
        if screenshot:
            messages[1]['content'].append({'type': 'image_url', 'image_url': {'url': screenshot}})

        response = await AIModelService.call_openai_compatible_api(
            config,
            messages,
            max_tokens=config.max_tokens,
            response_format={'type': 'json_object'},
        )
        try:
            content = response['choices'][0]['message']['content']
            payload = json.loads(str(content or ''))
            actions = payload.get('actions') if isinstance(payload, dict) else None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise GlobalPlanError('Planner Vision 未返回有效 JSON 动作计划。') from error
        if not isinstance(actions, list) or not actions or not all(isinstance(item, dict) for item in actions):
            raise GlobalPlanError('Planner Vision 动作计划为空或格式无效。')
        return actions

    async def assess_playback_advance(self, before_screenshot: str, after_screenshot: str) -> dict[str, Any]:
        config = await self._get_active_model_config()
        if config is None:
            raise GlobalPlanError('未配置可用的 Planner Vision 模型。')

        from apps.requirement_analysis.models import AIModelService

        messages = [
            {
                'role': 'system',
                'content': (
                    'Compare two playback screenshots. Read the burned-in HH:MM:SS timestamps. '
                    'Return only JSON: {"before_time":"HH:MM:SS","after_time":"HH:MM:SS",'
                    '"advanced_seconds":number,"confidence":number}. No prose.'
                ),
            },
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'First image is before clicking 10s Forward; second image is after.'},
                    {'type': 'image_url', 'image_url': {'url': before_screenshot}},
                    {'type': 'image_url', 'image_url': {'url': after_screenshot}},
                ],
            },
        ]
        response = await AIModelService.call_openai_compatible_api(
            config,
            messages,
            max_tokens=config.max_tokens,
            response_format={'type': 'json_object'},
        )
        try:
            payload = json.loads(str(response['choices'][0]['message']['content'] or ''))
            seconds = float(payload['advanced_seconds'])
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise GlobalPlanError('Planner Vision 未返回有效的 Playback 时间证据。') from error
        return {**payload, 'advanced_seconds': seconds}

    @staticmethod
    def _load_active_model_config():
        from apps.ai_testing.models import AITestModelConfig

        return AITestModelConfig.objects.filter(role='planner_vision', is_active=True).first()

    async def _get_active_model_config(self):
        return await sync_to_async(self._load_active_model_config)()


class GlobalTestPlanner:
    """Builds a typed cross-executor plan from one natural-language test goal."""

    async def create_plan(
        self,
        task_description: str,
        api_automation_configuration_id: int | None,
    ) -> list[dict[str, Any]]:
        configs = await self._get_active_model_configs()
        if not configs:
            raise GlobalPlanError('未配置可用的 Planner 模型。')

        from apps.requirement_analysis.models import AIModelService

        prompt_content = await sync_to_async(self._load_active_prompt_content)('planner_text')
        if not prompt_content:
            raise GlobalPlanError('未配置可用的 Planner 文本提示词。')
        messages = self._build_messages(task_description, api_automation_configuration_id, prompt_content)
        last_error: GlobalPlanError | None = None
        for config in configs:
            retry_messages = list(messages)
            for attempt in range(3):
                response = await AIModelService.call_openai_compatible_api(
                    config,
                    retry_messages,
                    max_tokens=1600,
                    response_format={'type': 'json_object'},
                )
                try:
                    return self.normalize_response(response, api_automation_configuration_id, task_description)
                except GlobalPlanError as error:
                    last_error = error
                    retry_messages.append({
                        'role': 'user',
                        'content': 'Your previous response was empty or invalid. Return only a complete JSON object with a non-empty steps array.',
                    })
        raise GlobalPlanError('Planner 连续返回空或无效 JSON 计划。') from last_error

    @staticmethod
    def _build_messages(
        task_description: str,
        configuration_id: int | None,
        prompt_content: str,
    ) -> list[dict[str, Any]]:
        device_context = (
            '设备 CLI 环境已配置，可以输出 device_cli 步骤。'
            if configuration_id is not None
            else '没有设备 CLI 环境配置；不要输出 device_cli 步骤。'
        )
        return [
            {
                'role': 'system',
                'content': (
                    f'{prompt_content}\n\n'
                    'You are a test planner. Convert the user goal into an ordered JSON object '
                    'with one key, steps. Each step must have executor and description. '
                    'executor can only be browser, data_factory, or device_cli. '
                    'For browser, output step_mode="ai" and a concrete description. '
                    'For device_cli, output device_id and optionally command. '
                    'For data_factory, use action="report_vehicle_event" and copy camera_name exactly '
                    'from the user goal when the task asks to construct or report a real Vehicle event. '
                    'For a camera browsing goal, create separate browser steps: open Cameras and verify the Site list '
                    'with camera online/offline counts; select a Site whose online camera count is greater than zero; '
                    'expand that Site, verify its Camera list and thumbnails, then select an online Camera and verify the live stream. '
                    'Copy device_id exactly from the user goal. Never use an internal environment ID, '
                    'never infer a device ID, and never substitute a short numeric value. '
                    'Device commands must be non-interactive: use systemctl is-active for service checks, '
                    'or include --no-pager when systemctl status is required. '
                    'Do not assume systemd exists on embedded devices. When the user asks to verify a '
                    'process such as manager, prefer a non-interactive ps/grep command that exits nonzero '
                    'when the process is absent. '
                    'Do not output credentials, connection commands, shell commands that alter users, '
                    'firewalls, disks, SSH keys, or device power state. '
                    'Keep the plan minimal and preserve dependencies between device and browser work. '
                    f'{device_context}'
                ),
            },
            {'role': 'user', 'content': str(task_description or '').strip()},
        ]

    @staticmethod
    def normalize_response(
        response: dict[str, Any],
        configuration_id: int | None,
        task_description: str = '',
    ) -> list[dict[str, Any]]:
        try:
            content = response['choices'][0]['message']['content']
            payload = json.loads(str(content or ''))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise GlobalPlanError('Planner 未返回有效 JSON 计划。') from error

        steps = payload.get('steps') if isinstance(payload, dict) else None
        if not isinstance(steps, list) or not steps or len(steps) > 50:
            raise GlobalPlanError('Planner 计划必须包含 1 到 50 个步骤。')

        normalized_steps: list[dict[str, Any]] = []
        for index, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, dict):
                raise GlobalPlanError(f'Planner 步骤 {index} 不是对象。')
            executor = str(raw_step.get('executor', '')).strip()
            description = str(raw_step.get('description', '')).strip()
            if executor == 'browser':
                if not description:
                    raise GlobalPlanError(f'Planner 浏览器步骤 {index} 缺少 description。')
                normalized_description = description.lower()
                camera_browse_markers = ('camera', '摄像头', '摄像机')
                if (
                    any(marker in normalized_description for marker in camera_browse_markers)
                    and ('缩略图' in description or 'thumbnail' in normalized_description)
                    and ('在线' in description or 'online' in normalized_description)
                ):
                    normalized_steps.extend([
                        {
                            'executor': 'browser',
                            'step_mode': 'ai',
                            'description': '打开 Cameras 页面，断言 Site 列表展示各 Site 的摄像头在线/离线数量。',
                        },
                        {
                            'executor': 'browser',
                            'step_mode': 'ai',
                            'description': '选择摄像头在线数量大于 0 的 Site 并展开，断言其 Camera 列表及缩略图可见。',
                        },
                    ])
                    continue
                camera_name = GlobalTestPlanner._event_camera_name(description, task_description)
                if camera_name:
                    if configuration_id is None:
                        raise GlobalPlanError('事件构造步骤需要可访问的 API 自动化环境。')
                    normalized_steps.extend([
                        {
                            'executor': 'data_factory',
                            'action': 'report_vehicle_event',
                            'description': f'为摄像头 {camera_name} 真实上报 Vehicle 事件',
                            'camera_name': camera_name,
                        },
                        {
                            'executor': 'browser',
                            'step_mode': 'ai',
                            'description': f'在 Alert 页面核实摄像头 {camera_name} 的新 Vehicle 事件已生成',
                        },
                    ])
                    continue
                normalized_steps.append({
                    'executor': 'browser',
                    'step_mode': 'ai',
                    'description': description,
                })
                continue
            if executor == 'data_factory':
                if configuration_id is None:
                    raise GlobalPlanError('计划包含 data_factory 步骤，但用例未选择设备 CLI 环境。')
                action = str(raw_step.get('action', '')).strip()
                camera_name = str(raw_step.get('camera_name', '')).strip()
                if action != 'report_vehicle_event' or not camera_name:
                    raise GlobalPlanError(f'Planner 数据工厂步骤 {index} 缺少 report_vehicle_event 或 camera_name。')
                if not GlobalTestPlanner._device_id_is_from_goal(camera_name, task_description):
                    raise GlobalPlanError(f'Planner 数据工厂步骤 {index} 的 camera_name 未在原始需求中明确出现。')
                normalized_steps.append({
                    'executor': 'data_factory',
                    'action': 'report_vehicle_event',
                    'description': description or f'为摄像头 {camera_name} 真实上报 Vehicle 事件',
                    'camera_name': camera_name,
                })
                continue
            if executor != 'device_cli':
                raise GlobalPlanError(f'Planner 步骤 {index} 使用了不支持的执行器：{executor}')
            if configuration_id is None:
                raise GlobalPlanError('计划包含 device_cli 步骤，但用例未选择设备 CLI 环境。')
            device_id = str(raw_step.get('device_id', '')).strip()
            if not device_id:
                raise GlobalPlanError(f'Planner 设备步骤 {index} 缺少 device_id。')
            if not GlobalTestPlanner._device_id_is_from_goal(device_id, task_description):
                raise GlobalPlanError(f'Planner 设备步骤 {index} 的 device_id 未在原始需求中明确出现。')
            step = {
                'executor': 'device_cli',
                'description': description or f'连接设备 {device_id} 并执行设备命令',
                'device_id': device_id,
            }
            command = raw_step.get('command')
            if command is not None and str(command).strip():
                step['command'] = str(command).strip()
            normalized_steps.append(step)
        camera_workflow_markers = ('cameras', 'camera', '摄像头', '摄像机', '缩略图', 'thumbnail')
        if sum(marker in task_description.lower() for marker in camera_workflow_markers) >= 2:
            playback_index = next(
                (
                    index for index, step in enumerate(normalized_steps)
                    if step.get('executor') == 'browser'
                    and any(token in str(step.get('description') or '').lower() for token in ('playback', '回放'))
                ),
                None,
            )
            if playback_index is not None:
                normalized_steps = [
                    {
                        'executor': 'browser',
                        'step_mode': 'ai',
                        'description': '打开 Cameras 页面，断言 Site 列表展示各 Site 的摄像头在线/离线数量。',
                    },
                    {
                        'executor': 'browser',
                        'step_mode': 'ai',
                        'description': '选择摄像头在线数量大于 0 的 Site 并展开，断言其 Camera 列表及缩略图可见。',
                    },
                    {
                        'executor': 'browser',
                        'step_mode': 'ai',
                        'description': '选择在线 Camera 的缩略图，断言直播流持续播放。',
                    },
                    *normalized_steps[playback_index:],
                ]
        return normalized_steps

    @staticmethod
    def _device_id_is_from_goal(device_id: str, task_description: str) -> bool:
        if not device_id or not task_description:
            return False
        pattern = rf'(?<![A-Za-z0-9_-]){re.escape(device_id)}(?![A-Za-z0-9_-])'
        return re.search(pattern, task_description) is not None

    @staticmethod
    def _event_camera_name(description: str, task_description: str) -> str | None:
        event_keywords = ('事件构造', '真实事件', '真实上报', 'construct event', 'report event')
        combined_text = f'{description}\n{task_description}'.lower()
        if not any(keyword in combined_text for keyword in event_keywords):
            return None
        match = re.search(r'\b\d{4,}_[A-Za-z]\d+\b', task_description)
        return match.group(0) if match else None

    @staticmethod
    def _load_active_model_configs():
        from apps.ai_testing.models import AITestModelConfig

        configs = list(
            AITestModelConfig.objects.filter(
                role='planner_text',
                is_active=True,
            ).order_by('id')
        )
        seen = set()
        unique_configs = []
        for config in configs:
            fingerprint = (config.model_type, config.base_url, config.model_name)
            if fingerprint not in seen:
                seen.add(fingerprint)
                unique_configs.append(config)
        return unique_configs

    @staticmethod
    def _load_active_prompt_content(prompt_type: str) -> str:
        from apps.ai_testing.models import AITestPromptConfig

        config = AITestPromptConfig.get_active_config(prompt_type)
        return config.content.strip() if config and config.content else ''

    async def _get_active_model_configs(self):
        return await sync_to_async(self._load_active_model_configs)()