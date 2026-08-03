from django.db import models
from django.conf import settings
from apps.unified_projects.models import MetaProject

class AiProject(models.Model):
    """AI测试项目"""
    name = models.CharField(max_length=100, verbose_name='项目名称')
    description = models.TextField(blank=True, verbose_name='项目描述')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='创建者', related_name='ai_testing_projects')
    unified_meta_project = models.OneToOneField(MetaProject, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_module', verbose_name='关联元项目')

    class Meta:
        db_table = 'ai_testing_projects'
        verbose_name = 'AI测试项目'
        verbose_name_plural = 'AI测试项目'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class AICase(models.Model):
    """AI测试用例"""
    CASE_MODE_CHOICES = [
        ('freeform', '自由描述'),
        ('hybrid', '混合步骤'),
        ('structured', '结构化步骤'),
    ]

    project = models.ForeignKey(AiProject, on_delete=models.CASCADE, null=True, blank=True, verbose_name='所属项目')
    name = models.CharField(max_length=200, verbose_name='用例名称')
    description = models.TextField(blank=True, null=True, verbose_name='描述')
    task_description = models.TextField(verbose_name='任务描述', help_text='自然语言任务描述')
    case_mode = models.CharField(max_length=20, choices=CASE_MODE_CHOICES, default='freeform', verbose_name='用例模式')
    task_steps = models.JSONField(default=list, blank=True, verbose_name='结构化步骤')
    api_automation_configuration = models.ForeignKey(
        'api_automation.ApiAutomationConfiguration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_testing_cases',
        verbose_name='设备 CLI 环境',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='创建者', related_name='ai_testing_created_cases')

    class Meta:
        db_table = 'ai_testing_cases'
        verbose_name = 'AI测试用例'
        verbose_name_plural = 'AI测试用例'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class AIExecutionRecord(models.Model):
    """AI执行记录"""
    EXECUTION_MODE_CHOICES = [
        ('text', '文本模式'),
        ('hermes', 'Hermes模式'),
        ('planner_v2', 'Planner'),
    ]

    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('running', '执行中'),
        ('passed', '成功'),
        ('failed', '失败'),
        ('stopped', '已停止'),
    ]

    project = models.ForeignKey(AiProject, on_delete=models.CASCADE, null=True, blank=True, verbose_name='所属项目')
    ai_case = models.ForeignKey(AICase, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联AI用例')
    case_name = models.CharField(max_length=200, verbose_name='用例名称快照')
    task_description = models.TextField(blank=True, default='', verbose_name='任务描述', help_text='用户输入的原始任务描述')
    execution_mode = models.CharField(max_length=20, choices=EXECUTION_MODE_CHOICES, default='planner_v2', verbose_name='执行模式')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='执行状态')
    start_time = models.DateTimeField(auto_now_add=True, verbose_name='开始时间')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    duration = models.FloatField(null=True, blank=True, verbose_name='执行时长(秒)')
    logs = models.TextField(blank=True, default='', verbose_name='执行日志')
    steps_completed = models.JSONField(default=list, verbose_name='已完成步骤')
    planned_tasks = models.JSONField(default=list, verbose_name='规划任务') # 规划的任务列表 [{'id': 1, 'description': '...', 'status': 'pending'}]
    planner_trace = models.JSONField(default=dict, blank=True, verbose_name='规划追踪数据')
    artifacts = models.JSONField(default=list, blank=True, verbose_name='执行产物')
    cache_stats = models.JSONField(default=dict, blank=True, verbose_name='缓存统计')
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='执行人', related_name='ai_testing_executions')
    gif_path = models.CharField(max_length=500, null=True, blank=True, verbose_name='GIF录制路径')
    screenshots_sequence = models.JSONField(default=list, verbose_name='截图序列')

    class Meta:
        db_table = 'ai_testing_execution_records'
        verbose_name = 'AI测试报告'
        verbose_name_plural = 'AI测试报告'
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.case_name} - {self.get_status_display()}"
