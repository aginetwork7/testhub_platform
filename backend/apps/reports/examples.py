"""
测试报告使用示例

演示如何创建和使用测试报告功能
"""
from datetime import datetime
from apps.reports.models import TestReport
from apps.users.models import User
from apps.projects.models import Project


def create_test_report_example():
    """
    创建测试报告示例
    
    使用场景：
    1. 测试执行完成后自动生成报告
    2. 定时任务执行后生成汇总报告
    3. 手动创建报告用于存档
    """
    
    # 获取用户和项目
    user = User.objects.first()
    project = Project.objects.first()
    
    # 创建测试报告
    report = TestReport.objects.create(
        name='UI自动化测试报告 - 登录模块',
        project=project,
        report_type='execution',
        status='completed',
        
        total_cases=50,
        passed_cases=45,
        failed_cases=3,
        skipped_cases=2,
        error_cases=0,
        duration=125.5,
        
        summary={
            'test_environment': '测试环境',
            'browser': 'Chrome 120',
            'test_date': '2026-03-07',
        },
        content={
            'modules': [
                {'name': '登录模块', 'passed': 20, 'failed': 1},
                {'name': '注册模块', 'passed': 15, 'failed': 2},
                {'name': '个人中心', 'passed': 10, 'failed': 0},
            ]
        },
        
        allure_report_url='http://localhost:8000/reports/allure/123/',
        environment_info={
            '操作系统': 'Windows 11',
            '浏览器': 'Chrome 120.0.6099.130',
            '测试环境': 'https://test.example.com',
            '执行引擎': 'Playwright',
        },
        
        started_at=datetime.now(),
        finished_at=datetime.now(),
        
        generated_by=user,
    )
    
    # 生成HTML报告
    html_content = report.generate_html_report()
    report.save()
    
    print(f'报告创建成功: {report.name}')
    print(f'通过率: {report.pass_rate:.1f}%')
    
    return report


def create_api_test_report_example():
    """
    创建API测试报告示例
    """
    user = User.objects.first()
    project = Project.objects.first()
    
    report = TestReport.objects.create(
        name='API接口测试报告 - 用户服务',
        project=project,
        report_type='execution',
        status='completed',
        
        total_cases=30,
        passed_cases=28,
        failed_cases=2,
        skipped_cases=0,
        error_cases=0,
        duration=45.3,
        
        summary={
            'base_url': 'https://api.example.com',
            'total_requests': 150,
            'avg_response_time': '120ms',
        },
        content={
            'endpoints': [
                {'path': '/api/users', 'method': 'GET', 'passed': 10, 'failed': 0},
                {'path': '/api/users', 'method': 'POST', 'passed': 8, 'failed': 1},
                {'path': '/api/auth', 'method': 'POST', 'passed': 10, 'failed': 1},
            ]
        },
        
        environment_info={
            'API版本': 'v2.0',
            '测试环境': 'https://api-test.example.com',
            '认证方式': 'Bearer Token',
        },
        
        started_at=datetime.now(),
        finished_at=datetime.now(),
        
        generated_by=user,
    )
    
    report.generate_html_report()
    report.save()
    
    return report


def create_app_test_report_example():
    """
    创建APP测试报告示例
    """
    user = User.objects.first()
    project = Project.objects.first()
    
    report = TestReport.objects.create(
        name='APP自动化测试报告 - iOS客户端',
        project=project,
        report_type='execution',
        status='completed',
        
        total_cases=25,
        passed_cases=22,
        failed_cases=2,
        skipped_cases=1,
        error_cases=0,
        duration=300.0,
        
        summary={
            'app_version': '2.5.0',
            'device': 'iPhone 15 Pro',
            'ios_version': '17.2',
        },
        content={
            'features': [
                {'name': '登录功能', 'passed': 5, 'failed': 0},
                {'name': '首页展示', 'passed': 8, 'failed': 1},
                {'name': '商品搜索', 'passed': 5, 'failed': 1},
                {'name': '订单流程', 'passed': 4, 'failed': 0},
            ]
        },
        
        environment_info={
            '设备': 'iPhone 15 Pro',
            'iOS版本': '17.2',
            'APP版本': '2.5.0',
            '执行框架': 'Appium 2.0',
        },
        
        started_at=datetime.now(),
        finished_at=datetime.now(),
        
        generated_by=user,
    )
    
    report.generate_html_report()
    report.save()
    
    return report


