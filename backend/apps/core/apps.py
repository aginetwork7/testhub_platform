"""
Core应用配置
在应用启动时加载配置文件
"""
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = '核心模块'
    
    def ready(self):
        """应用启动时执行"""
        logger.info('Core应用启动，开始加载配置...')
        
        # 导入配置加载器
        from backend.config_loader import config_loader
        
        # 记录配置信息
        server_config = config_loader.get_server_config()
        import json
        logger.info(f'服务器配置已加载: {json.dumps(server_config, ensure_ascii=False)}')
        
        # 注册自定义 Django Q Admin（中文化）
        self._register_django_q_admin()
        
        logger.info('Core应用启动完成')
    
    def _register_django_q_admin(self):
        """注册自定义的 Django Q Admin"""
        from django.contrib import admin
        from django.utils.translation import gettext_lazy as _
        from django.utils.safestring import mark_safe
        from django.contrib.admin import SimpleListFilter
        from django_q.models import Task, Schedule, Success, Failure
        from django_q.brokers import orm
        import json
        
        class ScheduleTypeFilter(SimpleListFilter):
            title = _('调度类型')
            parameter_name = 'schedule_type'
            
            def lookups(self, request, model_admin):
                return [
                    ('O', _('Once')),
                    ('I', _('Minutes')),
                    ('H', _('Hourly')),
                    ('D', _('Daily')),
                    ('W', _('Weekly')),
                    ('BW', _('Biweekly')),
                    ('M', _('Monthly')),
                    ('BM', _('Bimonthly')),
                    ('Q', _('Quarterly')),
                    ('Y', _('Yearly')),
                    ('C', _('Cron')),
                ]
            
            def queryset(self, request, queryset):
                if self.value():
                    return queryset.filter(schedule_type=self.value())
                return queryset
        
        class ModuleFilter(SimpleListFilter):
            title = _('所属模块')
            parameter_name = 'module'
            
            def lookups(self, request, model_admin):
                return [
                    ('API', _('API测试')),
                    ('UI', _('UI测试')),
                    ('APP', _('APP测试')),
                ]
            
            def queryset(self, request, queryset):
                if self.value():
                    from apps.scheduler.models import ScheduleConfig
                    schedule_ids = ScheduleConfig.objects.filter(module=self.value()).values_list('schedule_id', flat=True)
                    return queryset.filter(id__in=schedule_ids)
                return queryset
        
        # 检查是否已注册，如果已注册则先取消
        if admin.site.is_registered(Task):
            admin.site.unregister(Task)
        if admin.site.is_registered(Schedule):
            admin.site.unregister(Schedule)
        if admin.site.is_registered(Success):
            admin.site.unregister(Success)
        if admin.site.is_registered(Failure):
            admin.site.unregister(Failure)
        
        # 尝试取消注册 OrmQ（如果存在）
        try:
            OrmQ = orm.OrmQ
            if admin.site.is_registered(OrmQ):
                admin.site.unregister(OrmQ)
        except Exception:
            OrmQ = None
        
        @admin.register(Task)
        class TaskAdmin(admin.ModelAdmin):
            list_display = ('col_id', 'col_name', 'col_func', 'col_group', 'col_started', 'col_stopped', 'col_success')
            list_filter = ('success', 'group')
            search_fields = ('name', 'func', 'group')
            readonly_fields = ('id', 'name', 'func', 'hook', 'args', 'kwargs', 
                               'result', 'group', 'cluster', 'started', 'stopped', 
                               'success', 'attempt_count')
            list_per_page = 20
            verbose_name = _('任务')
            verbose_name_plural = _('任务管理')
            
            @admin.display(description=_('ID'))
            def col_id(self, obj):
                return obj.id
            
            @admin.display(description=_('名称'))
            def col_name(self, obj):
                return obj.name
            
            @admin.display(description=_('函数'))
            def col_func(self, obj):
                if obj.func:
                    func_str = str(obj.func)
                    # 处理方法绑定对象，提取友好名称
                    if 'bound method' in func_str or '<bound method' in func_str:
                        try:
                            # 提取方法名称
                            import re
                            match = re.search(r"method\s+(\w+\.?\w*)", func_str)
                            if match:
                                return match.group(1)
                            # 尝试提取最后一个方法名
                            match = re.search(r"'(\w+)'", func_str)
                            if match:
                                return match.group(1)
                        except Exception:
                            pass
                    return func_str
                return '-'
            
            @admin.display(description=_('分组'))
            def col_group(self, obj):
                return obj.group or '-'
            
            @admin.display(description=_('开始时间'))
            def col_started(self, obj):
                return obj.started
            
            @admin.display(description=_('结束时间'))
            def col_stopped(self, obj):
                return obj.stopped
            
            @admin.display(description=_('状态'))
            def col_success(self, obj):
                return _('成功') if obj.success else _('失败')
            
            def has_add_permission(self, request):
                return False
            
            def has_change_permission(self, request, obj=None):
                return False
        
        @admin.register(Schedule)
        class ScheduleAdmin(admin.ModelAdmin):
            list_display = ('col_id', 'col_name', 'col_module', 'col_task_type', 'col_schedule_type', 'col_status', 'col_next_run', 'col_last_run', 'col_success_count', 'col_actions')
            list_filter = (ModuleFilter, 'schedule_type')
            search_fields = ('name', 'func')
            readonly_fields = ('id', 'task', 'cluster')
            list_per_page = 20
            verbose_name = _('定时任务')
            verbose_name_plural = _('定时任务')
            fieldsets = (
                (_('基本信息'), {
                    'fields': ('id', 'name', 'func', 'hook')
                }),
                (_('调度配置'), {
                    'fields': ('schedule_type', 'minutes', 'cron', 'repeats', 'next_run')
                }),
                (_('参数'), {
                    'fields': ('args', 'kwargs'),
                    'classes': ('collapse',),
                }),
                (_('其他'), {
                    'fields': ('task', 'cluster'),
                    'classes': ('collapse',),
                }),
            )
            
            @admin.display(description=_('ID'))
            def col_id(self, obj):
                return obj.id
            
            @admin.display(description=_('名称'))
            def col_name(self, obj):
                return obj.name or '-'
            
            @admin.display(description=_('所属模块'))
            def col_module(self, obj):
                try:
                    config = obj.config
                    return config.get_module_display()
                except Exception:
                    return '-'
            
            @admin.display(description=_('任务类型'))
            def col_task_type(self, obj):
                try:
                    config = obj.config
                    return config.get_task_type_display()
                except Exception:
                    return '-'
            
            @admin.display(description=_('调度类型'))
            def col_schedule_type(self, obj):
                type_map = {
                    'O': _('单次'),
                    'I': _('分钟间隔'),
                    'H': _('每小时'),
                    'D': _('每天'),
                    'W': _('每周'),
                    'BW': _('双周'),
                    'M': _('每月'),
                    'BM': _('双月'),
                    'Q': _('每季度'),
                    'Y': _('每年'),
                    'C': _('Cron'),
                }
                return type_map.get(obj.schedule_type, obj.schedule_type or '-')
            
            @admin.display(description=_('状态'))
            def col_status(self, obj):
                try:
                    config = obj.config
                    status_map = {
                        'ACTIVE': '<span style="color: green;">激活</span>',
                        'PAUSED': '<span style="color: orange;">暂停</span>',
                        'COMPLETED': '<span style="color: gray;">已完成</span>',
                        'FAILED': '<span style="color: red;">失败</span>',
                    }
                    return mark_safe(status_map.get(config.status, config.status))
                except Exception:
                    return mark_safe('<span style="color: green;">启用</span>')
            
            @admin.display(description=_('下次运行'))
            def col_next_run(self, obj):
                from django.utils import timezone
                from datetime import timedelta
                
                if not obj.next_run:
                    return '-'
                
                now = timezone.now()
                next_run = obj.next_run
                
                if next_run > now:
                    return timezone.localtime(next_run).strftime('%Y-%m-%d %H:%M:%S')
                
                if obj.schedule_type == 'I' and obj.minutes:
                    while next_run <= now:
                        next_run = next_run + timedelta(minutes=obj.minutes)
                    return mark_safe(f'<span style="color: #888;" title="原计划时间已过，显示计算的下一次时间">{timezone.localtime(next_run).strftime("%Y-%m-%d %H:%M:%S")}</span>')
                elif obj.schedule_type == 'C' and obj.cron:
                    try:
                        from croniter import croniter
                        cron = croniter(obj.cron, now)
                        next_run = cron.get_next(type(now))
                        return mark_safe(f'<span style="color: #888;" title="原计划时间已过，显示计算的下一次时间">{timezone.localtime(next_run).strftime("%Y-%m-%d %H:%M:%S")}</span>')
                    except Exception:
                        pass
                
                return mark_safe(f'<span style="color: red;" title="任务调度器可能未运行">{timezone.localtime(obj.next_run).strftime("%Y-%m-%d %H:%M:%S")}</span>')
            
            @admin.display(description=_('上次运行'))
            def col_last_run(self, obj):
                from django.utils import timezone
                
                try:
                    config = obj.config
                    if config.last_run_time:
                        return timezone.localtime(config.last_run_time).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
                return '-'
            
            @admin.display(description=_('成功/失败'))
            def col_success_count(self, obj):
                try:
                    config = obj.config
                    success_count = config.success_count
                    failure_count = config.failure_count
                    
                    if success_count == 0 and failure_count == 0:
                        return '-'
                    return mark_safe(
                        f'<span style="color: green;">{success_count}</span>/<span style="color: red;">{failure_count}</span>'
                    )
                except Exception:
                    return '-'
            
            @admin.display(description=_('操作'))
            def col_actions(self, obj):
                from django.urls import reverse
                try:
                    config = obj.config
                    actions = []
                    
                    # 立即执行按钮
                    url = reverse('admin:schedule_execute', args=[obj.id])
                    actions.append(f'<a href="{url}" class="button" style="background-color: #00f6ff; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; margin-right: 5px;">立即执行</a>')
                    
                    # 暂停/恢复按钮
                    if config.status == 'ACTIVE':
                        url = reverse('admin:schedule_toggle', args=[obj.id])
                        actions.append(f'<a href="{url}" style="color: orange; text-decoration: underline;">暂停</a>')
                    else:
                        url = reverse('admin:schedule_toggle', args=[obj.id])
                        actions.append(f'<a href="{url}" style="color: green; text-decoration: underline;">恢复</a>')
                    
                    return mark_safe(''.join(actions))
                except Exception:
                    return '-'
            
            def get_urls(self):
                from django.urls import path
                urls = super().get_urls()
                custom_urls = [
                    path('<int:schedule_id>/execute/', self.admin_site.admin_view(self.execute_view), name='schedule_execute'),
                    path('<int:schedule_id>/toggle/', self.admin_site.admin_view(self.toggle_view), name='schedule_toggle'),
                ]
                return custom_urls + urls
            
            def execute_view(self, request, schedule_id):
                """立即执行任务"""
                from django.shortcuts import redirect
                from django.contrib import messages
                from django_q.tasks import async_task
                from django.utils import timezone
                
                try:
                    schedule = Schedule.objects.get(id=schedule_id)
                    
                    group_name = schedule.name
                    try:
                        config = schedule.config
                        group_name = config.get_module_display()
                        config.last_run_time = timezone.now()
                        config.save(update_fields=['last_run_time'])
                    except Exception:
                        pass
                    
                    # 解析参数并添加手动执行标志和执行用户ID
                    args = eval(schedule.args or '[]')
                    kwargs = eval(schedule.kwargs or '{}')
                    kwargs['is_manual_execution'] = True
                    kwargs['executed_by_id'] = request.user.id
                    
                    task_id = async_task(
                        schedule.func, 
                        *args, 
                        **kwargs,
                        name=schedule.name,
                        group=group_name
                    )
                    messages.success(request, f'任务已提交执行，任务ID: {task_id}')
                except Exception as e:
                    messages.error(request, f'执行失败: {e}')
                
                return redirect('admin:django_q_schedule_changelist')
            
            def toggle_view(self, request, schedule_id):
                """暂停/恢复任务"""
                from django.shortcuts import redirect
                from django.contrib import messages
                
                try:
                    schedule = Schedule.objects.get(id=schedule_id)
                    config = schedule.config
                    
                    if config.status == 'ACTIVE':
                        config.pause()
                        messages.success(request, f'任务已暂停')
                    else:
                        config.resume()
                        messages.success(request, f'任务已恢复')
                except Exception as e:
                    messages.error(request, f'操作失败: {e}')
                
                return redirect('admin:django_q_schedule_changelist')
            
            def save_model(self, request, obj, form, change):
                super().save_model(request, obj, form, change)
                
                if not change:
                    return
                
                try:
                    from django.utils import timezone
                    config = obj.config
                    if config.status == 'ACTIVE':
                        # 激活状态，确保next_run有值
                        if not obj.next_run:
                            obj.next_run = timezone.now()
                            obj.save()
                    elif config.status == 'PAUSED':
                        # 暂停状态，将next_run设置为None
                        obj.next_run = None
                        obj.save()
                except Exception:
                    pass
            
            def delete_model(self, request, obj):
                try:
                    config = obj.config
                    config.delete()
                except Exception:
                    pass
                super().delete_model(request, obj)
        
        @admin.register(Success)
        class SuccessAdmin(admin.ModelAdmin):
            list_display = ('col_name', 'col_group', 'col_func', 'col_cluster', 'col_started', 'col_stopped', 'col_time_taken')
            list_filter = ('group', 'cluster')
            search_fields = ('name', 'func', 'group')
            readonly_fields = ('id', 'name', 'func', 'hook', 'args', 'kwargs',
                               'result', 'group', 'cluster', 'started', 'stopped', 
                               'success', 'attempt_count')
            list_per_page = 20
            verbose_name = _('成功记录')
            verbose_name_plural = _('成功记录')
            
            @admin.display(description=_('名称'))
            def col_name(self, obj):
                return obj.name
            
            @admin.display(description=_('分组'))
            def col_group(self, obj):
                return obj.group or '-'
            
            @admin.display(description=_('函数'))
            def col_func(self, obj):
                if obj.func:
                    func_str = str(obj.func)
                    # 处理方法绑定对象，提取友好名称
                    if 'bound method' in func_str or '<bound method' in func_str:
                        try:
                            # 提取方法名称
                            import re
                            match = re.search(r"method\s+(\w+\.?\w*)", func_str)
                            if match:
                                return match.group(1)
                            # 尝试提取最后一个方法名
                            match = re.search(r"'(\w+)'", func_str)
                            if match:
                                return match.group(1)
                        except Exception:
                            pass
                    return func_str
                return '-'
            
            @admin.display(description=_('集群'))
            def col_cluster(self, obj):
                return obj.cluster or '-'
            
            @admin.display(description=_('开始时间'))
            def col_started(self, obj):
                return obj.started
            
            @admin.display(description=_('结束时间'))
            def col_stopped(self, obj):
                return obj.stopped
            
            @admin.display(description=_('耗时'))
            def col_time_taken(self, obj):
                if obj.started and obj.stopped:
                    delta = obj.stopped - obj.started
                    total_seconds = delta.total_seconds()
                    if total_seconds < 1:
                        return f'{int(total_seconds * 1000)}ms'
                    elif total_seconds < 60:
                        return f'{total_seconds:.2f}s'
                    else:
                        minutes = int(total_seconds // 60)
                        seconds = total_seconds % 60
                        return f'{minutes}m {seconds:.1f}s'
                return '-'
            
            def has_add_permission(self, request):
                return False
            
            def has_change_permission(self, request, obj=None):
                return False
        
        @admin.register(Failure)
        class FailureAdmin(admin.ModelAdmin):
            list_display = ('col_name', 'col_group', 'col_func', 'col_cluster', 'col_started', 'col_stopped', 'col_short_result')
            list_filter = ('group', 'cluster')
            search_fields = ('name', 'func', 'group')
            readonly_fields = ('id', 'name', 'func', 'hook', 'args', 'kwargs',
                               'result', 'group', 'cluster', 'started', 'stopped', 
                               'success', 'attempt_count')
            list_per_page = 20
            verbose_name = _('失败记录')
            verbose_name_plural = _('失败记录')
            
            @admin.display(description=_('名称'))
            def col_name(self, obj):
                return obj.name
            
            @admin.display(description=_('分组'))
            def col_group(self, obj):
                return obj.group or '-'
            
            @admin.display(description=_('函数'))
            def col_func(self, obj):
                if obj.func:
                    func_str = str(obj.func)
                    # 处理方法绑定对象，提取友好名称
                    if 'bound method' in func_str or '<bound method' in func_str:
                        try:
                            # 提取方法名称
                            import re
                            match = re.search(r"method\s+(\w+\.?\w*)", func_str)
                            if match:
                                return match.group(1)
                            # 尝试提取最后一个方法名
                            match = re.search(r"'(\w+)'", func_str)
                            if match:
                                return match.group(1)
                        except Exception:
                            pass
                    return func_str
                return '-'
            
            @admin.display(description=_('集群'))
            def col_cluster(self, obj):
                return obj.cluster or '-'
            
            @admin.display(description=_('开始时间'))
            def col_started(self, obj):
                return obj.started
            
            @admin.display(description=_('结束时间'))
            def col_stopped(self, obj):
                return obj.stopped
            
            @admin.display(description=_('简短结果'))
            def col_short_result(self, obj):
                if obj.result:
                    result_str = str(obj.result)
                    if len(result_str) > 50:
                        return result_str[:50] + '...'
                    return result_str
                return '-'
            
            def has_add_permission(self, request):
                return False
            
            def has_change_permission(self, request, obj=None):
                return False
        
        # 注册 OrmQ Admin（队列任务）
        if OrmQ:
            @admin.register(OrmQ)
            class OrmQAdmin(admin.ModelAdmin):
                list_display = ('col_id', 'col_key', 'col_name', 'col_group', 'col_func', 'col_lock', 'col_task_id')
                list_filter = ('key',)
                search_fields = ('key', 'payload')
                readonly_fields = ('id', 'key', 'payload', 'lock')
                list_per_page = 20
                verbose_name = _('队列任务')
                verbose_name_plural = _('队列任务')
                
                @admin.display(description=_('ID'))
                def col_id(self, obj):
                    return obj.id
                
                @admin.display(description=_('键'))
                def col_key(self, obj):
                    return obj.key
                
                @admin.display(description=_('名称'))
                def col_name(self, obj):
                    return obj.name() or '-'
                
                @admin.display(description=_('分组'))
                def col_group(self, obj):
                    return obj.group() or '-'
                
                @admin.display(description=_('函数'))
                def col_func(self, obj):
                    func = obj.func()
                    if func:
                        func_str = str(func)
                        # 处理方法绑定对象，提取友好名称
                        if 'bound method' in func_str or '<bound method' in func_str:
                            try:
                                # 提取方法名称
                                import re
                                match = re.search(r"method\s+(\w+\.?\w*)", func_str)
                                if match:
                                    return match.group(1)
                                # 尝试提取最后一个方法名
                                match = re.search(r"'(\w+)'", func_str)
                                if match:
                                    return match.group(1)
                            except Exception:
                                pass
                        return func_str
                    return '-'
                
                @admin.display(description=_('锁'))
                def col_lock(self, obj):
                    if obj.lock:
                        from django.utils import timezone
                        return timezone.localtime(obj.lock).strftime('%Y-%m-%d %H:%M:%S')
                    return '-'
                
                @admin.display(description=_('任务ID'))
                def col_task_id(self, obj):
                    return obj.task_id() or '-'
                
                def has_add_permission(self, request):
                    return False
                
                def has_change_permission(self, request, obj=None):
                    return False
