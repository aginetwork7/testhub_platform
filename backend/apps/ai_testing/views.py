import logging
import os
import re
import json
from pathlib import Path
from django.conf import settings
from django.db import connection, transaction
from django.db import models
from django.http import HttpResponse
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import AiProject, AICase, AIExecutionExperience, AIExecutionRecord
from .serializers import AiProjectSerializer, AICaseSerializer, AIExecutionExperienceSerializer, AIExecutionRecordSerializer
from .global_planner import GlobalPlanError, GlobalTestPlanner
from .alpha.access import accessible_ai_project_queryset

logger = logging.getLogger(__name__)

# 全局字典，用于存储停止信号
from .execution.dispatch import STOP_SIGNALS, dispatch_ai_execution, launch_case_execution, process_gif_recording, request_stop  # noqa: E402


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


def has_canonical_freeform_plan(planned_steps, environment_configuration_id, task_description):
    if not isinstance(planned_steps, list) or not planned_steps:
        return False
    try:
        GlobalTestPlanner.normalize_response(
            {'choices': [{'message': {'tool_calls': [{'function': {
                'name': 'submit_execution_plan',
                'arguments': json.dumps({'steps': planned_steps}),
            }}]}}]},
            environment_configuration_id,
            task_description,
            require_transition=True,
        )
    except (GlobalPlanError, TypeError, ValueError):
        return False
    return True


def extract_screenshot_sequence(artifacts):
    if not isinstance(artifacts, list):
        return []

    screenshot_paths = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get('type') not in {'screenshot', 'final_screenshot'}:
            continue
        path = artifact.get('path')
        if path:
            screenshot_paths.append(path)

    return screenshot_paths


def extract_step_info(step, step_index):
    """提取步骤信息，兼容 browser_use 风格对象和 planner_v2 字典结果。"""
    if isinstance(step, dict):
        return {
            'step': step_index,
            'action': step.get('action'),
            'status': step.get('status'),
            'element': step.get('element'),
            'thinking': step.get('thinking'),
            'duration_seconds': step.get('duration_seconds'),
            'error': step.get('error'),
            'output': step.get('output'),
        }


    step_info = {'step': step_index}
    if hasattr(step, 'action'):
        step_info['action'] = getattr(step, 'action')
    elif hasattr(step, 'model_output'):
        step_info['action'] = getattr(step, 'model_output')
    else:
        step_info['action'] = str(step)

    for key in ['status', 'element', 'thinking', 'duration_seconds', 'error', 'output']:
        if hasattr(step, key):
            step_info[key] = getattr(step, key)

    return step_info