def send_report_via_email(report_id):
    """
    通过邮件发送测试报告
    
    Args:
        report_id: 测试报告ID
    """
    from apps.core.models import UnifiedNotificationConfig
    from django_q.tasks import async_task
    
    report = TestReport.objects.get(id=report_id)
    
    # 获取邮件通知配置
    email_config = UnifiedNotificationConfig.objects.filter(
        config_type='email',
        is_active=True
    ).first()
    
    if not email_config:
        print('未找到邮件通知配置')
        return
    
    recipients = email_config.get_email_recipients()
    if not recipients:
        print('未配置邮件收件人')
        return
    
    # 准备邮件内容
    subject = f'[TestHub] {report.name}'
    
    html_content = report.html_content or report.generate_html_report()
    
    # 异步发送邮件
    async_task(
        'services.email_service.email_service.send_notification_email',
        subject=subject,
        message=f'测试报告已生成，请查看附件或访问报告链接。',
        recipients=recipients,
        html_content=html_content,
        q_options={'group': '邮件通知'}
    )
    
    print(f'邮件已加入发送队列，收件人: {", ".join(recipients)}')


def get_report_statistics(project_id=None, days=7):
    """
    获取测试报告统计信息
    
    Args:
        project_id: 项目ID（可选）
        days: 统计天数
    
    Returns:
        dict: 统计信息
    """
    from django.utils import timezone
    from datetime import timedelta
    
    start_date = timezone.now() - timedelta(days=days)
    
    queryset = TestReport.objects.filter(created_at__gte=start_date)
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    
    total_reports = queryset.count()
    total_cases = sum(r.total_cases for r in queryset)
    total_passed = sum(r.passed_cases for r in queryset)
    total_failed = sum(r.failed_cases for r in queryset)
    
    avg_pass_rate = (total_passed / total_cases * 100) if total_cases > 0 else 0
    
    return {
        'total_reports': total_reports,
        'total_cases': total_cases,
        'total_passed': total_passed,
        'total_failed': total_failed,
        'avg_pass_rate': round(avg_pass_rate, 1),
        'period_days': days,
    }


if __name__ == '__main__':
    # 运行示例
    print('=== 测试报告使用示例 ===')
    print()
    
    # 1. 创建UI测试报告
    print('1. 创建UI测试报告...')
    ui_report = create_test_report_example()
    print(f'   报告ID: {ui_report.id}')
    print(f'   通过率: {ui_report.pass_rate:.1f}%')
    print()
    
    # 2. 创建API测试报告
    print('2. 创建API测试报告...')
    api_report = create_api_test_report_example()
    print(f'   报告ID: {api_report.id}')
    print(f'   通过率: {api_report.pass_rate:.1f}%')
    print()
    
    # 3. 创建APP测试报告
    print('3. 创建APP测试报告...')
    app_report = create_app_test_report_example()
    print(f'   报告ID: {app_report.id}')
    print(f'   通过率: {app_report.pass_rate:.1f}%')
    print()
    
    # 4. 获取统计信息
    print('4. 获取统计信息...')
    stats = get_report_statistics(days=30)
    print(f'   总报告数: {stats["total_reports"]}')
    print(f'   平均通过率: {stats["avg_pass_rate"]}%')
    print()
    
    # 5. 发送报告邮件
    print('5. 发送报告邮件...')
    send_report_via_email(ui_report.id)
