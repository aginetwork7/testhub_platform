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
    PRIORITY_CHOICES = [
        ('P0', 'P0'),
        ('P1', 'P1'),
        ('P2', 'P2'),
    ]

    project = models.ForeignKey(AiProject, on_delete=models.CASCADE, null=True, blank=True, verbose_name='所属项目')
    name = models.CharField(max_length=200, verbose_name='用例名称')
    case_number = models.CharField(max_length=50, blank=True, default='', verbose_name='用例编号')
    priority = models.CharField(max_length=2, choices=PRIORITY_CHOICES, default='P0', verbose_name='优先级')
    description = models.TextField(blank=True, null=True, verbose_name='描述')
    task_description = models.TextField(verbose_name='任务描述', help_text='自然语言任务描述')
    case_mode = models.CharField(max_length=20, choices=CASE_MODE_CHOICES, default='freeform', verbose_name='用例模式')
    task_steps = models.JSONField(default=list, blank=True, verbose_name='结构化步骤')
    planned_steps = models.JSONField(default=list, blank=True, verbose_name='Planner执行步骤')
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


class AIExecutionExperience(models.Model):
    """A verified, reusable action sequence for one AI-planned step."""

    STATUS_CHOICES = [
        ('verified', '已验证'),
        ('invalid', '已失效'),
    ]
    REVIEW_STATUS_CHOICES = [
        ('auto_verified', '自动验证'),
        ('confirmed', '人工确认'),
        ('rejected', '人工拒绝'),
    ]

    project = models.ForeignKey(AiProject, on_delete=models.CASCADE, related_name='execution_experiences')
    ai_case = models.ForeignKey(AICase, on_delete=models.SET_NULL, null=True, blank=True, related_name='execution_experiences')
    execution_record = models.ForeignKey(AIExecutionRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='experiences')
    step_description = models.TextField(verbose_name='步骤描述')
    intent_hash = models.CharField(max_length=64, db_index=True, verbose_name='步骤语义哈希')
    page_url = models.CharField(max_length=1000, blank=True, default='', verbose_name='页面地址')
    page_fingerprint = models.CharField(max_length=64, blank=True, default='', db_index=True, verbose_name='页面指纹')
    environment_key = models.CharField(max_length=200, blank=True, default='', verbose_name='环境标识')
    action_sequence = models.JSONField(default=list, verbose_name='已验证动作序列')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='verified', db_index=True, verbose_name='状态')
    review_status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default='auto_verified', verbose_name='审核状态')
    review_note = models.TextField(blank=True, default='', verbose_name='审核备注')
    success_count = models.PositiveIntegerField(default=1, verbose_name='成功次数')
    failure_count = models.PositiveIntegerField(default=0, verbose_name='失败次数')
    confidence = models.FloatField(default=0.7, verbose_name='置信度')
    last_verified_at = models.DateTimeField(auto_now=True, verbose_name='最近验证时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'ai_testing_execution_experiences'
        verbose_name = 'AI执行经验'
        verbose_name_plural = 'AI执行经验'
        ordering = ['-confidence', '-last_verified_at']
        indexes = [
            models.Index(fields=['project', 'intent_hash', 'status'], name='ai_testing__project_37575f_idx'),
            models.Index(fields=['project', 'page_fingerprint', 'status'], name='ai_testing__project_e20de4_idx'),
        ]

    def __str__(self):
        return f'{self.project.name}: {self.step_description[:60]}'


class AlphaRun(models.Model):
    """Durable owner-scoped Alpha workflow instance."""

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('collecting_input', '收集参数'),
        ('planning', '规划中'),
        ('awaiting_confirmation', '等待确认'),
        ('executing', '执行中'),
        ('reflecting', '反思中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]

    project = models.ForeignKey(
        AiProject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alpha_runs',
        verbose_name='所属项目',
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='alpha_runs',
        verbose_name='发起人',
    )
    original_request = models.TextField(verbose_name='原始目标')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='draft', db_index=True)
    round_count = models.PositiveSmallIntegerField(default=0, verbose_name='已完成规划轮次')
    state_version = models.PositiveIntegerField(default=1, verbose_name='状态版本')
    planner_task_id = models.CharField(max_length=64, blank=True, default='', verbose_name='规划任务ID')
    reflection_task_id = models.CharField(max_length=64, blank=True, default='', verbose_name='反思任务ID')
    active_revision = models.ForeignKey(
        'AlphaPlanRevision',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='当前计划版本',
    )
    final_output = models.JSONField(null=True, blank=True, verbose_name='最终输出')
    error_message = models.TextField(blank=True, default='', verbose_name='错误信息')
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name='取消时间')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_testing_alpha_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['initiated_by', 'status']),
            models.Index(fields=['project', 'status']),
        ]


class AlphaPlanRevision(models.Model):
    """Append-only plan revision that freezes before execution."""

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('frozen', '已冻结'),
        ('superseded', '已替代'),
    ]

    run = models.ForeignKey(AlphaRun, on_delete=models.CASCADE, related_name='revisions')
    revision_number = models.PositiveSmallIntegerField(verbose_name='版本号')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft', db_index=True)
    planner_input = models.JSONField(default=dict, blank=True, verbose_name='规划输入快照')
    planner_output = models.JSONField(default=dict, blank=True, verbose_name='规划输出快照')
    content_hash = models.CharField(max_length=64, blank=True, default='', verbose_name='内容哈希')
    frozen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_testing_alpha_plan_revisions'
        ordering = ['run_id', 'revision_number']
        constraints = [
            models.UniqueConstraint(fields=['run', 'revision_number'], name='alpha_unique_run_revision'),
        ]


