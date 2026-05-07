# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from apps.core.models import NotificationTemplate


class Command(BaseCommand):
    """
    初始化默认通知模板
    """
    help = '初始化默认通知模板'

    def handle(self, *args, **options):
        self.stdout.write('正在初始化默认通知模板...')

        templates = [
            {
                'name': '默认邮件模板',
                'template_type': 'html',
                'subject': '【定时任务执行{{status}}】{{task_name}}',
                'content': '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: #f5f7fa; padding: 20px; }
        .card { max-width: 600px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1); overflow: hidden; }
        .header { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: #fff; padding: 24px; text-align: center; }
        .header h1 { font-size: 20px; font-weight: 600; margin-bottom: 8px; }
        .header .status { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 14px; font-weight: 500; }
        .header .status.success { background: rgba(255, 255, 255, 0.2); }
        .header .status.failed { background: rgba(255, 59, 48, 0.8); }
        .content { padding: 24px; }
        .info-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        .info-table tr { border-bottom: 1px solid #f0f0f0; }
        .info-table tr:last-child { border-bottom: none; }
        .info-table td { padding: 12px 0; font-size: 14px; }
        .info-table td:first-child { color: #8c8c8c; width: 100px; }
        .info-table td:last-child { color: #262626; font-weight: 500; }
        .stats { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
        .stat-item { flex: 1; min-width: 80px; text-align: center; padding: 16px 12px; background: #f8f9fa; border-radius: 8px; }
        .stat-item .number { font-size: 24px; font-weight: 600; color: #262626; }
        .stat-item .label { font-size: 12px; color: #8c8c8c; margin-top: 4px; }
        .stat-item.success .number { color: #52c41a; }
        .stat-item.failed .number { color: #ff4d4f; }
        .stat-item.warning .number { color: #faad14; }
        .stat-item.info .number { color: #1890ff; }
        .btn { display: block; text-align: center; padding: 12px 24px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: #fff; text-decoration: none; border-radius: 8px; font-size: 14px; font-weight: 500; }
        .btn:hover { opacity: 0.9; }
        .footer { text-align: center; padding: 16px 24px; background: #fafafa; color: #8c8c8c; font-size: 12px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>测试结果</h1>
            <span class="status {{status_class}}">{{status}}</span>
        </div>
        <div class="content">
            <table class="info-table">
                <tr>
                    <td>所属项目</td>
                    <td>{{project_name}}</td>
                </tr>
                <tr>
                    <td>测试人员</td>
                    <td>{{tester}}</td>
                </tr>
                <tr>
                    <td>开始时间</td>
                    <td>{{start_time}}</td>
                </tr>
                <tr>
                    <td>结束时间</td>
                    <td>{{end_time}}</td>
                </tr>
            </table>
            <div class="stats">
                <div class="stat-item info">
                    <div class="number">{{total_cases}}</div>
                    <div class="label">用例总数</div>
                </div>
                <div class="stat-item success">
                    <div class="number">{{passed_cases}}</div>
                    <div class="label">成功用例</div>
                </div>
                <div class="stat-item failed">
                    <div class="number">{{failed_cases}}</div>
                    <div class="label">失败用例</div>
                </div>
                <div class="stat-item warning">
                    <div class="number">{{error_cases}}</div>
                    <div class="label">错误用例</div>
                </div>
                <div class="stat-item">
                    <div class="number">{{skipped_cases}}</div>
                    <div class="label">跳过用例</div>
                </div>
            </div>
            <a href="{{report_url}}" class="btn">查看详细报告</a>
        </div>
        <div class="footer">
            此邮件由系统自动发送，请勿回复
        </div>
    </div>
</body>
</html>''',
                'description': '默认的邮件通知模板，类似钉钉/飞书卡片效果',
                'is_default': True,
                'is_active': True,
                'variables': [
                    'task_name', 'task_type', 'status', 'status_class', 'execution_time', 'tester',
                    'project_name', 'start_time', 'end_time',
                    'total_cases', 'passed_cases', 'failed_cases', 'error_cases',
                    'skipped_cases', 'pass_rate', 'report_url'
                ]
            },
            {
                'name': '简洁邮件模板',
                'template_type': 'markdown',
                'subject': '[TestHub] {{task_name}} 执行{{status}}',
                'content': '''**{{task_name}}** 执行{{status}}

- 总用例: {{total_cases}}
- 成功: {{passed_cases}}
- 失败: {{failed_cases}}
- 通过率: {{pass_rate}}

[查看报告]({{report_url}})''',
                'description': '简洁的邮件通知模板',
                'is_default': False,
                'is_active': True,
                'variables': [
                    'task_name', 'status', 'total_cases', 'passed_cases',
                    'failed_cases', 'pass_rate', 'report_url'
                ]
            },
            {
                'name': '卡片式邮件模板',
                'template_type': 'markdown',
                'subject': '【定时任务执行{{status}}】{{task_name}}',
                'content': '''【定时任务执行{{status}}】测试结果

| 项目 | 信息 |
|------|------|
| 所属项目 | {{project_name}} |
| 测试人员 | {{tester}} |
| 开始时间 | {{start_time}} |
| 结束时间 | {{end_time}} |

## 测试统计

| 统计项 | 数量 |
|---------|------|
| 用例总数 | {{total_cases}} |
| 成功用例 | {{passed_cases}} |
| 失败用例 | {{failed_cases}} |
| 错误用例 | {{error_cases}} |
| 跳过用例 | {{skipped_cases}} |

[查看详细报告]({{report_url}})''',
                'description': '卡片式邮件通知模板（Markdown格式）',
                'is_default': False,
                'is_active': True,
                'variables': [
                    'task_name', 'status', 'project_name', 'tester', 'start_time', 'end_time',
                    'total_cases', 'passed_cases', 'failed_cases', 'error_cases',
                    'skipped_cases', 'report_url'
                ]
            },
            {
                'name': '详细邮件模板',
                'template_type': 'html',
                'subject': '[TestHub] {{task_type}}任务执行{{status}}: {{task_name}}',
                'content': '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        h2 { color: #34495e; margin-top: 20px; }
        .info-box { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }
        .stat-box { display: inline-block; width: 30%; text-align: center; margin: 10px 1%; padding: 15px; background: #ecf0f1; border-radius: 5px; }
        .stat-number { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .stat-label { font-size: 12px; color: #7f8c8d; }
        .success { color: #27ae60; }
        .failed { color: #e74c3c; }
        .btn { display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }
        .footer { margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #7f8c8d; }
    </style>
</head>
<body>
    <h1>测试报告</h1>
    
    <div class="info-box">
        <p><strong>任务名称:</strong> {{task_name}}</p>
        <p><strong>任务类型:</strong> {{task_type}}</p>
        <p><strong>执行状态:</strong> <span class="{{status_class}}">{{status}}</span></p>
        <p><strong>执行时间:</strong> {{execution_time}}</p>
        <p><strong>测试人员:</strong> {{tester}}</p>
    </div>
    
    <h2>测试统计</h2>
    <div>
        <div class="stat-box">
            <div class="stat-number">{{total_cases}}</div>
            <div class="stat-label">总用例数</div>
        </div>
        <div class="stat-box">
            <div class="stat-number success">{{passed_cases}}</div>
            <div class="stat-label">成功用例</div>
        </div>
        <div class="stat-box">
            <div class="stat-number failed">{{failed_cases}}</div>
            <div class="stat-label">失败用例</div>
        </div>
    </div>
    
    <div class="info-box">
        <p><strong>错误用例:</strong> {{error_cases}}</p>
        <p><strong>跳过用例:</strong> {{skipped_cases}}</p>
        <p><strong>通过率:</strong> {{pass_rate}}</p>
    </div>
    
    <a href="{{report_url}}" class="btn">查看详细报告</a>
    
    <div class="footer">
        此邮件由系统自动发送，请勿回复。
    </div>
</body>
</html>''',
                'description': '详细的HTML邮件通知模板',
                'is_default': False,
                'is_active': True,
                'variables': [
                    'task_name', 'task_type', 'status', 'status_class', 'execution_time', 'tester',
                    'total_cases', 'passed_cases', 'failed_cases', 'error_cases',
                    'skipped_cases', 'pass_rate', 'report_url'
                ]
            },
        ]

        for template_data in templates:
            existing = NotificationTemplate.objects.filter(name=template_data['name']).first()

            if existing:
                self.stdout.write(f'模板已存在: {template_data["name"]}')
                existing.content = template_data['content']
                existing.subject = template_data['subject']
                existing.variables = template_data['variables']
                existing.description = template_data['description']
                existing.save()
                self.stdout.write(self.style.SUCCESS(f'更新模板: {template_data["name"]}'))
            else:
                NotificationTemplate.objects.create(**template_data)
                self.stdout.write(self.style.SUCCESS(f'创建模板: {template_data["name"]}'))

        self.stdout.write(self.style.SUCCESS('默认通知模板初始化完成'))
