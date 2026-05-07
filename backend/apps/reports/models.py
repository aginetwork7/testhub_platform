from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.projects.models import Project
from apps.executions.models import TestRun


class TestReport(models.Model):
    """测试报告"""
    TYPE_CHOICES = [
        ('execution', '执行报告'),
        ('summary', '汇总报告'),
        ('trend', '趋势报告'),
    ]
    
    STATUS_CHOICES = [
        ('running', '执行中'),
        ('completed', '已完成'),
        ('failed', '执行失败'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reports')
    name = models.CharField(max_length=200, verbose_name='报告名称')
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='execution', verbose_name='报告类型')
    execution = models.OneToOneField(TestRun, on_delete=models.CASCADE, null=True, blank=True, related_name='report', verbose_name='关联执行')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running', verbose_name='状态')
    
    total_cases = models.IntegerField(default=0, verbose_name='总用例数')
    passed_cases = models.IntegerField(default=0, verbose_name='通过数')
    failed_cases = models.IntegerField(default=0, verbose_name='失败数')
    skipped_cases = models.IntegerField(default=0, verbose_name='跳过数')
    error_cases = models.IntegerField(default=0, verbose_name='错误数')
    duration = models.FloatField(default=0, verbose_name='执行时长(秒)')
    
    summary = models.JSONField(default=dict, verbose_name='报告摘要')
    content = models.JSONField(default=dict, verbose_name='报告内容')
    html_content = models.TextField(blank=True, verbose_name='HTML报告内容')
    allure_report_url = models.URLField(blank=True, default='', verbose_name='Allure报告链接')
    environment_info = models.JSONField(default=dict, blank=True, verbose_name='环境信息')
    
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generated_reports', verbose_name='生成者')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'test_reports'
        verbose_name = '测试报告'
        verbose_name_plural = '测试报告'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.get_report_type_display()}"
    
    @property
    def pass_rate(self):
        """计算通过率"""
        if self.total_cases == 0:
            return 0
        return (self.passed_cases / self.total_cases) * 100
    
    def generate_html_report(self):
        """生成HTML报告"""
        from utils.html_report import html_report_generator
        
        report_type_display = self.get_report_type_display()
        
        self.html_content = html_report_generator.generate_simple_report(
            title=self.name,
            test_type=report_type_display,
            total=self.total_cases,
            passed=self.passed_cases,
            failed=self.failed_cases,
            skipped=self.skipped_cases,
            duration=self.duration,
            report_url=self.allure_report_url if self.allure_report_url else None
        )
        return self.html_content

class ReportTemplate(models.Model):
    """报告模板"""
    name = models.CharField(max_length=200, verbose_name='模板名称')
    description = models.TextField(blank=True, verbose_name='模板描述')
    template_config = models.JSONField(default=dict, verbose_name='模板配置')
    is_default = models.BooleanField(default=False, verbose_name='是否默认')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    
    class Meta:
        db_table = 'report_templates'
        verbose_name = '报告模板'
        verbose_name_plural = '报告模板'