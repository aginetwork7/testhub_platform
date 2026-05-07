"""
统一调度器应用
基于 Django-Q 实现定时任务管理
"""
from django.apps import AppConfig


class SchedulerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scheduler'
    verbose_name = '任务调度'

    def ready(self):
        """应用启动时执行"""
        from django.contrib import admin
        from django_q.models import Schedule

        # 注销Django-Q的默认ScheduleAdmin
        try:
            admin.site.unregister(Schedule)
        except admin.sites.NotRegistered:
            pass

        # 导入并注册自定义的ScheduleAdmin
        from .admin import ScheduleAdmin
        admin.site.register(Schedule, ScheduleAdmin)
