import logging
import threading
import os
import re
import json
from pathlib import Path
from django.conf import settings
from asgiref.sync import sync_to_async
from django.db import connection, DatabaseError, transaction
from django.utils import timezone
from django.db import models
from django.http import HttpResponse
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import AiProject, AICase, AIExecutionExperience, AIExecutionRecord
from .serializers import AiProjectSerializer, AICaseSerializer, AIExecutionExperienceSerializer, AIExecutionRecordSerializer
from .ai_testing import run_full_process_sync
from .global_planner import GlobalPlanError, GlobalTestPlanner
from .alpha.access import accessible_ai_project_queryset
from .execution.plan_persistence import persist_execution_plan
from .execution.quality_gate_persistence import evaluate_execution_quality_gate

logger = logging.getLogger(__name__)

# 全局字典，用于存储停止信号
STOP_SIGNALS = {}


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
            {'choices': [{'message': {'content': json.dumps({'steps': planned_steps})}}]},
            environment_configuration_id,
            task_description,
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
        for alias in aliases:
            if not alias:
                continue
            if re.fullmatch(r'[a-z0-9_-]+', alias):
                matched = re.search(rf'(?<![a-z0-9_-]){re.escape(alias)}(?![a-z0-9_-])', text)
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
    return best_matches[0][2] if len(best_matches) == 1 else None


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

        # 创建执行记录
        execution_record = AIExecutionRecord.objects.create(
            project=ai_case.project,
            ai_case=ai_case,
            environment_configuration=environment_configuration,
            case_name=ai_case.name,
            task_description=ai_case.task_description,
            execution_mode=execution_mode,
            status='running',
            executed_by=request.user,
            logs="正在分析任务...\n"
        )

        # 异步执行
        import threading
        import os
        from asgiref.sync import sync_to_async
        from django.db import connection, DatabaseError
        from .ai_testing import run_full_process_sync

        def run_task():
            # 注册停止信号
            STOP_SIGNALS[execution_record.id] = False

            # 关键修复：关闭旧连接，避免子线程共享主线程的连接
            try:
                connection.close()
            except:
                pass

            # 设置环境变量，允许在后台线程中使用同步 ORM
            os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

            def safe_save(record, update_fields=None, max_retries=3):
                """安全的保存方法，带有重试机制"""
                for attempt in range(max_retries):
                    try:
                        record.save(update_fields=update_fields)
                        return True
                    except (DatabaseError, Exception) as e:
                        error_str = str(e)
                        # 检查是否是MySQL连接错误
                        if '2006' in error_str or 'MySQL server has gone away' in error_str or '0' == error_str:
                            if attempt < max_retries - 1:
                                logger.warning(f"数据库连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                                # 关闭旧连接并重试
                                try:
                                    connection.close()
                                except:
                                    pass
                                import time
                                time.sleep(0.5)  # 等待一下再重试
                                continue
                            else:
                                logger.error(f"数据库保存失败，已达最大重试次数: {e}")
                                raise
                        else:
                            # 其他错误直接抛出
                            logger.error(f"数据库保存失败: {e}")
                            raise
                return False

            try:
                def should_stop():
                    return STOP_SIGNALS.get(execution_record.id, False)

                async def on_analysis_complete(planned_tasks):
                    execution_record.planned_tasks = sanitize_planned_tasks(planned_tasks)
                    await sync_to_async(persist_execution_plan)(
                        execution_record.id,
                        ai_case.task_description,
                        execution_record.planned_tasks,
                    )
                    execution_record.logs += "任务分析完成，开始执行...\n"
                    await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks', 'logs'])

                async def on_step_update(step_info):
                    try:
                        # 处理日志
                        if step_info.get('type') == 'log':
                            content = step_info.get('content')
                            if content:
                                execution_record.logs += content
                                await sync_to_async(safe_save)(execution_record, update_fields=['logs'])
                            return

                        # 处理任务状态
                        task_id = step_info.get('task_id')
                        status = step_info.get('status')
                        if task_id and status:
                            execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                            updated = update_planned_task_status(
                                execution_record.planned_tasks,
                                task_id,
                                status
                            )
                            if updated:
                                await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks'])
                    except Exception as e:
                        logger.error(f"更新步骤状态失败: {e}")

                use_persisted_freeform_plan = (
                    ai_case.case_mode == 'freeform'
                    and has_canonical_freeform_plan(
                        ai_case.planned_steps,
                        environment_configuration.id if environment_configuration else None,
                        ai_case.task_description,
                    )
                )
                if ai_case.case_mode == 'freeform' and ai_case.planned_steps and not use_persisted_freeform_plan:
                    execution_record.logs += '[planner_v2] Ignored legacy persisted plan that does not meet the current assertion and capability contract.\n'
                    safe_save(execution_record, update_fields=['logs'])
                runtime_task_steps = (
                    ai_case.planned_steps
                    if ai_case.case_mode == 'freeform' and ai_case.planned_steps
                    else ai_case.task_steps
                )

                history = run_full_process_sync(
                    ai_case.task_description,
                    analysis_callback=on_analysis_complete,
                    step_callback=on_step_update,
                    should_stop=should_stop,
                    execution_mode=execution_mode,
                    enable_gif=(execution_mode == 'text'),
                    case_name=ai_case.name,
                    case_mode='hybrid' if use_persisted_freeform_plan else ai_case.case_mode,
                    task_steps=runtime_task_steps,
                    use_cache=use_cache,
                    execution_user_id=request.user.id,
                    environment_configuration=environment_configuration,
                    ai_project_id=ai_case.project_id,
                    execution_record_id=execution_record.id,
                    ai_case_id=ai_case.id,
                )

                # 检查是否是手动停止
                if should_stop():
                    execution_record.status = 'stopped'
                    execution_record.logs += "\n[System] 任务已由用户停止。"
                else:
                    execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                    quality_gate_result = evaluate_execution_quality_gate(execution_record.id)
                    if quality_gate_result is None:
                        execution_record.status, task_summary = resolve_execution_status(execution_record.planned_tasks)
                    else:
                        execution_record.status = quality_gate_result.status
                        task_summary = summarize_planned_tasks(execution_record.planned_tasks)
                    if execution_record.status == 'passed':
                        execution_record.logs += "\n执行完成。"
                    elif execution_record.status == 'inconclusive':
                        execution_record.logs += "\n执行结束，但计划为空或仍有未完成子任务，无法证明通过。"
                    else:
                        execution_record.logs += "\n执行结束，但存在未完成或失败的子任务。"
                    logger.info(
                        "🏁 Task completion summary: "
                        f"{task_summary['completed']}/{task_summary['total']} completed, "
                        f"{task_summary['failed']} failed, "
                        f"{task_summary['pending'] + task_summary['in_progress']} pending"
                    )

                execution_record.end_time = timezone.now()
                execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()

                # 格式化 history 为日志 (如果不是停止状态)
                steps = []
                if history:
                    if hasattr(history, 'steps'):
                        steps = [extract_step_info(s, i) for i, s in enumerate(history.steps)]
                    if hasattr(history, 'planner_trace'):
                        execution_record.planner_trace = history.planner_trace or {}
                    if hasattr(history, 'artifacts'):
                        execution_record.artifacts = history.artifacts or []
                        execution_record.screenshots_sequence = extract_screenshot_sequence(execution_record.artifacts)
                    if hasattr(history, 'cache_stats'):
                        execution_record.cache_stats = history.cache_stats or {}

                execution_record.steps_completed = steps

                if execution_record.planned_tasks:
                    execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                    execution_record.logs = append_execution_summary(
                        execution_record.logs,
                        summarize_planned_tasks(execution_record.planned_tasks)
                    )

                # 处理GIF录制文件
                if execution_record.execution_mode == 'text':
                    self._process_gif_recording(execution_record, history)

                safe_save(execution_record)

            except Exception as e:
                error_message = str(e)
                logger.error(f"AI 执行线程异常: {error_message}", exc_info=True)
                execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                current_summary = summarize_planned_tasks(execution_record.planned_tasks)
                failed_task_id = None if is_infrastructure_failure(error_message) else mark_first_active_task(execution_record.planned_tasks, 'failed')
                execution_record.status = 'failed'
                if 'Execution LLM unavailable' in error_message:
                    execution_record.logs += f"\n执行出错: AI 执行模型连接失败。{error_message}"
                else:
                    execution_record.logs += f"\n执行出错: {error_message}"
                if failed_task_id is not None:
                    execution_record.logs += f"\n[System] 子任务 {failed_task_id} 已自动标记为失败。"

                execution_record.end_time = timezone.now()
                execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()
                execution_record.logs = append_execution_summary(
                    execution_record.logs,
                    summarize_planned_tasks(execution_record.planned_tasks)
                )
                try:
                    safe_save(execution_record)
                except:
                    # 如果保存失败，至少尝试保存基本信息
                    logger.error(f"保存失败状态时出错: {e}")
                    pass
            finally:
                # 清理停止信号
                if execution_record.id in STOP_SIGNALS:
                    del STOP_SIGNALS[execution_record.id]

        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()

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
        """
        处理GIF录制文件
        在执行完成后查找生成的GIF文件并保存路径到数据库
        """
        try:
            import os
            from django.conf import settings
            from datetime import datetime

            # browser-use 默认生成的GIF文件名（固定为agent_history.gif）
            default_gif_path = os.path.join(os.getcwd(), 'agent_history.gif')

            # 如果找到GIF文件，移动到media/ai_recording目录并重命名
            if os.path.exists(default_gif_path):
                import shutil

                # 创建录制文件目录 - 使用配置文件中的路径
                gif_dir = os.path.join(settings.MEDIA_ROOT, settings.ALLURE_AI_RECORDING)
                os.makedirs(gif_dir, exist_ok=True)

                # 生成新的文件名：用例名称+年月日时分秒
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                # 清理用例名称中的非法字符
                safe_case_name = "".join(
                    [c if c.isalnum() or c in (' ', '_', '-') else '_' for c in execution_record.case_name])
                new_gif_filename = f"{safe_case_name}_{timestamp}.gif"
                new_gif_path = os.path.join(gif_dir, new_gif_filename)

                # 移动并重命名文件
                shutil.move(default_gif_path, new_gif_path)

                # 保存相对路径到数据库（使用正斜杠，确保跨平台兼容）- 使用配置文件中的路径
                # 注意：不要包含 'media/' 前缀，因为 MEDIA_URL 已经是 '/media/'
                relative_path = f'{settings.ALLURE_AI_RECORDING}/{new_gif_filename}'
                execution_record.gif_path = relative_path

                logger.info(f"✅ GIF recording saved to: {relative_path}")
            else:
                logger.warning(f"⚠️ GIF file not found at: {default_gif_path}")
        except Exception as e:
            logger.error(f"❌ Error moving GIF file: {e}")
            logger.warning(f"⚠️ Failed to process GIF recording: {e}")

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
STOP_SIGNALS = {}

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
        for record in records:
            if record.ai_case_id and record.ai_case_id not in first_records:
                first_records[record.ai_case_id] = record.status
            stats = record.cache_stats if isinstance(record.cache_stats, dict) else {}
            cache_hits += int(stats.get('hit') or 0)
            experience_hits += int(stats.get('experience_hit') or 0)
            experience_writes += int(stats.get('experience_write') or 0)
            revalidated += int(stats.get('revalidated') or 0)

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

        # 异步执行
        import threading
        import os
        from asgiref.sync import sync_to_async
        from django.db import connection, DatabaseError
        from .ai_testing import run_full_process_sync

        def run_task():
            # 注册停止信号
            STOP_SIGNALS[execution_record.id] = False

            # 关键修复：关闭旧连接，避免子线程共享主线程的连接
            try:
                connection.close()
            except:
                pass

            # 设置环境变量，允许在后台线程中使用同步 ORM
            os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

            def safe_save(record, update_fields=None, max_retries=3):
                """安全的保存方法，带有重试机制"""
                for attempt in range(max_retries):
                    try:
                        record.save(update_fields=update_fields)
                        return True
                    except (DatabaseError, Exception) as e:
                        error_str = str(e)
                        # 检查是否是MySQL连接错误
                        if '2006' in error_str or 'MySQL server has gone away' in error_str or '0' == error_str:
                            if attempt < max_retries - 1:
                                logger.warning(f"数据库连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                                # 关闭旧连接并重试
                                try:
                                    connection.close()
                                except:
                                    pass
                                import time
                                time.sleep(0.5)  # 等待一下再重试
                                continue
                            else:
                                logger.error(f"数据库保存失败，已达最大重试次数: {e}")
                                raise
                        else:
                            # 其他错误直接抛出
                            logger.error(f"数据库保存失败: {e}")
                            raise
                return False

            try:
                # 定义异步安全的 should_stop
                async def should_stop_async():
                    # 优先检查内存信号
                    if STOP_SIGNALS.get(execution_record.id, False):
                        return True
                    # 兜底检查数据库状态 (使用 sync_to_async 避免异步上下文错误)
                    # 关键修复：只刷新 status 字段，避免覆盖内存中最新的 planned_tasks
                    await sync_to_async(execution_record.refresh_from_db)(fields=['status'])
                    return execution_record.status == 'stopped'

                # 定义同步版本的 should_stop 用于最后检查
                def should_stop_sync():
                    if STOP_SIGNALS.get(execution_record.id, False):
                        return True
                    # 只刷新 status 字段，避免覆盖内存中最新的 planned_tasks
                    # 因为 planned_tasks 已经由 on_step_update 实时更新并在内存中是最新的
                    execution_record.refresh_from_db(fields=['status'])
                    return execution_record.status == 'stopped'

                async def on_analysis_complete(planned_tasks):
                    execution_record.planned_tasks = sanitize_planned_tasks(planned_tasks)
                    await sync_to_async(persist_execution_plan)(
                        execution_record.id,
                        task_description,
                        execution_record.planned_tasks,
                    )
                    execution_record.logs += "任务分析完成，开始执行...\n"
                    await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks', 'logs'])

                async def on_step_update(step_info):
                    try:
                        # 处理日志
                        if step_info.get('type') == 'log':
                            content = step_info.get('content')
                            if content:
                                execution_record.logs += content
                                # 立即保存到数据库，确保前端轮询能看到最新日志
                                await sync_to_async(safe_save)(execution_record, update_fields=['logs'])
                            return

                        # 处理任务状态
                        task_id = step_info.get('task_id')
                        status = step_info.get('status')
                        logger.info(f"DEBUG: on_step_update received: task_id={task_id}, status={status}")

                        if task_id and status:
                            updated = False
                            if execution_record.planned_tasks:
                                execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                                old_status = None
                                for task in execution_record.planned_tasks:
                                    if str(task.get('id')) == str(task_id):
                                        old_status = task.get('status', 'pending')
                                        break
                                updated = update_planned_task_status(
                                    execution_record.planned_tasks,
                                    task_id,
                                    status
                                )
                                if updated:
                                    logger.info(f"DEBUG: Updated task {task_id} from {old_status} to {status}")
                            if updated:
                                # 立即保存到数据库，确保前端轮询能看到最新状态
                                await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks'])
                            else:
                                logger.warning(
                                    f"DEBUG: Task ID {task_id} not found in planned_tasks: {execution_record.planned_tasks}")
                    except Exception as e:
                        logger.error(f"更新步骤状态失败: {e}", exc_info=True)

                history = run_full_process_sync(
                    task_description,
                    analysis_callback=on_analysis_complete,
                    step_callback=on_step_update,
                    should_stop=should_stop_async,  # 传递异步版本
                    execution_mode=execution_mode,
                    enable_gif=enable_gif,  # 传递GIF录制开关
                    case_name=task_description[:50] if task_description else "Adhoc Task",  # 传递用例名称用于GIF文件命名
                    case_mode=case_mode,
                    task_steps=task_steps,
                    use_cache=use_cache,
                    execution_user_id=request.user.id,
                    environment_configuration=environment_configuration,
                    execution_record_id=execution_record.id,
                )

                # 检查是否是手动停止 (使用同步版本)
                if should_stop_sync():
                    execution_record.status = 'stopped'
                    execution_record.logs += "\n[System] 任务已由用户停止。"
                else:
                    execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                    # 关键修复：移除可能导致数据回滚的 refresh_from_db 调用
                    # 内存中的 execution_record.planned_tasks 已经由 on_step_update 实时更新并在内存中是最新的
                    # 信任内存中的状态，而不是去数据库拉取（可能存在异步写入延迟）
                    # execution_record.refresh_from_db(fields=['planned_tasks'])
                    
                    quality_gate_result = evaluate_execution_quality_gate(execution_record.id)
                    if quality_gate_result is None:
                        execution_record.status, task_summary = resolve_execution_status(execution_record.planned_tasks)
                    else:
                        execution_record.status = quality_gate_result.status
                        task_summary = summarize_planned_tasks(execution_record.planned_tasks)
                    
                    # 添加详细调试日志，以便排查问题
                    logger.info(f"🔍 Final task status check before save: {task_summary}")
                    if execution_record.status != 'passed':
                        logger.warning(f"⚠️ Execution failed despite tasks completed? Tasks: {execution_record.planned_tasks}")

                    if execution_record.status == 'passed':
                        execution_record.logs += "\n执行完成。"
                    elif execution_record.status == 'inconclusive':
                        execution_record.logs += "\n执行结束，但计划为空或仍有未完成子任务，无法证明通过。"
                    else:
                        execution_record.logs += "\n执行结束，但存在未完成或失败的子任务。"
                    logger.info(
                        "🏁 Task completion summary: "
                        f"{task_summary['completed']}/{task_summary['total']} completed, "
                        f"{task_summary['failed']} failed, "
                        f"{task_summary['pending'] + task_summary['in_progress']} pending"
                    )

                execution_record.end_time = timezone.now()
                execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()

                # 格式化 history 为日志 (如果不是停止状态)
                steps = []
                if history:
                    if hasattr(history, 'steps'):
                        steps = [extract_step_info(s, i) for i, s in enumerate(history.steps)]
                    if hasattr(history, 'planner_trace'):
                        execution_record.planner_trace = history.planner_trace or {}
                    if hasattr(history, 'artifacts'):
                        execution_record.artifacts = history.artifacts or []
                        execution_record.screenshots_sequence = extract_screenshot_sequence(execution_record.artifacts)
                    if hasattr(history, 'cache_stats'):
                        execution_record.cache_stats = history.cache_stats or {}

                execution_record.steps_completed = steps

                if execution_record.planned_tasks:
                    execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                    execution_record.logs = append_execution_summary(
                        execution_record.logs,
                        summarize_planned_tasks(execution_record.planned_tasks)
                    )

                # 处理GIF录制文件
                if execution_record.execution_mode == 'text':
                    self._process_gif_recording(execution_record, history)

                safe_save(execution_record)

            except Exception as e:
                error_message = str(e)
                logger.error(f"AI adhoc 执行线程异常: {error_message}", exc_info=True)
                execution_record.planned_tasks = sanitize_planned_tasks(execution_record.planned_tasks)
                current_summary = summarize_planned_tasks(execution_record.planned_tasks)
                failed_task_id = None if is_infrastructure_failure(error_message) else mark_first_active_task(execution_record.planned_tasks, 'failed')
                execution_record.status = 'failed'
                if 'Execution LLM unavailable' in error_message:
                    execution_record.logs += f"\n执行出错: AI 执行模型连接失败。{error_message}"
                else:
                    execution_record.logs += f"\n执行出错: {error_message}"
                if failed_task_id is not None:
                    execution_record.logs += f"\n[System] 子任务 {failed_task_id} 已自动标记为失败。"

                execution_record.end_time = timezone.now()
                execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()
                execution_record.logs = append_execution_summary(
                    execution_record.logs,
                    summarize_planned_tasks(execution_record.planned_tasks)
                )
                try:
                    safe_save(execution_record)
                except:
                    # 如果保存失败，至少尝试保存基本信息
                    logger.error(f"保存失败状态时出错: {e}")
                    pass
            finally:
                # 清理停止信号
                if execution_record.id in STOP_SIGNALS:
                    del STOP_SIGNALS[execution_record.id]

        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()

        return Response({
            'message': 'AI 任务开始执行',
            'execution_id': execution_record.id
        })

    @action(detail=True, methods=['post'], url_path='stop')
    def stop_task(self, request, pk=None):
        """停止正在执行的任务"""
        try:
            execution_id = int(pk)
            if execution_id in STOP_SIGNALS:
                STOP_SIGNALS[execution_id] = True
                return Response({'message': '已发送停止信号'})
            else:
                # 如果不在内存中，可能已经结束，或者重启过服务
                # 尝试直接更新数据库状态
                record = self.get_object()
                if record.status == 'running':
                    record.status = 'stopped'
                    record.end_time = timezone.now()
                    record.logs += "\n[System] 任务被强制标记为停止（未在运行队列中找到）。"
                    record.save()
                    return Response({'message': '任务已标记为停止'})
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
        """
        处理GIF录制文件
        在执行完成后查找生成的GIF文件并保存路径到数据库
        """
        try:
            import os
            from django.conf import settings
            from datetime import datetime

            # browser-use 默认生成的GIF文件名（固定为agent_history.gif）
            default_gif_path = os.path.join(os.getcwd(), 'agent_history.gif')

            # 如果找到GIF文件，移动到media/ai_recording目录并重命名
            if os.path.exists(default_gif_path):
                import shutil

                # 创建录制文件目录 - 使用配置文件中的路径
                gif_dir = os.path.join(settings.MEDIA_ROOT, settings.ALLURE_AI_RECORDING)
                os.makedirs(gif_dir, exist_ok=True)

                # 生成新的文件名：用例名称+年月日时分秒
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                # 清理用例名称中的非法字符
                safe_case_name = "".join(
                    [c if c.isalnum() or c in (' ', '_', '-') else '_' for c in execution_record.case_name])
                new_gif_filename = f"{safe_case_name}_{timestamp}.gif"
                new_gif_path = os.path.join(gif_dir, new_gif_filename)

                # 移动并重命名文件
                shutil.move(default_gif_path, new_gif_path)

                # 保存相对路径到数据库（使用正斜杠，确保跨平台兼容）- 使用配置文件中的路径
                # 注意：不要包含 'media/' 前缀，因为 MEDIA_URL 已经是 '/media/'
                relative_path = f'{settings.ALLURE_AI_RECORDING}/{new_gif_filename}'
                execution_record.gif_path = relative_path

                logger.info(f"✅ GIF recording saved to: {relative_path}")
            else:
                logger.warning(f"⚠️ GIF file not found at: {default_gif_path}")
        except Exception as e:
            logger.error(f"❌ Error moving GIF file: {e}")
            logger.warning(f"⚠️ Failed to process GIF recording: {e}")

    def _auto_mark_completed_tasks(self, execution_record):
        return AICaseViewSet._auto_mark_completed_tasks(self, execution_record)
