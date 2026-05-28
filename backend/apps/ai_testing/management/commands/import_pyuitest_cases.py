from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ai_testing.models import AICase, AiProject


logger = logging.getLogger('django')
User = get_user_model()


class Command(BaseCommand):
    help = 'Import pyuitest testcase.yaml into AI intelligent mode cases as hybrid steps'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--yaml-path',
            default=None,
            help='Path to pyuitest testcase.yaml. Defaults to <repo>/pyuitest/tests/testcase.yaml',
        )
        parser.add_argument(
            '--project-name',
            default='pyuitest 导入用例',
            help='Target AI testing project name',
        )
        parser.add_argument(
            '--case-id',
            action='append',
            dest='case_ids',
            default=[],
            help='Import only the specified case id. Can be passed multiple times.',
        )
        parser.add_argument(
            '--created-by',
            default=None,
            help='Username to assign as creator/owner when creating missing project or cases',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Update existing cases with the same name inside the target project',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse and preview the import without writing to the database',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        yaml_path = self._resolve_yaml_path(options.get('yaml_path'))
        if not yaml_path.exists():
            raise CommandError(f'YAML file not found: {yaml_path}')

        selected_case_ids = {str(case_id).strip() for case_id in options['case_ids'] if str(case_id).strip()}
        overwrite = bool(options['overwrite'])
        dry_run = bool(options['dry_run'])

        raw_cases = self._load_cases(yaml_path)
        normalized_cases = self._normalize_cases(raw_cases, selected_case_ids)
        if not normalized_cases:
            self.stdout.write(self.style.WARNING('没有匹配的用例可导入'))
            return

        self.stdout.write(f'读取文件: {yaml_path}')
        self.stdout.write(f'候选用例数: {len(normalized_cases)}')

        if dry_run:
            self._print_preview(normalized_cases)
            self.stdout.write(self.style.SUCCESS('Dry run 完成，未写入数据库'))
            return

        creator = self._resolve_creator(options.get('created_by'))

        with transaction.atomic():
            project = self._get_or_create_project(
                name=str(options['project_name']).strip(),
                description=f'Imported from {yaml_path.name}',
                creator=creator,
            )

            created_count = 0
            updated_count = 0
            skipped_count = 0

            for case in normalized_cases:
                defaults = {
                    'description': case['description'],
                    'task_description': case['task_description'],
                    'case_mode': 'hybrid',
                    'task_steps': case['task_steps'],
                }
                existing = AICase.objects.filter(project=project, name=case['name']).first()
                if existing and not overwrite:
                    skipped_count += 1
                    self.stdout.write(self.style.WARNING(f"跳过已存在用例: {case['name']}"))
                    continue

                obj, created = AICase.objects.update_or_create(
                    project=project,
                    name=case['name'],
                    defaults={
                        **defaults,
                        'created_by': existing.created_by if existing and existing.created_by else creator,
                    },
                )
                action = '创建' if created else '更新'
                self.stdout.write(self.style.SUCCESS(f'{action}用例: {obj.name} ({case["source_id"]})'))
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('导入完成'))
        self.stdout.write(f'项目: {project.name}')
        self.stdout.write(f'新建: {created_count}')
        self.stdout.write(f'更新: {updated_count}')
        self.stdout.write(f'跳过: {skipped_count}')

    def _resolve_yaml_path(self, value: str | None) -> Path:
        if value:
            return Path(value).expanduser().resolve()

        from django.conf import settings

        return (Path(settings.BASE_DIR).parent / 'pyuitest' / 'tests' / 'testcase.yaml').resolve()

    def _resolve_creator(self, username: str | None):
        normalized_username = str(username or '').strip()
        if normalized_username:
            user = User.objects.filter(username=normalized_username).first()
            if user is None:
                raise CommandError(f'用户不存在: {normalized_username}')
            return user

        return User.objects.order_by('-is_superuser', 'id').first()

    def _load_cases(self, yaml_path: Path) -> list[dict[str, Any]]:
        try:
            with yaml_path.open('r', encoding='utf-8') as handle:
                payload = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise CommandError(f'YAML 解析失败: {exc}') from exc

        if not isinstance(payload, list):
            raise CommandError('testcase.yaml 顶层必须是列表')
        return [item for item in payload if isinstance(item, dict)]

    def _normalize_cases(self, raw_cases: list[dict[str, Any]], selected_case_ids: set[str]) -> list[dict[str, Any]]:
        normalized_cases: list[dict[str, Any]] = []
        for raw_case in raw_cases:
            source_id = str(raw_case.get('id') or '').strip()
            if not source_id:
                logger.warning('Skip pyuitest case without id: %s', raw_case)
                continue
            if selected_case_ids and source_id not in selected_case_ids:
                continue

            base_case_name = str(raw_case.get('name') or source_id).strip()
            case_name = f'[{source_id}] {base_case_name}'
            module_name = str(raw_case.get('module') or '').strip()
            raw_steps = raw_case.get('steps') or []
            if not isinstance(raw_steps, list) or not raw_steps:
                logger.warning('Skip pyuitest case %s due to empty or invalid steps', source_id)
                continue

            task_steps = self._build_task_steps(raw_steps)
            if not task_steps:
                logger.warning('Skip pyuitest case %s because no executable steps were produced', source_id)
                continue

            normalized_cases.append(
                {
                    'source_id': source_id,
                    'name': case_name,
                    'description': f'Imported from pyuitest ({source_id})' + (f' / {module_name}' if module_name else ''),
                    'task_description': self._build_task_description(task_steps),
                    'task_steps': task_steps,
                }
            )
        return normalized_cases

    def _build_task_steps(self, raw_steps: list[Any]) -> list[dict[str, Any]]:
        task_steps: list[dict[str, Any]] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, str):
                logger.warning('Skip non-string step during import: %s', raw_step)
                continue
            task_steps.extend(self._convert_step(raw_step.strip()))

        for index, step in enumerate(task_steps, start=1):
            step['step_no'] = index
        return task_steps

    def _convert_step(self, raw_step: str) -> list[dict[str, Any]]:
        if not raw_step:
            return []
        if not raw_step.startswith('playwright:'):
            return [
                {
                    'step_mode': 'ai',
                    'description': raw_step,
                    'timeout_ms': 10000,
                }
            ]

        raw_payload = raw_step[len('playwright:'):].strip()
        try:
            actions = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.warning('Fallback playwright step to AI due to invalid JSON: %s', raw_step)
            return [
                {
                    'step_mode': 'ai',
                    'description': f'执行原始 pyuitest 指令: {raw_step}',
                    'timeout_ms': 10000,
                }
            ]

        if not isinstance(actions, list):
            logger.warning('Fallback playwright step to AI due to non-list JSON: %s', raw_step)
            return [
                {
                    'step_mode': 'ai',
                    'description': f'执行原始 pyuitest 指令: {raw_step}',
                    'timeout_ms': 10000,
                }
            ]

        converted_steps: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                logger.warning('Skip invalid playwright action: %s', action)
                continue
            converted_steps.append(self._map_playwright_action(action))
        return converted_steps

    def _map_playwright_action(self, action: dict[str, Any]) -> dict[str, Any]:
        action_name = str(action.get('action') or '').strip().lower()
        param = str(action.get('param') or '').strip()
        visible = str(action.get('visible') or '').strip().lower()

        if action_name == 'wait':
            wait_seconds = self._safe_seconds(param)
            return {
                'step_mode': 'direct',
                'action': 'wait',
                'description': f'等待 {wait_seconds:g} 秒',
                'timeout_ms': int(wait_seconds * 1000),
            }

        if action_name == 'assert_url':
            return {
                'step_mode': 'direct',
                'action': 'assert_url_contains',
                'description': f'断言当前 URL 包含 {param}',
                'expected': param,
                'timeout_ms': 10000,
            }

        if action_name == 'key':
            return {
                'step_mode': 'direct',
                'action': 'press',
                'description': f'在页面主体按下 {param}',
                'selector': 'body',
                'value': param,
                'timeout_ms': 10000,
            }

        if action_name == 'assert_popup':
            return {
                'step_mode': 'direct',
                'action': 'assert_popup_contains',
                'description': f'断言页面出现提示弹窗，且包含“{param}”' if param else '断言页面出现提示弹窗',
                'expected': param,
                'timeout_ms': 10000,
            }

        if action_name == 'assert_media':
            return {
                'step_mode': 'direct',
                'action': 'assert_media_visible',
                'description': '断言页面中存在可见媒体内容',
                'expected': visible or 'true',
                'timeout_ms': 10000,
            }

        if action_name == 'assert_video':
            return {
                'step_mode': 'direct',
                'action': 'assert_video_visible',
                'description': f'断言页面中可见视频元素 {f"“{param}”" if param else "目标视频流"}',
                'expected': param,
                'timeout_ms': 10000,
            }

        return {
            'step_mode': 'ai',
            'description': self._build_fallback_description(action_name, param, visible),
            'timeout_ms': 10000,
        }

    def _build_fallback_description(self, action_name: str, param: str, visible: str) -> str:
        details: list[str] = []
        if param:
            details.append(f'param={param}')
        if visible:
            details.append(f'visible={visible}')
        suffix = f" ({', '.join(details)})" if details else ''
        normalized_action = action_name or 'unknown'
        return f'执行原始 pyuitest 指令 {normalized_action}{suffix}'

    def _build_task_description(self, task_steps: list[dict[str, Any]]) -> str:
        lines = []
        for index, step in enumerate(task_steps, start=1):
            prefix = '[DIRECT]' if step.get('step_mode') == 'direct' else '[AI]'
            description = str(step.get('description') or '').strip() or f'步骤 {index}'
            lines.append(f'{index}. {prefix} {description}')
        return '\n'.join(lines)

    def _get_or_create_project(self, name: str, description: str, creator):
        existing = AiProject.objects.filter(name=name).first()
        if existing:
            return existing

        project = AiProject.objects.create(
            name=name,
            description=description,
            created_by=creator,
        )

        if creator is None:
            self.stdout.write(self.style.WARNING('未找到可用用户，已创建 AI 项目但未关联统一项目'))
            return project

        from apps.unified_projects.models import MetaProject, ProjectModule

        meta_project = MetaProject.objects.create(
            name=name,
            description=description,
            owner=creator,
            status='not_started',
        )
        ProjectModule.objects.create(
            meta_project=meta_project,
            module_type='AI_TEST',
            ai_project=project,
            config={
                'owner': creator.id,
                'member_ids': [],
            },
        )
        project.unified_meta_project = meta_project
        project.save(update_fields=['unified_meta_project'])
        return project

    def _print_preview(self, normalized_cases: list[dict[str, Any]]) -> None:
        for case in normalized_cases:
            direct_count = sum(1 for step in case['task_steps'] if step.get('step_mode') == 'direct')
            ai_count = sum(1 for step in case['task_steps'] if step.get('step_mode') == 'ai')
            self.stdout.write(
                f"- {case['source_id']} | {case['name']} | total={len(case['task_steps'])} | direct={direct_count} | ai={ai_count}"
            )

    def _safe_seconds(self, value: str) -> float:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            seconds = 1.0
        return max(seconds, 0.0)
