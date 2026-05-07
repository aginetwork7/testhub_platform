"""
定时任务扩展模块
扩展 Django-Q Schedule 模型，添加业务字段
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django_q.models import Schedule

User = get_user_model()


class ScheduleConfig(models.Model):
    """
    定时任务配置扩展
    与 Django-Q Schedule 一对一关联，存储业务配置
    """
    MODULE_CHOICES = [
        ('API', 'API测试'),
        ('UI', 'UI自动化'),
        ('APP', 'APP自动化'),
    ]
    
    TASK_TYPE_CHOICES = [
        ('API_TEST_SUITE', 'API测试套件'),
        ('API_REQUEST', 'API请求'),
        ('UI_TEST_SUITE', 'UI测试套件'),
        ('UI_TEST_CASE', 'UI测试用例'),
        ('APP_TEST_SUITE', 'APP测试套件'),
        ('APP_TEST_CASE', 'APP测试用例'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', '激活'),
        ('PAUSED', '暂停'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失败'),
    ]
    
    schedule = models.OneToOneField(
        Schedule, on_delete=models.CASCADE, related_name='config',
        verbose_name='关联调度'
    )
    
    module = models.CharField(
        max_length=20, choices=MODULE_CHOICES, 
        verbose_name='所属模块'
    )
    task_type = models.CharField(
        max_length=30, choices=TASK_TYPE_CHOICES,
        verbose_name='任务类型'
    )
    
    project_id = models.IntegerField(
        null=True, blank=True, verbose_name='项目ID'
    )
    target_id = models.IntegerField(
        null=True, blank=True, verbose_name='目标ID'
    )
    environment_id = models.IntegerField(
        null=True, blank=True, verbose_name='环境ID'
    )
    
    task_config = models.JSONField(
        default=dict, blank=True, verbose_name='执行配置',
        help_text='存储引擎、浏览器、设备、测试用例列表等配置'
    )
    
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='ACTIVE',
        verbose_name='状态'
    )
    
    description = models.TextField(
        blank=True, default='', verbose_name='任务描述'
    )
    
    notify_on_success = models.BooleanField(
        default=False, verbose_name='成功时通知'
    )
    notify_on_failure = models.BooleanField(
        default=True, verbose_name='失败时通知'
    )
    notify_on_email = models.BooleanField(
        default=False, verbose_name='邮箱通知'
    )
    notify_on_webhook = models.BooleanField(
        default=False, verbose_name='Webhook机器人通知'
    )
    notification_configs = models.ManyToManyField(
        'core.UnifiedNotificationConfig',
        blank=True,
        verbose_name='通知配置',
        related_name='schedules',
        help_text='选择通知配置，用于发送通知时使用'
    )
    notify_emails = models.JSONField(
        default=list, blank=True, verbose_name='通知邮箱'
    )
    use_webhook = models.BooleanField(
        default=False, verbose_name='使用Webhook通知'
    )
    webhook_url = models.URLField(
        blank=True, default='', verbose_name='Webhook地址'
    )
    notification_template = models.ForeignKey(
        'core.NotificationTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='通知模板',
        related_name='schedule_configs',
        help_text='选择通知模板，用于发送通知时使用'
    )
    
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='创建者'
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='创建时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name='更新时间'
    )
    
    last_run_time = models.DateTimeField(
        null=True, blank=True, verbose_name='上次运行时间'
    )
    success_count = models.IntegerField(
        default=0, verbose_name='成功次数'
    )
    failure_count = models.IntegerField(
        default=0, verbose_name='失败次数'
    )
    
    class Meta:
        db_table = 'scheduler_schedule_config'
        verbose_name = '任务配置'
        verbose_name_plural = '任务配置'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"[{self.get_module_display()}] {self.schedule.name if self.schedule else '-'}"
    
    def pause(self):
        """暂停任务"""
        self.status = 'PAUSED'
        self.save()
        # 暂停时将next_run设置为None，防止Django-Q调度器执行
        self.schedule.next_run = None
        self.schedule.save()
    
    def resume(self):
        """恢复任务"""
        self.status = 'ACTIVE'
        self.save()
        # 恢复时重新计算next_run
        from django.utils import timezone
        self.schedule.next_run = timezone.now()
        self.schedule.save()
    
    def execute_now(self):
        """立即执行任务"""
        from apps.scheduler.task_executor import execute_task
        return execute_task(self.schedule_id)
    
    def update_stats(self, success=True):
        """更新执行统计"""
        from django.utils import timezone
        self.last_run_time = timezone.now()
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.save(update_fields=['last_run_time', 'success_count', 'failure_count'])


def get_task_function(task_type):
    """获取任务执行函数路径"""
    FUNCTION_MAP = {
        'API_TEST_SUITE': 'apps.scheduler.task_executor.execute_api_test_suite',
        'API_REQUEST': 'apps.scheduler.task_executor.execute_api_request',
        'UI_TEST_SUITE': 'apps.scheduler.task_executor.execute_ui_test_suite',
        'UI_TEST_CASE': 'apps.scheduler.task_executor.execute_ui_test_cases',
        'APP_TEST_SUITE': 'apps.scheduler.task_executor.execute_app_test_suite',
        'APP_TEST_CASE': 'apps.scheduler.task_executor.execute_app_test_cases',
    }
    return FUNCTION_MAP.get(task_type)


def create_scheduled_task(
    name,
    module,
    task_type,
    schedule_type,
    target_id=None,
    project_id=None,
    environment_id=None,
    task_config=None,
    cron=None,
    minutes=None,
    next_run=None,
    repeats=-1,
    created_by=None,
    description='',
    notify_on_success=False,
    notify_on_failure=True,
    notify_emails=None,
    webhook_url='',
    notification_template=None,
):
    """
    创建定时任务的统一入口
    
    Args:
        name: 任务名称
        module: 所属模块 (API/UI/APP)
        task_type: 任务类型
        schedule_type: 调度类型 (O/H/D/W/BW/M/BM/Q/Y/C)
        target_id: 目标ID（套件/用例/请求）
        project_id: 项目ID
        environment_id: 环境ID
        task_config: 执行配置字典
        cron: Cron表达式
        minutes: 分钟间隔
        next_run: 下次运行时间
        repeats: 重复次数 (-1=无限)
        created_by: 创建者
        description: 描述
        notify_on_success: 成功时通知
        notify_on_failure: 失败时通知
        notify_emails: 通知邮箱列表
        webhook_url: Webhook地址
        notification_template: 通知模板
    
    Returns:
        (Schedule, ScheduleConfig) 元组
    """
    func = get_task_function(task_type)
    if not func:
        raise ValueError(f"未知的任务类型: {task_type}")
    
    schedule = Schedule.objects.create(
        name=name,
        func=func,
        schedule_type=schedule_type,
        cron=cron,
        minutes=minutes,
        next_run=next_run or timezone.now(),
        repeats=repeats,
    )
    
    module_display = dict(ScheduleConfig.MODULE_CHOICES).get(module, module)
    schedule.args = []
    schedule.kwargs = {
        'schedule_id': schedule.id,
        'q_options': {
            'group': module_display
        }
    }
    schedule.save()
    
    config = ScheduleConfig.objects.create(
        schedule=schedule,
        module=module,
        task_type=task_type,
        project_id=project_id,
        target_id=target_id,
        environment_id=environment_id,
        task_config=task_config or {},
        status='ACTIVE',
        description=description,
        notify_on_success=notify_on_success,
        notify_on_failure=notify_on_failure,
        notify_emails=notify_emails or [],
        webhook_url=webhook_url,
        notification_template=notification_template,
        created_by=created_by,
    )
    
    return schedule, config