def normalize_step_thinking(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if re.fullmatch(r'planner_v2 executed action=\s*', text):
        return None

    matched_action = re.fullmatch(r'planner_v2 executed action=\s*([a-z][a-z0-9_]*)\s*', text)
    if matched_action:
        return f'action={matched_action.group(1)}'

    return text


def normalize_planner_artifact_path(value):
    if value is None:
        return None

    text = str(value)
    text = re.sub(
        r'ai_testing/planner_v2/([A-Za-z0-9_]+)__[^/]+_(\d{14})/',
        r'ai_testing/planner_v2/\1_\2/',
        text,
    )
    text = re.sub(
        r'([A-Za-z0-9_]+)__[^/]+_step_(\d+)_completed\.png',
        r'\1_step_\2.png',
        text,
    )
    text = re.sub(
        r'([A-Za-z0-9_]+)__[^/]+_final\.png',
        r'\1_final.png',
        text,
    )
    text = re.sub(
        r'([A-Za-z0-9_]+)__[^/]+_report\.(jsonl|html)',
        r'\1_report.\2',
        text,
    )
    return text


def normalize_planner_payload(value):
    if isinstance(value, str):
        return normalize_planner_artifact_path(value)
    if isinstance(value, list):
        return [normalize_planner_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_planner_payload(item) for key, item in value.items()}
    return value


def extract_machine_action_name(step):
    if not isinstance(step, dict):
        return None

    for key in ['report_action', 'runtime_action', 'action']:
        candidate = str(step.get(key) or '').strip()
        if re.fullmatch(r'[a-z][a-z0-9_]*', candidate):
            return candidate
    return None


def build_step_thinking(step):
    if not isinstance(step, dict):
        return None

    normalized = normalize_step_thinking(step.get('thinking'))
    if normalized:
        return normalized

    source = str(step.get('source') or '').strip()
    action = extract_machine_action_name(step) or str(step.get('action') or '').strip()
    if source and action and action != '-':
        return f'source={source}; action={action}'
    if source:
        return f'source={source}'
    if action and action != '-':
        return f'action={action}'
    return None


def build_accessible_ai_project_queryset(user):
    return accessible_ai_project_queryset(user)


def build_accessible_environment_configuration_queryset(user):
    from apps.core.models import EnvironmentConfiguration

    if user is None or not getattr(user, 'is_authenticated', False):
        return EnvironmentConfiguration.objects.none()
    return EnvironmentConfiguration.objects.all()


def resolve_environment_configuration_from_task(task_description, user):
    text = str(task_description or '').strip().lower()
    configurations = build_accessible_environment_configuration_queryset(user)
    if not text:
        return configurations.filter(is_default=True).order_by('id').first()

    matches = []
    for configuration in configurations:
        aliases = {
            str(configuration.environment or '').strip().lower(),
            str(configuration.name or '').strip().lower(),
        }
        # Check the most specific alias first so the match length is deterministic
        # (a display name such as "sam 环境" outranks its bare environment code).
        for alias in sorted(aliases, key=len, reverse=True):
            if not alias:
                continue
            if re.fullmatch(r'[a-z0-9_-]+', alias):
                matched = re.search(rf'(?<![a-z0-9_@./-]){re.escape(alias)}(?![a-z0-9_@./-])', text)
            else:
                matched = alias in text
            if matched:
                matches.append((len(alias), configuration.id, configuration))
                break

    if not matches:
        return configurations.filter(is_default=True).order_by('id').first()
    matches.sort(key=lambda item: item[:2], reverse=True)
    best_length = matches[0][0]
    best_matches = [item for item in matches if item[0] == best_length]
    if len(best_matches) == 1:
        return best_matches[0][2]
    default_candidates = [item for item in best_matches if item[2].is_default]
    if default_candidates:
        return default_candidates[0][2]
    return None


def _is_relative_to(path, base_path):
    try:
        path.relative_to(base_path)
        return True
    except ValueError:
        return False

class AiProjectViewSet(viewsets.ModelViewSet):
    queryset = AiProject.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = AiProjectSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering = ['-created_at']

    def get_queryset(self):
        return build_accessible_ai_project_queryset(self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AICaseViewSet(viewsets.ModelViewSet):
    queryset = AICase.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = AICaseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project']
    search_fields = ['name', 'description', 'task_description']
    ordering = ['case_number', 'name']

    def get_queryset(self):
        accessible_projects = build_accessible_ai_project_queryset(self.request.user)
        return AICase.objects.filter(
            models.Q(project__in=accessible_projects)
            | models.Q(project__isnull=True, created_by=self.request.user)
        ).distinct()

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None, ai_case=None):
        """执行 AI 用例"""
        ai_case = ai_case or self.get_object()
        execution_mode = request.data.get('execution_mode', 'planner_v2')
        use_cache = parse_request_bool(request.data.get('use_cache'), default=True)
        force_replan = parse_request_bool(request.data.get('force_replan'), default=False)
        configuration_id = request.data.get('environment_configuration_id')
        if configuration_id is not None:
            try:
                configuration_id = int(configuration_id)
            except (TypeError, ValueError):
                return Response({'error': '设备 CLI 环境参数无效'}, status=status.HTTP_400_BAD_REQUEST)
            environment_configuration = build_accessible_environment_configuration_queryset(
                request.user,
            ).filter(id=configuration_id).first()
            if environment_configuration is None:
                return Response({'error': '设备 CLI 环境不存在或无访问权限'}, status=status.HTTP_403_FORBIDDEN)
        else:
            environment_configuration = resolve_environment_configuration_from_task(
                ai_case.task_description,
                request.user,
            )
        if environment_configuration is not None:
            has_configuration_access = build_accessible_environment_configuration_queryset(request.user).filter(
                id=environment_configuration.id,
            ).exists()
            if not has_configuration_access:
                return Response({'error': '设备 CLI 环境不存在或无访问权限'}, status=status.HTTP_403_FORBIDDEN)

        execution_record = launch_case_execution(
            ai_case,
            user=request.user,
            execution_mode=execution_mode,
            use_cache=use_cache,
            environment_configuration=environment_configuration,
            force_replan=force_replan,
        )

        return Response({
            'message': 'AI 用例开始执行',
            'execution_id': execution_record.id
        })

    @action(detail=False, methods=['post'])
    def batch_run(self, request):
        """批量启动 AI 用例执行。"""
        case_ids = request.data.get('case_ids')
        if not isinstance(case_ids, list) or not case_ids:
            return Response({'error': '请至少选择一个用例'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            normalized_case_ids = [int(case_id) for case_id in case_ids]
        except (TypeError, ValueError):
            return Response({'error': '用例 ID 参数无效'}, status=status.HTTP_400_BAD_REQUEST)

        if len(normalized_case_ids) != len(set(normalized_case_ids)):
            return Response({'error': '用例 ID 不能重复'}, status=status.HTTP_400_BAD_REQUEST)

        ai_cases = list(self.get_queryset().filter(id__in=normalized_case_ids))
        if len(ai_cases) != len(normalized_case_ids):
            return Response({'error': '部分用例不存在或无访问权限'}, status=status.HTTP_403_FORBIDDEN)

        configuration_id = request.data.get('environment_configuration_id')
        if configuration_id is not None:
            try:
                configuration_id = int(configuration_id)
            except (TypeError, ValueError):
                return Response({'error': '设备 CLI 环境参数无效'}, status=status.HTTP_400_BAD_REQUEST)
            if not build_accessible_environment_configuration_queryset(
                request.user,
            ).filter(id=configuration_id).exists():
                return Response({'error': '设备 CLI 环境不存在或无访问权限'}, status=status.HTTP_403_FORBIDDEN)

        execution_ids = []
        for ai_case in ai_cases:
            response = self.run(request, ai_case=ai_case)
            if response.status_code >= status.HTTP_400_BAD_REQUEST:
                return response
            execution_ids.append(response.data['execution_id'])

        return Response({
            'message': f'已启动 {len(execution_ids)} 个 AI 用例执行',
            'execution_ids': execution_ids,
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除当前用户有权访问的 AI 用例。"""
        case_ids = request.data.get('case_ids')
        if not isinstance(case_ids, list) or not case_ids:
            return Response({'error': '请至少选择一个用例'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            normalized_case_ids = [int(case_id) for case_id in case_ids]
        except (TypeError, ValueError):
            return Response({'error': '用例 ID 参数无效'}, status=status.HTTP_400_BAD_REQUEST)

        if len(normalized_case_ids) != len(set(normalized_case_ids)):
            return Response({'error': '用例 ID 不能重复'}, status=status.HTTP_400_BAD_REQUEST)

        ai_cases = self.get_queryset().filter(id__in=normalized_case_ids)
        if ai_cases.count() != len(normalized_case_ids):
            return Response({'error': '部分用例不存在或无访问权限'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            deleted_count, _ = ai_cases.delete()

        return Response({'deleted_count': deleted_count})

    @action(detail=True, methods=['post'], url_path='execute')
    def execute(self, request, pk=None):
        return self.run(request, pk=pk)

    def _process_gif_recording(self, execution_record, history):
        """GIF 录制归档已收敛到 execution.dispatch.process_gif_recording。"""
        process_gif_recording(execution_record)

    def _auto_mark_completed_tasks(self, execution_record):
        """
        自动标记已完成的任务
        通过分析执行历史和当前任务状态，自动标记那些已经执行但未被标记完成的任务

        注意：已移除统一标记逻辑，任务状态完全由AI智能体通过mark_task_complete控制
        - 执行成功时标记为completed
        - 执行失败时标记为failed
        - 跳过执行时标记为skipped
        - 未执行时标记为pending
        """
        try:
            # 记录初始状态
            initial_completed = 0
            initial_pending = 0
            initial_failed = 0
            initial_skipped = 0

            if execution_record.planned_tasks:
                execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                initial_completed = len([t for t in execution_record.planned_tasks if t.get('status') == 'completed'])
                initial_pending = len([t for t in execution_record.planned_tasks if t.get('status') == 'pending'])
                initial_failed = len([t for t in execution_record.planned_tasks if t.get('status') == 'failed'])
                initial_skipped = len([t for t in execution_record.planned_tasks if t.get('status') == 'skipped'])
                
                logger.info(f"📊 Task status summary: {initial_completed} completed, {initial_pending} pending, {initial_failed} failed, {initial_skipped} skipped")

            # 不再自动标记所有任务为完成
            # 任务状态完全由AI智能体通过mark_task_complete来控制
            logger.info("📋 Task statuses are controlled by AI agent via mark_task_complete action")

        except Exception as e:
            logger.warning(f"⚠️ Failed to auto-mark completed tasks: {e}")


# 全局停止信号字典 {execution_id: bool}

TERMINAL_TASK_STATUSES = {'completed', 'failed', 'skipped'}
ACTIVE_TASK_STATUSES = {'pending', 'in_progress'}


def sanitize_planned_tasks(planned_tasks):
    """清洗并标准化 planned_tasks，确保元素为 dict。"""
    if not planned_tasks:
        return []

    if not isinstance(planned_tasks, list):
        planned_tasks = [planned_tasks]

    flattened = []
    for item in planned_tasks:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)

    normalized = []
    for task in flattened:
        if isinstance(task, dict):
            normalized.append(task)
            continue
        if hasattr(task, 'model_dump'):
            try:
                dumped = task.model_dump()
                if isinstance(dumped, dict):
                    normalized.append(dumped)
                continue
            except Exception:
                continue
        if hasattr(task, '__dict__'):
            task_dict = dict(task.__dict__)
            if isinstance(task_dict, dict):
                normalized.append(task_dict)
    return normalized


def update_planned_task_status(planned_tasks, task_id, task_status):
    """更新子任务状态，返回是否命中任务。"""
    if not planned_tasks or task_id is None or not task_status:
        return False

    normalized_tasks = sanitize_planned_tasks(planned_tasks)
    if isinstance(planned_tasks, list):
        planned_tasks[:] = normalized_tasks

    normalized_status = str(task_status).strip().lower()
    for task in normalized_tasks:
        if str(task.get('id')) == str(task_id):
            task['status'] = normalized_status
            return True
    return False


def mark_first_active_task(planned_tasks, task_status):
    """在执行异常时为第一个未终态任务补一个状态。"""
    if not planned_tasks:
        return None

    normalized_tasks = sanitize_planned_tasks(planned_tasks)
    if isinstance(planned_tasks, list):
        planned_tasks[:] = normalized_tasks

    normalized_status = str(task_status).strip().lower()
    for task in normalized_tasks:
        if task.get('status', 'pending') in ACTIVE_TASK_STATUSES:
            task['status'] = normalized_status
            return task.get('id')
    return None


def summarize_planned_tasks(planned_tasks):
    """汇总子任务状态。"""
    summary = {
        'total': 0,
        'completed': 0,
        'failed': 0,
        'skipped': 0,
        'pending': 0,
        'in_progress': 0,
    }
    if not planned_tasks:
        return summary

    normalized_tasks = sanitize_planned_tasks(planned_tasks)
    if isinstance(planned_tasks, list):
        planned_tasks[:] = normalized_tasks

    summary['total'] = len(normalized_tasks)
    for task in normalized_tasks:
        task_status = task.get('status', 'pending')
        if task_status in summary:
            summary[task_status] += 1
        else:
            summary['pending'] += 1
    return summary


def resolve_execution_status(planned_tasks):
    """根据子任务实际状态推导整单状态。"""
    summary = summarize_planned_tasks(planned_tasks)

    if summary['total'] == 0:
        return 'inconclusive', summary
    if summary['failed'] > 0:
        return 'failed', summary
    if summary['pending'] > 0 or summary['in_progress'] > 0:
        return 'inconclusive', summary
    return 'passed', summary


def append_execution_summary(logs, summary):
    """把任务统计附加到日志中。"""
    if summary['total'] == 0:
        return logs
    return (
        f"{logs}\n[System] 子任务统计: 总数 {summary['total']}，"
        f"已完成 {summary['completed']}，失败 {summary['failed']}，"
        f"跳过 {summary['skipped']}，待处理 {summary['pending'] + summary['in_progress']}。"
    )


def is_infrastructure_failure(error_message: str) -> bool:
    """判断是否为模型/网络/初始化类故障，这类问题不应直接把首个子任务标失败。"""
    message = (error_message or '').lower()
    infra_markers = [
        'execution llm unavailable',
        'connection error',
        'timed out',
        'timeout',
        'api key',
        'authentication',
        'unauthorized',
        'forbidden',
        'rate limit',
        'service unavailable',
    ]
    return any(marker in message for marker in infra_markers)


class AIExecutionExperienceViewSet(viewsets.ModelViewSet):
    queryset = AIExecutionExperience.objects.all()
    serializer_class = AIExecutionExperienceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['project', 'ai_case', 'execution_record', 'status', 'review_status']
    ordering = ['-confidence', '-last_verified_at']

    def get_queryset(self):
        queryset = AIExecutionExperience.objects.filter(
            project__in=build_accessible_ai_project_queryset(self.request.user),
        ).select_related('project', 'ai_case', 'execution_record')
        review_scope = str(self.request.query_params.get('review_scope') or '').strip().lower()
        if review_scope == 'pending':
            return queryset.filter(review_status__in=['pending', 'auto_verified'])
        if review_scope == 'verified':
            return queryset.filter(status='verified', review_status='confirmed')
        return queryset

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        experience = self.get_object()
        experience.status = 'verified'
        experience.review_status = 'confirmed'
        experience.review_note = str(request.data.get('review_note') or '').strip()
        experience.confidence = max(experience.confidence, 0.95)
        experience.save(update_fields=['status', 'review_status', 'review_note', 'confidence', 'updated_at'])
        return Response(self.get_serializer(experience).data)

    def destroy(self, request, *args, **kwargs):
        experience = self.get_object()
        experience.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['delete'], url_path='clear')
    def clear(self, request):
        experiences = self.filter_queryset(self.get_queryset())
        deleted_count, _ = experiences.delete()
        return Response({'deleted_count': deleted_count})


class AIExecutionRecordViewSet(viewsets.ModelViewSet):
    """AI执行记录视图集"""
    queryset = AIExecutionRecord.objects.all()
    serializer_class = AIExecutionRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['project', 'ai_case', 'status']
    ordering = ['-start_time']

    def get_queryset(self):
        accessible_projects = build_accessible_ai_project_queryset(self.request.user)
        queryset = AIExecutionRecord.objects.filter(
            models.Q(project__in=accessible_projects)
            | models.Q(project__isnull=True, executed_by=self.request.user)
        ).distinct()

        query_params = getattr(self.request, 'query_params', None)
        if query_params is None:
            query_params = getattr(self.request, 'GET', {})
        project_scope = str(query_params.get('project_scope') or '').strip().lower()
        if project_scope == 'unarchived':
            return queryset.filter(project__isnull=True)

        return queryset

    @action(detail=False, methods=['get'], url_path='learning-metrics')
    def learning_metrics(self, request):
        record_queryset = self.get_queryset()
        accessible_projects = build_accessible_ai_project_queryset(request.user)
        experiences = AIExecutionExperience.objects.filter(project__in=accessible_projects)
        project_id = request.query_params.get('project')
        normalized_project_id = None
        if project_id:
            try:
                normalized_project_id = int(project_id)
            except (TypeError, ValueError):
                return Response({'error': 'project 参数无效'}, status=status.HTTP_400_BAD_REQUEST)
            record_queryset = record_queryset.filter(project_id=normalized_project_id)
            experiences = experiences.filter(project_id=normalized_project_id)
        records = list(record_queryset.only('ai_case_id', 'status', 'cache_stats', 'start_time').order_by('start_time'))

        first_records = {}
        cache_hits = 0
        experience_hits = 0
        experience_writes = 0
        revalidated = 0
        stale_skips = 0
        plan_cache_hits = 0
        for record in records:
            if record.ai_case_id and record.ai_case_id not in first_records:
                first_records[record.ai_case_id] = record.status
            stats = record.cache_stats if isinstance(record.cache_stats, dict) else {}
            cache_hits += int(stats.get('hit') or 0)
            experience_hits += int(stats.get('experience_hit') or 0)
            experience_writes += int(stats.get('experience_write') or 0)
            revalidated += int(stats.get('revalidated') or 0)
            stale_skips += int(stats.get('stale_skip') or 0)
            plan_cache_hits += int(stats.get('plan_cache_hit') or 0)

        from django.utils import timezone as dj_timezone

        from .models import AIActionCacheEntry

        action_cache = AIActionCacheEntry.objects.all()
        if normalized_project_id is not None:
            action_cache = action_cache.filter(project_id=normalized_project_id)
        now = dj_timezone.now()
        first_run_total = len(first_records)
        first_run_passed = sum(status == 'passed' for status in first_records.values())
        total_records = len(records)
        passed_records = sum(record.status == 'passed' for record in records)
        return Response({
            'executions': {
                'total': total_records,
                'passed': passed_records,
                'pass_rate': round(passed_records / total_records, 4) if total_records else 0,
                'first_run_total': first_run_total,
                'first_run_passed': first_run_passed,
                'first_run_pass_rate': round(first_run_passed / first_run_total, 4) if first_run_total else 0,
            },
            'learning': {
                'experience_total': experiences.count(),
                'experience_active': experiences.filter(status='verified', review_status='confirmed').count(),
                'experience_confirmed': experiences.filter(review_status='confirmed', status='verified').count(),
                'experience_invalid': experiences.filter(status='invalid').count(),
                'cache_hits': cache_hits,
                'experience_hits': experience_hits,
                'experience_writes': experience_writes,
                'revalidated': revalidated,
                'stale_skips': stale_skips,
                'plan_cache_hits': plan_cache_hits,
                # What the runtime can actually reuse: verified and confident, regardless of human review.
                'experience_reusable': experiences.filter(status='verified', confidence__gte=0.7).count(),
                'action_cache_entries': action_cache.filter(expires_at__gt=now).count(),
                'action_cache_expired': action_cache.filter(expires_at__lte=now).count(),
            },
        })

    def _execution_record_artifact_paths(self, execution_record):
        paths = set()

        gif_path = str(getattr(execution_record, 'gif_path', '') or '').strip()
        if gif_path:
            paths.add(gif_path)

        for screenshot in getattr(execution_record, 'screenshots_sequence', []) or []:
            screenshot_path = str(screenshot or '').strip()
            if screenshot_path:
                paths.add(screenshot_path)

        for artifact in getattr(execution_record, 'artifacts', []) or []:
            if not isinstance(artifact, dict):
                continue
            artifact_path = str(artifact.get('path') or '').strip()
            if artifact_path:
                paths.add(artifact_path)

        return sorted(paths)

    def _resolve_execution_artifact_path(self, artifact_path):
        raw_path = str(artifact_path or '').strip()
        if not raw_path:
            return None

        media_root = Path(settings.MEDIA_ROOT).resolve()
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = (media_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if not _is_relative_to(candidate, media_root):
            logger.warning('skip deleting artifact outside MEDIA_ROOT: %s', candidate)
            return None

        return candidate

    def _delete_execution_record_artifacts(self, execution_record):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        removable_dirs = set()

        for artifact_path in self._execution_record_artifact_paths(execution_record):
            resolved_path = self._resolve_execution_artifact_path(artifact_path)
            if resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
                continue

            removable_dirs.add(resolved_path.parent)
            resolved_path.unlink(missing_ok=True)

        for directory in sorted(removable_dirs, key=lambda item: len(item.parts), reverse=True):
            current = directory
            while _is_relative_to(current, media_root) and current != media_root:
                try:
                    current.rmdir()
                except OSError:
                    break
                current = current.parent

    def perform_destroy(self, instance):
        self._delete_execution_record_artifacts(instance)
        instance.delete()

    @action(detail=False, methods=['post'])
    def batch_delete(self, request):
        """批量删除AI执行记录"""
        try:
            ids = request.data.get('ids', [])

            # 验证ids参数
            if not ids:
                return Response({'error': '请选择要删除的记录'}, status=status.HTTP_400_BAD_REQUEST)

            # 确保ids是列表
            if not isinstance(ids, list):
                return Response({'error': 'ids参数格式错误，应为数组'}, status=status.HTTP_400_BAD_REQUEST)

            # 只能删除自己有权限的项目下的记录
            queryset = self.get_queryset()
            records_to_delete = queryset.filter(id__in=ids)

            # 检查是否有权限删除这些记录
            if not records_to_delete.exists():
                return Response({'error': '未找到可删除的记录或没有权限删除'}, status=status.HTTP_404_NOT_FOUND)

            # 获取可删除记录的ID列表，避免对distinct()后的queryset调用delete()
            deletable_records = list(records_to_delete)
            deleted_count = 0
            for record in deletable_records:
                self._delete_execution_record_artifacts(record)
                record.delete()
                deleted_count += 1

            return Response({'message': f'成功删除 {deleted_count} 条记录', 'deleted_count': deleted_count})
        except Exception as e:
            logger.error(f"批量删除AI执行记录失败: {str(e)}", exc_info=True)
            return Response({'error': f'批量删除失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='run_adhoc')
    def run_adhoc(self, request):
        """执行临时 AI 任务"""
        project_id = request.data.get('project_id')
        task_description = request.data.get('task_description')
        execution_mode = request.data.get('execution_mode', 'planner_v2')  # 默认 Planner 模式
        enable_gif = request.data.get('enable_gif', True)  # GIF录制开关，默认开启
        case_mode = request.data.get('case_mode', 'freeform')
        task_steps = request.data.get('task_steps') or []
        use_cache = parse_request_bool(request.data.get('use_cache'), default=True)
        force_replan = parse_request_bool(request.data.get('force_replan'), default=False)
        environment_configuration_id = request.data.get('environment_configuration_id')

        if not task_description:
            return Response({'error': '缺少任务描述参数'}, status=status.HTTP_400_BAD_REQUEST)

        # 获取项目对象（如果提供了project_id）
        project = None
        if project_id:
            try:
                project = AiProject.objects.get(id=project_id)
            except AiProject.DoesNotExist:
                return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

        environment_configuration = None
        if environment_configuration_id is not None:
            environment_configuration = build_accessible_environment_configuration_queryset(request.user).filter(
                id=environment_configuration_id,
            ).first()
            if environment_configuration is None:
                return Response({'error': '设备 CLI 环境不存在或无访问权限'}, status=status.HTTP_403_FORBIDDEN)
        else:
            environment_configuration = resolve_environment_configuration_from_task(
                task_description,
                request.user,
            )

        # 创建执行记录
        execution_record = AIExecutionRecord.objects.create(
            project=project,
            environment_configuration=environment_configuration,
            case_name="Adhoc Task",
            task_description=task_description,
            execution_mode=execution_mode,
            status='running',
            executed_by=request.user,
            logs="正在分析任务...\n"
        )

        dispatch_ai_execution(execution_record.id, {
            'task_description': task_description,
            'execution_mode': execution_mode,
            'enable_gif': parse_request_bool(enable_gif, default=True),
            'case_name': task_description[:50] if task_description else 'Adhoc Task',
            'case_mode': case_mode,
            'task_steps': task_steps,
            'use_cache': use_cache,
            'force_replan': force_replan,
            'execution_user_id': request.user.id,
            'ai_project_id': project.id if project else None,
            'ai_case_id': None,
        })

        return Response({
            'message': 'AI 任务开始执行',
            'execution_id': execution_record.id
        })

    @action(detail=True, methods=['post'], url_path='stop')
    def stop_task(self, request, pk=None):
        """停止正在执行的任务（对任意进程/worker 生效）。"""
        try:
            execution_id = int(pk)
            record = self.get_object()
            if request_stop(execution_id):
                return Response({'message': '已发送停止信号'})
            if execution_id in STOP_SIGNALS:
                STOP_SIGNALS[execution_id] = True
                return Response({'message': '已发送停止信号'})
            if record.status == 'running':
                return Response({'message': '已发送停止信号'})
            return Response({'message': '任务不在运行中'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_task_statistics(self, execution_record):
        tasks = execution_record.planned_tasks or []
        stats = {
            'total': len(tasks),
            'completed': 0,
            'pending': 0,
            'failed': 0,
            'skipped': 0
        }

        for task in tasks:
            task_status = str(task.get('status', 'pending')).strip().lower()
            if task_status in ('completed', 'passed', 'success'):
                stats['completed'] += 1
            elif task_status in ('failed', 'error'):
                stats['failed'] += 1
            elif task_status in ('skipped', 'stopped'):
                stats['skipped'] += 1
            else:
                stats['pending'] += 1

        return stats

    def _format_duration(self, duration):
        duration = float(duration or 0)
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        if minutes > 0:
            return f'{minutes}分{seconds}秒'
        return f'{seconds}秒'

    def _status_display(self, status_value):
        status_map = {
            'passed': '成功',
            'failed': '失败',
            'inconclusive': '证据不足',
            'running': '执行中',
            'pending': '等待中',
            'stopped': '已停止'
        }
        return status_map.get(str(status_value or '').strip().lower(), str(status_value or '-'))

    def _status_color(self, status_value):
        color_map = {
            'passed': 'success',
            'failed': 'danger',
            'inconclusive': 'warning',
            'running': 'warning',
            'pending': 'info',
            'stopped': 'info'
        }
        return color_map.get(str(status_value or '').strip().lower(), 'info')

    def _extract_step_action_text(self, step):
        if isinstance(step, dict):
            for key in ['step_description', 'description', 'task_description']:
                candidate = str(step.get(key) or '').strip()
                if candidate:
                    return candidate

        action = step.get('action') if isinstance(step, dict) else None
        if isinstance(action, str):
            return action
        if isinstance(action, dict):
            action_name = next(iter(action.keys()), None)
            action_params = action.get(action_name, {})
            if isinstance(action_params, dict) and action_params:
                summary = ', '.join(f'{k}={v}' for k, v in list(action_params.items())[:2])
                return f'{action_name}: {summary}' if summary else str(action_name or '-')
            return str(action_name or '-')
        if isinstance(action, list) and action:
            first_action = action[0]
            if isinstance(first_action, dict):
                action_name = next(iter(first_action.keys()), None)
                return str(action_name or '-')
            return str(first_action)
        return str(action or '-')

    def _extract_step_action_name(self, step):
        action = step.get('action') if isinstance(step, dict) else None
        if isinstance(action, dict):
            return str(next(iter(action.keys()), 'other'))
        if isinstance(action, list) and action and isinstance(action[0], dict):
            return str(next(iter(action[0].keys()), 'other'))
        if isinstance(action, str):
            lowered = action.lower()
            for keyword in ['click', 'input', 'navigate', 'scroll', 'wait', 'done', 'open_tab', 'search_google']:
                if keyword in lowered:
                    return keyword
        return 'other'

    def _extract_step_duration(self, step):
        if not isinstance(step, dict):
            return None
        for key in ['duration', 'duration_seconds', 'elapsed', 'execution_time']:
            value = step.get(key)
            if value is None:
                continue
            try:
                return round(float(value), 2)
            except (TypeError, ValueError):
                continue
        return None

    def _extract_errors(self, execution_record):
        errors = []
        for line in str(execution_record.logs or '').splitlines():
            normalized = line.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if any(token in lowered for token in ['执行出错', '异常', 'error', 'failed', 'warning', 'not found']):
                error_type = 'warning' if 'warning' in lowered else 'error'
                errors.append({'type': error_type, 'message': normalized})
        return errors[-20:]

    def _merge_report_step(self, recorded_step, case_report_step):
        merged = dict(recorded_step or {})
        planner_step = case_report_step if isinstance(case_report_step, dict) else {}

        step_description = str(planner_step.get('step_description') or planner_step.get('description') or '').strip()
        if step_description and not merged.get('step_description'):
            merged['step_description'] = step_description

        report_action = str(planner_step.get('action') or '').strip()
        if report_action:
            merged['report_action'] = report_action
        if not merged.get('source') and planner_step.get('source'):
            merged['source'] = planner_step.get('source')

        step_screenshot = normalize_planner_artifact_path(
            merged.get('step_screenshot') or planner_step.get('step_screenshot')
        )
        if step_screenshot:
            merged['step_screenshot'] = step_screenshot

        fail_screenshot = normalize_planner_artifact_path(planner_step.get('fail_screenshot'))
        if fail_screenshot:
            merged['fail_screenshot'] = fail_screenshot

        if not merged.get('error') and planner_step.get('error'):
            merged['error'] = planner_step.get('error')

        return merged

    def _report_step_records(self, execution_record):
        recorded_steps = execution_record.steps_completed or []
        planner_trace = execution_record.planner_trace or {}
        case_report = planner_trace.get('case_report') if isinstance(planner_trace, dict) else None
        fallback_steps = case_report.get('steps') if isinstance(case_report, dict) else None
        if not isinstance(fallback_steps, list):
            fallback_steps = []

        if recorded_steps:
            normalized_recorded_steps = []
            for index, step in enumerate(recorded_steps):
                if not isinstance(step, dict):
                    continue
                planner_step = fallback_steps[index] if index < len(fallback_steps) else {}
                normalized_recorded_steps.append(self._merge_report_step(step, planner_step))
            return normalized_recorded_steps

        if not fallback_steps:
            return []

        normalized_steps = []
        for step in fallback_steps:
            if not isinstance(step, dict):
                continue
            normalized_steps.append(self._merge_report_step({
                'action': step.get('step_description') or step.get('action') or '-',
                'status': 'completed' if step.get('result') else 'failed',
                'thinking': build_step_thinking(step),
                'duration_seconds': None,
                'error': step.get('error'),
                'element': None,
            }, step))
        return normalized_steps

    def _execution_audit_summary(self, execution_record):
        plan_revisions = getattr(execution_record, 'plan_revisions', None)
        if plan_revisions is None:
            return None
        revisions = list(plan_revisions.prefetch_related(
            'steps__attempts__evidence_artifacts',
            'steps__assertion_results__evidence_artifacts',
            'quality_gate_results',
        ).order_by('revision_number'))
        if not revisions:
            return None
        revision = revisions[-1]

        quality_gate = revision.quality_gate_results.order_by('-evaluation_number').first()
        return {
            'plan_revision': revision.revision_number,
            'plan_hash': revision.plan_hash,
            'quality_gate': {
                'status': quality_gate.status,
                'details': quality_gate.details,
                'evaluated_at': quality_gate.evaluated_at.isoformat(),
            } if quality_gate is not None else None,
            'revision_history': [
                {
                    'revision_number': item.revision_number,
                    'reason': item.reason,
                    'plan_hash': item.plan_hash,
                    'created_at': item.created_at.isoformat(),
                    'quality_gate_status': (
                        item.quality_gate_results.order_by('-evaluation_number').first().status
                        if item.quality_gate_results.exists() else None
                    ),
                }
                for item in revisions
            ],
            'steps': [
                {
                    'step_key': step.step_key,
                    'intent': step.intent,
                    'status': step.status,
                    'attempts': [
                        {
                            'attempt_number': attempt.attempt_number,
                            'action': attempt.action,
                            'status': attempt.status,
                            'evidence': [
                                {
                                    'artifact_type': artifact.artifact_type,
                                    'content_hash': artifact.content_hash,
                                    'captured_at': artifact.captured_at.isoformat(),
                                }
                                for artifact in attempt.evidence_artifacts.all()
                            ],
                        }
                        for attempt in step.attempts.all()
                    ],
                    'assertions': [
                        {
                            'status': assertion.status,
                            'assertion': assertion.assertion,
                            'actual': assertion.actual,
                            'evidence_hashes': [artifact.content_hash for artifact in assertion.evidence_artifacts.all()],
                        }
                        for assertion in step.assertion_results.all()
                    ],
                }
                for step in revision.steps.all()
            ],
        }

    def _build_execution_report(self, execution_record, report_type='summary'):
        stats = self._get_task_statistics(execution_record)
        report_steps = self._report_step_records(execution_record)
        total_steps = len(report_steps)
        completion_rate = round((stats['completed'] / stats['total']) * 100, 2) if stats['total'] else (100 if execution_record.status == 'passed' else 0)

        overview = {
            'status': self._status_display(execution_record.status),
            'status_color': self._status_color(execution_record.status),
            'duration_formatted': self._format_duration(execution_record.duration),
            'completion_rate': completion_rate,
            'total_steps': total_steps,
            'execution_mode': execution_record.execution_mode,
            'execution_mode_display': 'Hermes' if execution_record.execution_mode == 'hermes' else 'Browser'
        }

        timeline = []
        for task in execution_record.planned_tasks or []:
            task_status = str(task.get('status', 'pending')).strip().lower()
            timeline.append({
                'id': task.get('id'),
                'description': task.get('description', ''),
                'status': task_status,
                'status_display': self._status_display(task_status)
            })

        detailed_steps = []
        step_durations = []
        for index, step in enumerate(report_steps, start=1):
            action_text = self._extract_step_action_text(step if isinstance(step, dict) else {})
            step_status = str((step or {}).get('status', 'completed')) if isinstance(step, dict) else 'completed'
            duration = self._extract_step_duration(step)
            if duration is not None:
                step_durations.append(duration)
            detailed_steps.append({
                'step_number': index,
                'status': step_status,
                'action': action_text,
                'element': (step or {}).get('element') if isinstance(step, dict) else None,
                'thinking': build_step_thinking(step if isinstance(step, dict) else {}),
                'output': (step or {}).get('output') if isinstance(step, dict) else None,
                'duration': duration
            })

        action_distribution = {}
        for step in report_steps:
            action_name = self._extract_step_action_name(step if isinstance(step, dict) else {})
            action_distribution[action_name] = action_distribution.get(action_name, 0) + 1

        metrics = None
        bottlenecks = []
        recommendations = []
        if step_durations:
            avg_duration = round(sum(step_durations) / len(step_durations), 2)
            max_duration = round(max(step_durations), 2)
            min_duration = round(min(step_durations), 2)
            metrics = {
                'avg_step_duration': avg_duration,
                'max_step_duration': max_duration,
                'min_step_duration': min_duration
            }
            for step in detailed_steps:
                if step.get('duration') is not None and avg_duration > 0 and step['duration'] > avg_duration * 1.5:
                    bottlenecks.append({
                        'step_number': step['step_number'],
                        'action': step['action'],
                        'duration': step['duration'],
                        'slower_than_avg_by': round(((step['duration'] - avg_duration) / avg_duration) * 100, 2)
                    })
            bottlenecks = bottlenecks[:10]
            if bottlenecks:
                recommendations.append(f'发现 {len(bottlenecks)} 个相对耗时较高的步骤，建议优先检查对应页面响应与元素定位稳定性')
            if avg_duration >= 5:
                recommendations.append('平均步骤耗时偏高，建议检查网络速度、页面加载性能或等待策略')

        if stats['failed'] > 0:
            recommendations.append('存在失败任务，建议优先查看详细步骤中的失败动作与执行日志')
        if not recommendations:
            recommendations.append('执行过程整体稳定，建议继续关注关键步骤的成功率与耗时变化')

        report = {
            'overview': overview,
            'statistics': stats,
            'timeline': timeline,
            'detailed_steps': detailed_steps,
            'errors': self._extract_errors(execution_record),
            'metrics': metrics,
            'action_distribution': action_distribution,
            'bottlenecks': bottlenecks,
            'recommendations': recommendations,
            'gif_path': execution_record.gif_path,
            'planner_trace': normalize_planner_payload(execution_record.planner_trace or {}),
            'artifacts': normalize_planner_payload(execution_record.artifacts or []),
            'cache_stats': execution_record.cache_stats or {},
            'execution_audit': self._execution_audit_summary(execution_record),
            'experience_revalidations': [
                {
                    'step_description': experience.step_description,
                    'status': experience.status,
                    'confidence': experience.confidence,
                    'plan_revision': experience.last_verified_plan_revision,
                    'attempt': experience.last_verified_attempt,
                    'evidence_hashes': experience.last_verified_evidence_hashes,
                    'verified_at': experience.last_verified_at.isoformat() if experience.last_verified_at else None,
                }
                for experience in execution_record.experiences.all()
            ] if getattr(execution_record, 'experiences', None) is not None else [],
        }

        if report_type == 'summary':
            return report
        if report_type == 'detailed':
            return report
        if report_type == 'performance':
            return report
        return report

    @action(detail=True, methods=['get'], url_path='report')
    def report(self, request, pk=None):
        execution_record = self.get_object()
        report_type = request.query_params.get('report_type', 'summary')
        report_data = self._build_execution_report(execution_record, report_type)
        return Response({
            'success': True,
            'data': report_data
        })

    @action(detail=True, methods=['get'], url_path='export_pdf')
    def export_pdf(self, request, pk=None):
        execution_record = self.get_object()
        report_type = request.query_params.get('report_type', 'summary')
        report_data = self._build_execution_report(execution_record, report_type)
        report_data['execution_details'] = {
            'case_name': execution_record.case_name,
            'execution_mode': execution_record.execution_mode,
            'task_description': execution_record.task_description,
            'start_time': execution_record.start_time.isoformat() if execution_record.start_time else None,
            'end_time': execution_record.end_time.isoformat() if execution_record.end_time else None,
        }

        try:
            from apps.ui_automation.pdf_generator import AIReportPDFGenerator

            generator = AIReportPDFGenerator(report_data, report_type=report_type, report_category='ai_testing')
            pdf_buffer = generator.generate()
            pdf_bytes = pdf_buffer.getvalue()
        except Exception as e:
            logger.error(f'导出 AI 测试 PDF 失败: {e}', exc_info=True)
            return Response({'success': False, 'error': f'导出PDF失败: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f'ai_execution_report_{execution_record.id}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _process_gif_recording(self, execution_record, history):
        """GIF 录制归档已收敛到 execution.dispatch.process_gif_recording。"""
        process_gif_recording(execution_record)

    def _auto_mark_completed_tasks(self, execution_record):
        return AICaseViewSet._auto_mark_completed_tasks(self, execution_record)
