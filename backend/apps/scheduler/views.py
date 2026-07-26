"""
调度器视图
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db import models
from django_q.models import Schedule, Success, Failure
from django_q.tasks import async_task
from loguru import logger

from .models import ScheduleConfig, create_scheduled_task
from .serializers import (
    ScheduleSerializer, ScheduleCreateSerializer,
    ScheduleConfigSerializer, ScheduleExecuteSerializer,
    ScheduleToggleSerializer
)
from apps.core.models import NotificationTemplate


class SchedulePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    定时任务视图集
    """
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    pagination_class = SchedulePagination
    filterset_fields = ['schedule_type', 'cluster']
    search_fields = ['name', 'func']
    ordering_fields = ['next_run', 'name']
    ordering = ['-next_run']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # 使用 select_related 优化查询，避免 N+1 查询问题
        queryset = queryset.select_related('config')
        # 预加载多对多关系
        queryset = queryset.prefetch_related('config__notification_configs')
        
        # 筛选模块
        module = self.request.query_params.get('module')
        if module:
            queryset = queryset.filter(config__module=module)
        
        # 筛选任务类型
        task_type = self.request.query_params.get('task_type')
        if task_type:
            queryset = queryset.filter(config__task_type=task_type)
        
        # 筛选状态
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(config__status=status)
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ScheduleCreateSerializer
        if self.action in ['update', 'partial_update']:
            return ScheduleCreateSerializer
        return ScheduleSerializer
    
    def update(self, request, *args, **kwargs):
        """更新定时任务"""
        schedule = self.get_object()
        
        try:
            config = ScheduleConfig.objects.get(schedule=schedule)
        except ScheduleConfig.DoesNotExist:
            return Response(
                {'error': _('任务配置不存在')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        try:
            # 更新 Schedule
            if 'name' in data:
                schedule.name = data['name']
            if 'schedule_type' in data:
                schedule.schedule_type = data['schedule_type']
            if 'cron' in data:
                schedule.cron = data['cron']
            if 'minutes' in data:
                schedule.minutes = data['minutes']
            if 'next_run' in data:
                schedule.next_run = data['next_run']
            
            schedule.save()
            
            # 更新 ScheduleConfig
            if 'task_type' in data:
                config.task_type = data['task_type']
            if 'target_id' in data:
                config.target_id = data['target_id']
            if 'environment_id' in data:
                config.environment_id = data['environment_id']
            if 'description' in data:
                config.description = data['description']
            if 'task_config' in data:
                current_config = config.task_config or {}
                current_config.update(data['task_config'])
                config.task_config = current_config
            
            if 'notify_on_success' in data:
                config.notify_on_success = data['notify_on_success']
            
            if 'notify_on_failure' in data:
                config.notify_on_failure = data['notify_on_failure']
            
            if 'notify_on_email' in data:
                config.notify_on_email = data['notify_on_email']
            
            if 'notify_on_webhook' in data:
                config.notify_on_webhook = data['notify_on_webhook']
            
            if 'notification_template_id' in data:
                try:
                    template = NotificationTemplate.objects.get(id=data['notification_template_id'])
                    config.notification_template = template
                except NotificationTemplate.DoesNotExist:
                    return Response(
                        {'error': _('通知模板不存在')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # 处理通知配置
            if 'notification_config_ids' in data:
                config.notification_configs.set(data['notification_config_ids'])
            
            config.save()
            
            # 重新加载 schedule 对象以获取最新的 config 数据
            schedule.refresh_from_db()
            # 重新预加载关系
            schedule = Schedule.objects.select_related('config').prefetch_related('config__notification_configs').get(id=schedule.id)
            
            return Response(
                ScheduleSerializer(schedule).data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"更新定时任务失败: {e}", exc_info=True)
            logger.error(f"任务ID: {schedule.id}, 错误类型: {type(e).__name__}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """创建定时任务"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        try:
            # 处理通知模板
            notification_template = None
            if 'notification_template_id' in data and data['notification_template_id']:
                try:
                    notification_template = NotificationTemplate.objects.get(id=data['notification_template_id'])
                except NotificationTemplate.DoesNotExist:
                    return Response(
                        {'error': _('通知模板不存在')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # 处理通知配置
            notification_config_ids = []
            if 'notification_config_ids' in data and data['notification_config_ids']:
                notification_config_ids = data['notification_config_ids']
                logger.info(f"从 validated_data 获取 notification_config_ids: {notification_config_ids}")
            else:
                logger.info(f"validated_data 中没有 notification_config_ids, data keys: {data.keys()}")
            
            schedule, config = create_scheduled_task(
                name=data['name'],
                module=data['module'],
                task_type=data['task_type'],
                schedule_type=data['schedule_type'],
                target_id=data.get('target_id'),
                project_id=data.get('project_id'),
                environment_id=data.get('environment_id'),
                task_config=data.get('task_config', {}),
                cron=data.get('cron'),
                minutes=data.get('minutes'),
                next_run=data.get('next_run'),
                repeats=data.get('repeats', -1),
                created_by=request.user,
                description=data.get('description', ''),
                notify_on_success=data.get('notify_on_success', False),
                notify_on_failure=data.get('notify_on_failure', True),
                notify_emails=[],
                webhook_url='',
                notification_template=notification_template,
            )
            
            # 设置通知配置
            if notification_config_ids:
                try:
                    from core.models import UnifiedNotificationConfig
                    configs = UnifiedNotificationConfig.objects.filter(id__in=notification_config_ids)
                    logger.info(f"找到 {configs.count()} 个通知配置")
                    config.notification_configs.set(configs)
                    logger.info(f"已设置通知配置到任务 {config.id}")
                except Exception as e:
                    logger.error(f"设置通知配置失败: {e}")
            else:
                logger.warning(f"notification_config_ids 为空，跳过设置通知配置")
            
            if 'notify_on_email' in data:
                config.notify_on_email = data['notify_on_email']
                config.save()
            
            if 'notify_on_webhook' in data:
                config.notify_on_webhook = data['notify_on_webhook']
                config.save()
            
            return Response(
                ScheduleSerializer(schedule).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.error(f"创建定时任务失败: {e}", exc_info=True)
            logger.error(f"请求数据: {request.data}, 错误类型: {type(e).__name__}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def list(self, request, *args, **kwargs):
        """获取定时任务列表"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # 分页
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # 添加 last_run_display 到每个结果
            for item in serializer.data:
                schedule_id = item['id']
                # 查询该 schedule 的最近执行时间
                try:
                    from django.utils import timezone
                    schedule = next(s for s in page if s.id == schedule_id)
                    last_run = None
                    for record in Success.objects.filter(func=schedule.func).order_by('-stopped')[:100]:
                        if record.kwargs and isinstance(record.kwargs, dict) and record.kwargs.get('schedule_id') == schedule_id:
                            last_run = record
                            break
                    if last_run and last_run.stopped:
                        item['last_run_display'] = timezone.localtime(last_run.stopped).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        item['last_run_display'] = '-'
                except Exception as e:
                    item['last_run_display'] = '-'
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        # 添加 last_run_display 到每个结果
        for item in serializer.data:
            schedule_id = item['id']
            try:
                from django.utils import timezone
                schedule = next(s for s in queryset if s.id == schedule_id)
                last_run = None
                for record in Success.objects.filter(func=schedule.func).order_by('-stopped')[:100]:
                    if record.kwargs and isinstance(record.kwargs, dict) and record.kwargs.get('schedule_id') == schedule_id:
                        last_run = record
                        break
                if last_run and last_run.stopped:
                    item['last_run_display'] = timezone.localtime(last_run.stopped).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    item['last_run_display'] = '-'
            except Exception as e:
                item['last_run_display'] = '-'
        return Response(serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        """删除定时任务"""
        schedule = self.get_object()
        
        try:
            config = ScheduleConfig.objects.get(schedule=schedule)
            config.delete()
        except ScheduleConfig.DoesNotExist:
            pass
        
        schedule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'], serializer_class=ScheduleExecuteSerializer)
    def execute(self, request, pk=None):
        """立即执行任务"""
        schedule = self.get_object()
        
        try:
            args = eval(schedule.args) if schedule.args else []
            kwargs = eval(schedule.kwargs) if schedule.kwargs else {}
            kwargs['is_manual_execution'] = True
            kwargs['executed_by_id'] = request.user.id
            task_id = async_task(schedule.func, *args, **kwargs)
            
            return Response({
                'message': _('任务已提交执行'),
                'task_id': task_id
            })
        except Exception as e:
            logger.error(f"执行任务失败: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], serializer_class=ScheduleToggleSerializer)
    def toggle(self, request, pk=None):
        """暂停/恢复任务"""
        schedule = self.get_object()
        action_type = request.data.get('action', 'pause')
        
        try:
            config = ScheduleConfig.objects.get(schedule=schedule)
            
            if action_type == 'pause':
                config.pause()
                return Response({'message': _('任务已暂停')})
            else:
                config.resume()
                return Response({'message': _('任务已恢复')})
        except ScheduleConfig.DoesNotExist:
            if action_type == 'pause':
                schedule.next_run = None
                schedule.save(update_fields=['next_run'])
                return Response({'message': _('任务已禁用')})
            schedule.next_run = timezone.now()
            schedule.save(update_fields=['next_run'])
            return Response({'message': _('任务已启用')})
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """获取任务执行历史"""
        from django.utils import timezone
        
        schedule = self.get_object()
        
        # PickledObjectField 不支持直接查询，需要在 Python 中过滤
        success_records = []
        for record in Success.objects.filter(func=schedule.func).order_by('-stopped')[:100]:
            if record.kwargs and isinstance(record.kwargs, dict) and record.kwargs.get('schedule_id') == schedule.id:
                success_records.append(record)
        
        failure_records = []
        for record in Failure.objects.filter(func=schedule.func).order_by('-stopped')[:100]:
            if record.kwargs and isinstance(record.kwargs, dict) and record.kwargs.get('schedule_id') == schedule.id:
                failure_records.append(record)
        
        from .serializers import ScheduleConfigSerializer
        
        return Response({
            'success': [
                {
                    'id': r.id,
                    'name': r.name,
                    'started': timezone.localtime(r.started).isoformat() if r.started else None,
                    'stopped': timezone.localtime(r.stopped).isoformat() if r.stopped else None,
                    'success': r.success,
                }
                for r in success_records[:20]
            ],
            'failure': [
                {
                    'id': r.id,
                    'name': r.name,
                    'started': timezone.localtime(r.started).isoformat() if r.started else None,
                    'stopped': timezone.localtime(r.stopped).isoformat() if r.stopped else None,
                    'result': str(r.result)[:200] if r.result else None,
                }
                for r in failure_records[:20]
            ],
        })
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """获取任务统计"""
        total = Schedule.objects.count()
        active = Schedule.objects.filter(enabled=True).count()
        paused = Schedule.objects.filter(enabled=False).count()
        
        success_total = Success.objects.count()
        failure_total = Failure.objects.count()
        
        return Response({
            'total_schedules': total,
            'active_schedules': active,
            'paused_schedules': paused,
            'total_executions': success_total + failure_total,
            'success_count': success_total,
            'failure_count': failure_total,
            'success_rate': round(success_total / (success_total + failure_total) * 100, 2) if (success_total + failure_total) > 0 else 0,
        })


class ScheduleConfigViewSet(viewsets.ReadOnlyModelViewSet):
    """
    任务配置视图集（只读）
    """
    queryset = ScheduleConfig.objects.all()
    serializer_class = ScheduleConfigSerializer
    filterset_fields = ['module', 'task_type', 'status']
    search_fields = ['schedule__name']
    ordering = ['-created_at']
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """暂停任务"""
        config = self.get_object()
        config.pause()
        return Response({'message': _('任务已暂停')})
    
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """恢复任务"""
        config = self.get_object()
        config.resume()
        return Response({'message': _('任务已恢复')})
