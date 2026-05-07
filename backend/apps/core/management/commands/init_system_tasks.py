# -*- coding: utf-8 -*-
# -----------------------------
# @Author    : 影子
# @Time      : 2026/3/7 00:41
# @Software  : PyCharm
# @FileName  : init_system_tasks.py
# -----------------------------
from django.core.management.base import BaseCommand
from django_q.models import Schedule
from django.utils import timezone


class Command(BaseCommand):
    """
    初始化系统定时任务
    """
    help = '初始化系统定时任务'

    def handle(self, *args, **options):
        self.stdout.write('正在初始化系统定时任务...')

        tasks = [
            {
                'name': '每日性能统计聚合',
                'func': 'apps.core.tasks.aggregate_daily_performance_stats',
                'schedule_type': Schedule.DAILY,
                'minutes': 0,
                'repeats': -1,
            },
            {
                'name': '实时性能统计聚合',
                'func': 'apps.core.tasks.aggregate_current_day_stats',
                'schedule_type': Schedule.MINUTES,
                'minutes': 30,
                'repeats': -1,
            },
        ]

        for task_config in tasks:
            existing = Schedule.objects.filter(name=task_config['name']).first()

            if existing:
                self.stdout.write(f'定时任务已存在: {task_config["name"]}')
            else:
                Schedule.objects.create(
                    name=task_config['name'],
                    func=task_config['func'],
                    schedule_type=task_config['schedule_type'],
                    minutes=task_config.get('minutes', 0),
                    next_run=timezone.now(),
                    repeats=task_config['repeats'],
                )
                self.stdout.write(self.style.SUCCESS(f'创建定时任务: {task_config["name"]}'))

        self.stdout.write(self.style.SUCCESS('系统定时任务初始化完成'))
        self.stdout.write('')
        self.stdout.write('请确保已启动 Django Q 集群:')
        self.stdout.write('  python manage.py qcluster')
