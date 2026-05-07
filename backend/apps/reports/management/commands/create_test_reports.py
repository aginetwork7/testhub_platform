"""
测试报告管理命令
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.reports.models import TestReport
from apps.projects.models import Project
import random

User = get_user_model()


class Command(BaseCommand):
    help = '创建测试报告示例数据'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=5,
            help='创建报告数量',
        )
        parser.add_argument(
            '--type',
            type=str,
            default='all',
            choices=['all', 'ui', 'api', 'app'],
            help='报告类型',
        )
    
    def handle(self, *args, **options):
        count = options['count']
        report_type = options['type']
        
        user = User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR('请先创建用户'))
            return
        
        project = Project.objects.first()
        if not project:
            self.stdout.write(self.style.ERROR('请先创建项目'))
            return
        
        created_count = 0
        now = timezone.now()
        
        if report_type in ['all', 'ui']:
            for i in range(count):
                total = random.randint(20, 100)
                passed = random.randint(int(total * 0.7), total)
                failed = random.randint(0, total - passed)
                skipped = total - passed - failed
                
                report = TestReport.objects.create(
                    name=f'UI自动化测试报告 - 模块{i+1}',
                    project=project,
                    report_type='execution',
                    status='completed',
                    total_cases=total,
                    passed_cases=passed,
                    failed_cases=failed,
                    skipped_cases=skipped,
                    error_cases=0,
                    duration=random.uniform(60, 300),
                    summary={
                        'browser': random.choice(['Chrome', 'Firefox', 'Edge']),
                        'environment': '测试环境',
                    },
                    environment_info={
                        '操作系统': 'Windows 11',
                        '浏览器': 'Chrome 120',
                        '执行引擎': 'Playwright',
                    },
                    started_at=now,
                    finished_at=now,
                    generated_by=user,
                )
                report.generate_html_report()
                report.save()
                created_count += 1
        
        if report_type in ['all', 'api']:
            for i in range(count):
                total = random.randint(30, 150)
                passed = random.randint(int(total * 0.8), total)
                failed = random.randint(0, total - passed)
                skipped = total - passed - failed
                
                report = TestReport.objects.create(
                    name=f'API接口测试报告 - 服务{i+1}',
                    project=project,
                    report_type='execution',
                    status='completed',
                    total_cases=total,
                    passed_cases=passed,
                    failed_cases=failed,
                    skipped_cases=skipped,
                    error_cases=0,
                    duration=random.uniform(30, 120),
                    summary={
                        'base_url': 'https://api.example.com',
                        'avg_response_time': f'{random.randint(50, 200)}ms',
                    },
                    environment_info={
                        'API版本': 'v2.0',
                        '测试环境': 'https://api-test.example.com',
                    },
                    started_at=now,
                    finished_at=now,
                    generated_by=user,
                )
                report.generate_html_report()
                report.save()
                created_count += 1
        
        if report_type in ['all', 'app']:
            for i in range(count):
                total = random.randint(15, 50)
                passed = random.randint(int(total * 0.75), total)
                failed = random.randint(0, total - passed)
                skipped = total - passed - failed
                
                report = TestReport.objects.create(
                    name=f'APP自动化测试报告 - 功能{i+1}',
                    project=project,
                    report_type='execution',
                    status='completed',
                    total_cases=total,
                    passed_cases=passed,
                    failed_cases=failed,
                    skipped_cases=skipped,
                    error_cases=0,
                    duration=random.uniform(100, 400),
                    summary={
                        'app_version': '2.5.0',
                        'device': random.choice(['iPhone 15', 'Samsung S24', 'Pixel 8']),
                    },
                    environment_info={
                        '设备': 'iPhone 15 Pro',
                        'APP版本': '2.5.0',
                        '执行框架': 'Appium 2.0',
                    },
                    started_at=now,
                    finished_at=now,
                    generated_by=user,
                )
                report.generate_html_report()
                report.save()
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'成功创建 {created_count} 个测试报告')
        )
