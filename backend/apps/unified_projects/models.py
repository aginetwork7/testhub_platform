from django.db import models
from django.utils import timezone
from apps.users.models import User


class MetaProject(models.Model):
    """元项目 - 项目管理"""

    STATUS_CHOICES = [
        ('not_started', '未开始'),
        ('active', '进行中'),
        ('paused', '暂停'),
        ('completed', '已完成'),
        ('archived', '已归档'),
    ]

    name = models.CharField(max_length=200, verbose_name='项目名称')
    description = models.TextField(blank=True, verbose_name='项目描述')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started', verbose_name='状态')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meta_projects', verbose_name='负责人')
    unified_meta_project = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_projects',
        verbose_name='父项目'
    )
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'unified_meta_projects'
        verbose_name = '元项目'
        verbose_name_plural = '元项目'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def is_parent(self):
        return self.child_projects.exists()

    @property
    def is_child(self):
        return self.unified_meta_project is not None


class MetaProjectMember(models.Model):
    """元项目成员"""

    ROLE_CHOICES = [
        ('owner', '负责人'),
        ('admin', '管理员'),
        ('developer', '开发者'),
        ('tester', '测试者'),
        ('viewer', '观察者'),
    ]

    meta_project = models.ForeignKey(MetaProject, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tester', verbose_name='角色')
    joined_at = models.DateTimeField(default=timezone.now, verbose_name='加入时间')

    class Meta:
        db_table = 'unified_meta_project_members'
        unique_together = ['meta_project', 'user']
        verbose_name = '元项目成员'
        verbose_name_plural = '元项目成员'


class ProjectModule(models.Model):
    """项目模块 - 关联各模块的实际项目并存储特定配置"""

    MODULE_TYPE_CHOICES = [
        ('AI', 'AI用例生成'),
        ('AI_TEST', 'AI智能测试'),
        ('API', 'API测试'),
        ('UI', 'UI自动化'),
        ('APP', 'APP自动化'),
    ]

    meta_project = models.ForeignKey(
        MetaProject,
        on_delete=models.CASCADE,
        related_name='modules',
        verbose_name='所属元项目'
    )
    module_type = models.CharField(max_length=10, choices=MODULE_TYPE_CHOICES, verbose_name='模块类型')

    ai_project = models.OneToOneField(
        'ai_testing.AiProject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='module_config',
        verbose_name='AI项目'
    )
    api_project = models.OneToOneField(
        'api_testing.ApiProject',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='meta_module',
        verbose_name='API项目'
    )
    ui_project = models.OneToOneField(
        'ui_automation.UiProject',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='meta_module',
        verbose_name='UI项目'
    )
    app_project = models.OneToOneField(
        'app_automation.AppProject',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='meta_module',
        verbose_name='APP项目'
    )

    config = models.JSONField(default=dict, verbose_name='模块配置')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'unified_project_modules'
        unique_together = ['meta_project', 'module_type']
        verbose_name = '项目模块'
        verbose_name_plural = '项目模块'

    def __str__(self):
        return f"{self.meta_project.name} - {self.get_module_type_display()}"

    def get_project(self):
        """获取关联的实际项目"""
        if self.module_type == 'AI':
            try:
                return self.meta_project.project
            except Exception:
                return None
        elif self.module_type == 'AI_TEST' and self.ai_project:
            return self.ai_project
        elif self.module_type == 'API' and self.api_project:
            return self.api_project
        elif self.module_type == 'UI' and self.ui_project:
            return self.ui_project
        elif self.module_type == 'APP' and self.app_project:
            return self.app_project
        return None
