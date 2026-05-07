"""
调度器 Admin 配置
"""
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.contrib import messages
from django_q.models import Schedule
from .models import ScheduleConfig
from apps.core.admin_mixins import StandardAdminMixin


@staff_member_required
def schedule_execute_now(request, schedule_id):
    """立即执行定时任务"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"schedule_execute_now 被调用: schedule_id={schedule_id}, user={request.user.username}, user_id={request.user.id}")
    
    try:
        schedule = Schedule.objects.get(id=schedule_id)
        from apps.scheduler.task_executor import execute_task
        task_id = execute_task(schedule_id, is_manual_execution=True, executed_by_id=request.user.id)
        logger.info(f"execute_task 返回: task_id={task_id}")
        messages.success(request, f'任务已提交执行: {schedule.name}, task_id={task_id}')
    except Schedule.DoesNotExist:
        messages.error(request, f'任务不存在: {schedule_id}')
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        messages.error(request, f'执行失败: {str(e)}')
    
    return HttpResponseRedirect(reverse('admin:django_q_schedule_changelist'))


class ScheduleConfigInline(admin.StackedInline):
    """在 Schedule Admin 中内联显示配置"""
    model = ScheduleConfig
    fk_name = 'schedule'
    extra = 0
    max_num = 1
    verbose_name = _('任务配置')
    verbose_name_plural = _('任务配置')
    fieldsets = (
        (_('业务配置'), {
            'fields': ('module', 'task_type', 'project_id', 'target_id', 'environment_id', 'task_config')
        }),
        (_('状态'), {
            'fields': ('status', 'description')
        }),
        (_('通知配置'), {
            'fields': ('notify_on_success', 'notify_on_failure', 'notify_emails', 'webhook_url')
        }),
        (_('其他'), {
            'fields': ('created_by',),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


# 注销Django-Q的默认ScheduleAdmin，注册自定义的ScheduleAdmin
# 注意：ScheduleAdmin的注册现在在apps.py的ready()方法中处理

class ScheduleAdmin(StandardAdminMixin, admin.ModelAdmin):
    """Django-Q Schedule Admin 配置"""
    list_display = ['name', 'status_display', 'task_type', 'next_run', 'success_count', 'failure_count', 'execute_now_button']
    list_filter = []
    search_fields = ['name', 'func']
    readonly_fields = ['last_run', 'next_run', 'success_count', 'failure_count', 'execute_now_button']
    inlines = [ScheduleConfigInline]
    
    fieldsets = (
        (_('基本信息'), {
            'fields': ('name', 'func', 'args', 'kwargs')
        }),
        (_('调度配置'), {
            'fields': ('cron', 'schedule_type', 'minutes', 'repeats', 'next_run')
        }),
        (_('执行信息'), {
            'fields': ('last_run', 'success_count', 'failure_count', 'execute_now_button'),
            'classes': ('collapse',),
        }),
        (_('其他'), {
            'fields': ('timeout', 'retries', 'hook'),
            'classes': ('collapse',),
        }),
    )
    
    def status_display(self, obj):
        """获取任务状态"""
        try:
            config = ScheduleConfig.objects.get(schedule=obj)
            return config.get_status_display()
        except ScheduleConfig.DoesNotExist:
            return '-'
    status_display.short_description = _('状态')
    
    def task_type(self, obj):
        """获取任务类型"""
        try:
            config = ScheduleConfig.objects.get(schedule=obj)
            return config.get_task_type_display()
        except ScheduleConfig.DoesNotExist:
            return '-'
    task_type.short_description = _('任务类型')
    
    def last_run(self, obj):
        """上次运行时间"""
        try:
            from django_q.models import Task
            
            # 使用 group 字段过滤（group 是任务名称）
            last_task = Task.objects.filter(group=obj.name).order_by('-started').first()
            
            if last_task:
                return last_task.started.strftime('%Y-%m-%d %H:%M:%S')
            return '-'
        except Exception as e:
            return '-'
    last_run.short_description = _('上次运行')
    
    def success_count(self, obj):
        """成功次数"""
        try:
            from django_q.models import Task
            return Task.objects.filter(group=obj.name, success=True).count()
        except Exception:
            return 0
    success_count.short_description = _('成功次数')
    
    def failure_count(self, obj):
        """失败次数"""
        try:
            from django_q.models import Task
            return Task.objects.filter(group=obj.name, success=False).count()
        except Exception:
            return 0
    failure_count.short_description = _('失败次数')
    
    def execute_now_button(self, obj):
        """立即执行按钮"""
        return format_html(
            '<a href="/admin/scheduler/schedule/{}/execute/" class="button" style="background-color: #417690; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px;">立即执行</a>',
            obj.id
        )
    execute_now_button.short_description = _('操作')
    execute_now_button.allow_tags = True
    
    def save_model(self, request, obj, form, change):
        """保存模型时同步更新ScheduleConfig状态"""
        super().save_model(request, obj, form, change)
        try:
            config = ScheduleConfig.objects.get(schedule=obj)
            if not obj.enabled:
                config.status = 'PAUSED'
            else:
                config.status = 'ACTIVE'
            config.save()
        except ScheduleConfig.DoesNotExist:
            pass