class AlphaTaskNode(models.Model):
    """A single versioned task node with presentation hierarchy and execution state."""

    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('awaiting_confirmation', '等待确认'),
        ('dispatched', '已派发'),
        ('running', '执行中'),
        ('succeeded', '成功'),
        ('failed', '失败'),
        ('blocked', '阻塞'),
        ('skipped', '跳过'),
        ('cancelled', '已取消'),
        ('superseded', '已替代'),
    ]
    TIER_CHOICES = [('read', '只读'), ('run', '运行'), ('write', '写入')]

    revision = models.ForeignKey(AlphaPlanRevision, on_delete=models.CASCADE, related_name='task_nodes')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
    )
    task_key = models.CharField(max_length=100, verbose_name='任务键')
    display_order = models.PositiveIntegerField(default=0)
    skill_name = models.CharField(max_length=120, verbose_name='注册技能名称')
    skill_version = models.CharField(max_length=40, blank=True, default='')
    tier = models.CharField(max_length=16, choices=TIER_CHOICES)
    risk_metadata = models.JSONField(default=dict, blank=True)
    normalized_arguments = models.JSONField(default=dict, blank=True)
    arguments_hash = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    evidence = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_testing_alpha_task_nodes'
        ordering = ['revision_id', 'display_order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['revision', 'task_key'], name='alpha_unique_revision_task_key'),
        ]
        indexes = [
            models.Index(fields=['revision', 'status']),
        ]


class AlphaTaskDependency(models.Model):
    """Execution dependency, deliberately separate from task hierarchy."""

    task = models.ForeignKey(AlphaTaskNode, on_delete=models.CASCADE, related_name='dependencies')
    depends_on = models.ForeignKey(AlphaTaskNode, on_delete=models.CASCADE, related_name='dependent_tasks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_testing_alpha_task_dependencies'
        constraints = [
            models.UniqueConstraint(fields=['task', 'depends_on'], name='alpha_unique_task_dependency'),
        ]


class AlphaParameterRequest(models.Model):
    """Machine-readable parameter requirement resolved against one plan revision."""

    STATUS_CHOICES = [('pending', '待填写'), ('valid', '有效'), ('invalid', '无效')]

    revision = models.ForeignKey(AlphaPlanRevision, on_delete=models.CASCADE, related_name='parameter_requests')
    task = models.ForeignKey(
        AlphaTaskNode,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='parameter_requests',
    )
    field_key = models.CharField(max_length=100)
    field_schema = models.JSONField(default=dict)
    answer = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    validation_error = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_testing_alpha_parameter_requests'
        constraints = [
            models.UniqueConstraint(fields=['revision', 'task', 'field_key'], name='alpha_unique_parameter_field'),
        ]


class AlphaApprovalRequest(models.Model):
    """Exact, expiring user approval for a risky task action."""

    STATUS_CHOICES = [('pending', '待确认'), ('approved', '已批准'), ('rejected', '已拒绝'), ('expired', '已过期'), ('invalidated', '已失效')]

    run = models.ForeignKey(AlphaRun, on_delete=models.CASCADE, related_name='approval_requests')
    revision = models.ForeignKey(AlphaPlanRevision, on_delete=models.CASCADE, related_name='approval_requests')
    task = models.ForeignKey(AlphaTaskNode, on_delete=models.CASCADE, related_name='approval_requests')
    arguments_hash = models.CharField(max_length=64)
    risk_metadata = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alpha_approvals',
    )

    class Meta:
        db_table = 'ai_testing_alpha_approval_requests'
        indexes = [
            models.Index(fields=['task', 'status', 'expires_at']),
        ]


class AlphaDispatchIntent(models.Model):
    """Transactional outbox record for idempotent worker dispatch."""

    STATUS_CHOICES = [('pending', '待派发'), ('claimed', '已领取'), ('dispatched', '已派发'), ('failed', '失败'), ('cancelled', '已取消')]

    task = models.ForeignKey(AlphaTaskNode, on_delete=models.CASCADE, related_name='dispatch_intents')
    idempotency_key = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_testing_alpha_dispatch_intents'
        indexes = [
            models.Index(fields=['status', 'lease_expires_at']),
        ]


class AlphaExternalRun(models.Model):
    """Normalized reference and status for one external run-tier execution."""

    STATUS_CHOICES = [('pending', '等待中'), ('running', '运行中'), ('succeeded', '成功'), ('failed', '失败'), ('cancelled', '已取消'), ('timed_out', '超时')]

    task = models.ForeignKey(AlphaTaskNode, on_delete=models.CASCADE, related_name='external_runs')
    external_reference = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)
    cancellation_supported = models.BooleanField(default=False)
    details = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_testing_alpha_external_runs'
        constraints = [
            models.UniqueConstraint(fields=['task', 'external_reference'], name='alpha_unique_external_reference'),
        ]


class AlphaRound(models.Model):
    """Immutable planner/reflection artifact for one completed workflow cycle."""

    run = models.ForeignKey(AlphaRun, on_delete=models.CASCADE, related_name='rounds')
    revision = models.OneToOneField(AlphaPlanRevision, on_delete=models.CASCADE, related_name='round_artifact')
    sequence = models.PositiveSmallIntegerField()
    planner_model = models.CharField(max_length=100, blank=True, default='')
    reflection_model = models.CharField(max_length=100, blank=True, default='')
    planner_input = models.JSONField(default=dict, blank=True)
    planner_output = models.JSONField(default=dict, blank=True)
    reflection_input = models.JSONField(default=dict, blank=True)
    reflection_verdict = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_testing_alpha_rounds'
        constraints = [
            models.UniqueConstraint(fields=['run', 'sequence'], name='alpha_unique_run_round'),
        ]
