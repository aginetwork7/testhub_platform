import json
from base64 import urlsafe_b64encode
from hashlib import sha256

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


class ApiAutomationProject(models.Model):
    STATUS_CHOICES = [
        ('active', '进行中'),
        ('paused', '暂停'),
        ('archived', '已归档'),
    ]

    name = models.CharField(max_length=200, unique=True, verbose_name='项目名称')
    description = models.TextField(blank=True, verbose_name='项目描述')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name='项目状态')
    websocket_params = models.JSONField(default=dict, verbose_name='WebSocket协议参数')
    websocket_schemas = models.JSONField(default=dict, verbose_name='WebSocket响应Schema')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_api_automation_projects',
        verbose_name='负责人',
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='api_automation_projects',
        verbose_name='团队成员',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_automation_projects'
        ordering = ['-created_at']
        verbose_name = 'API自动化项目'
        verbose_name_plural = 'API自动化项目'

    def __str__(self) -> str:
        return self.name


class ApiAutomationSuite(models.Model):
    project = models.ForeignKey(
        ApiAutomationProject,
        on_delete=models.CASCADE,
        related_name='suites',
        verbose_name='所属项目',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父级套件',
    )
    name = models.CharField(max_length=200, verbose_name='套件名称')
    source_path = models.CharField(max_length=500, verbose_name='来源相对路径')
    description = models.TextField(blank=True, verbose_name='描述')
    order = models.PositiveIntegerField(default=0, verbose_name='排序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_automation_suites'
        ordering = ['order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['project', 'source_path'], name='unique_api_automation_suite_path'),
        ]
        verbose_name = 'API自动化套件'
        verbose_name_plural = 'API自动化套件'

    def __str__(self) -> str:
        return self.source_path


class ApiAutomationEndpoint(models.Model):
    project = models.ForeignKey(
        ApiAutomationProject,
        on_delete=models.CASCADE,
        related_name='endpoints',
        verbose_name='所属项目',
    )
    key = models.CharField(max_length=300, verbose_name='接口别名')
    path = models.CharField(max_length=1000, verbose_name='接口路径')
    description = models.TextField(blank=True, verbose_name='描述')
    methods = models.JSONField(default=list, verbose_name='HTTP方法')
    tags = models.JSONField(default=list, verbose_name='Swagger标签')
    summary = models.CharField(max_length=500, blank=True, verbose_name='接口摘要')
    deprecated = models.BooleanField(default=False, verbose_name='是否废弃')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_automation_endpoints'
        ordering = ['key']
        constraints = [
            models.UniqueConstraint(fields=['project', 'key'], name='unique_api_automation_endpoint_key'),
        ]
        verbose_name = 'API自动化接口目录'
        verbose_name_plural = 'API自动化接口目录'

    def __str__(self) -> str:
        return self.key


class ApiAutomationCoverageSnapshot(models.Model):
    PERIOD_CHOICES = [
        ('WEEKLY', '每周'),
        ('MONTHLY', '每月'),
    ]

    project = models.ForeignKey(
        ApiAutomationProject,
        on_delete=models.CASCADE,
        related_name='coverage_snapshots',
        verbose_name='所属项目',
    )
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES, verbose_name='统计周期')
    snapshot_date = models.DateField(verbose_name='快照日期')
    total_endpoints = models.PositiveIntegerField(default=0, verbose_name='接口总数')
    covered_endpoints = models.PositiveIntegerField(default=0, verbose_name='已覆盖接口数')
    coverage_rate = models.FloatField(default=0, verbose_name='覆盖率')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'api_automation_coverage_snapshots'
        ordering = ['period', 'snapshot_date']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'period', 'snapshot_date'],
                name='unique_api_automation_coverage_snapshot',
            ),
        ]
        verbose_name = 'API自动化覆盖率快照'
        verbose_name_plural = 'API自动化覆盖率快照'


class ApiAutomationSchemaSnapshot(models.Model):
    project = models.ForeignKey(ApiAutomationProject, on_delete=models.CASCADE, related_name='schema_snapshots')
    source_hash = models.CharField(max_length=64)
    schema_count = models.PositiveIntegerField(default=0)
    schema_fingerprints = models.JSONField(default=dict)
    change_summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_automation_schema_snapshots'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['project', '-created_at'])]


class ApiAutomationCase(models.Model):
    PRIORITY_CHOICES = [
        ('P0', 'P0'),
        ('P1', 'P1'),
        ('P2', 'P2'),
    ]
    EXECUTION_MODE_CHOICES = [
        ('STRUCTURED', '结构化执行'),
        ('CODE', '代码执行'),
        ('MANUAL_REVIEW', '待人工完善'),
    ]

    suite = models.ForeignKey(
        ApiAutomationSuite,
        on_delete=models.CASCADE,
        related_name='cases',
        verbose_name='所属套件',
    )
    name = models.CharField(max_length=300, verbose_name='用例名称')
    description = models.TextField(blank=True, verbose_name='用例描述')
    source_path = models.CharField(max_length=500, verbose_name='来源相对路径')
    source_class = models.CharField(max_length=200, verbose_name='来源测试类')
    source_function = models.CharField(max_length=300, verbose_name='来源测试方法')
    node_id = models.CharField(max_length=255, unique=True, verbose_name='pytest节点ID')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='P2', verbose_name='优先级')
    markers = models.JSONField(default=list, verbose_name='pytest标记')
    parameter_sets = models.JSONField(default=list, verbose_name='参数化数据')
    capabilities = models.JSONField(default=list, verbose_name='运行能力依赖')
    module_imports = models.TextField(blank=True, verbose_name='模块导入代码')
    module_support_code = models.TextField(blank=True, verbose_name='模块辅助代码')
    class_support_code = models.TextField(blank=True, verbose_name='测试类辅助代码')
    support_code = models.TextField(blank=True, verbose_name='辅助代码')
    source_code = models.TextField(verbose_name='原始用例代码')
    setup_code = models.TextField(blank=True, verbose_name='前置代码')
    teardown_code = models.TextField(blank=True, verbose_name='后置代码')
    execution_mode = models.CharField(
        max_length=30,
        choices=EXECUTION_MODE_CHOICES,
        default='MANUAL_REVIEW',
        verbose_name='执行模式',
    )
    is_skipped = models.BooleanField(default=False, verbose_name='是否跳过')
    skip_reason = models.CharField(max_length=500, blank=True, verbose_name='跳过原因')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    source_hash = models.CharField(max_length=64, verbose_name='来源哈希')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_automation_cases'
        ordering = ['source_path', 'source_class', 'source_function']
        indexes = [
            models.Index(fields=['suite', 'priority']),
            models.Index(fields=['source_path']),
            models.Index(fields=['execution_mode']),
        ]
        verbose_name = 'API自动化用例'
        verbose_name_plural = 'API自动化用例'

    def __str__(self) -> str:
        return self.node_id


class ApiAutomationStep(models.Model):
    STEP_TYPE_CHOICES = [
        ('AUTHENTICATE', '认证'),
        ('HTTP_REQUEST', 'HTTP请求'),
        ('WEBSOCKET_REQUEST', 'WebSocket请求'),
        ('PAYMENT_ACTION', '支付操作'),
        ('MODEL_REQUEST', '模型请求'),
        ('PYTHON', 'Python代码'),
    ]

    case = models.ForeignKey(ApiAutomationCase, on_delete=models.CASCADE, related_name='steps', verbose_name='所属用例')
    order = models.PositiveIntegerField(verbose_name='执行顺序')
    name = models.CharField(max_length=300, verbose_name='步骤名称')
    step_type = models.CharField(max_length=30, choices=STEP_TYPE_CHOICES, verbose_name='步骤类型')
    request_data = models.JSONField(default=dict, blank=True, verbose_name='请求定义')
    assertions = models.JSONField(default=list, blank=True, verbose_name='断言定义')
    code = models.TextField(blank=True, verbose_name='代码片段')
    is_executable = models.BooleanField(default=False, verbose_name='是否可执行')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_automation_steps'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['case', 'order'], name='unique_api_automation_step_order'),
        ]
        verbose_name = 'API自动化步骤'
        verbose_name_plural = 'API自动化步骤'


class ApiAutomationConfiguration(models.Model):
    project = models.ForeignKey(
        ApiAutomationProject,
        on_delete=models.CASCADE,
        related_name='configurations',
        verbose_name='所属项目',
    )
    name = models.CharField(max_length=200, verbose_name='配置名称')
    environment = models.CharField(max_length=50, default='custom', verbose_name='运行环境')
    base_url = models.URLField(blank=True, verbose_name='HTTP基础地址')
    web_url = models.URLField(blank=True, verbose_name='Web地址')
    websocket_url = models.URLField(blank=True, verbose_name='WebSocket地址')
    variables = models.JSONField(default=dict, verbose_name='环境变量')
    auth_profiles = models.JSONField(default=dict, verbose_name='认证角色配置')
    payment_config = models.JSONField(default=dict, verbose_name='支付服务配置')
    model_profiles = models.JSONField(default=dict, verbose_name='模型服务配置')
    runtime_settings = models.JSONField(default=dict, verbose_name='测试运行设置')
    event_device_keys_encrypted = models.TextField(blank=True, default='', verbose_name='事件设备私钥密文')
    timeout_seconds = models.PositiveIntegerField(default=30, verbose_name='请求超时秒数')
    max_workers = models.PositiveIntegerField(default=1, verbose_name='并发数')
    is_default = models.BooleanField(default=False, verbose_name='是否默认配置')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='创建人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_automation_configurations'
        ordering = ['-is_default', 'name']
        constraints = [
            models.UniqueConstraint(fields=['project', 'name'], name='unique_api_automation_configuration_name'),
            models.UniqueConstraint(fields=['project', 'environment'], name='unique_api_automation_configuration_environment'),
        ]
        verbose_name = 'API自动化配置'
        verbose_name_plural = 'API自动化配置'

    @staticmethod
    def _event_device_key_cipher() -> Fernet:
        encryption_key = urlsafe_b64encode(sha256(settings.SECRET_KEY.encode('utf-8')).digest())
        return Fernet(encryption_key)

    def get_event_device_key(self, device: str) -> str:
        if device not in {'main', 'backup'} or not self.event_device_keys_encrypted:
            return ''
        try:
            payload = self._event_device_key_cipher().decrypt(
                self.event_device_keys_encrypted.encode('utf-8')
            )
            device_keys = json.loads(payload.decode('utf-8'))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
            return ''
        return str(device_keys.get(device, '')) if isinstance(device_keys, dict) else ''

    def set_event_device_keys(
        self,
        main_device_key: str | None = None,
        backup_device_key: str | None = None,
    ) -> None:
        device_keys = {
            'main': self.get_event_device_key('main'),
            'backup': self.get_event_device_key('backup'),
        }
        if main_device_key is not None:
            device_keys['main'] = main_device_key.strip()
        if backup_device_key is not None:
            device_keys['backup'] = backup_device_key.strip()
        serialized = json.dumps(device_keys, ensure_ascii=False).encode('utf-8')
        self.event_device_keys_encrypted = self._event_device_key_cipher().encrypt(serialized).decode('utf-8')


class ApiAutomationRun(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '待执行'),
        ('RUNNING', '执行中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失败'),
        ('CANCELLED', '已取消'),
    ]

    project = models.ForeignKey(ApiAutomationProject, on_delete=models.CASCADE, related_name='runs', verbose_name='所属项目')
    configuration = models.ForeignKey(
        ApiAutomationConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='runs',
        verbose_name='执行配置',
    )
    selection = models.JSONField(default=dict, verbose_name='用例选择条件')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name='执行状态')
    total_cases = models.PositiveIntegerField(default=0, verbose_name='用例总数')
    passed_cases = models.PositiveIntegerField(default=0, verbose_name='通过数')
    schema_warning_cases = models.PositiveIntegerField(default=0, verbose_name='Schema告警数')
    failed_cases = models.PositiveIntegerField(default=0, verbose_name='失败数')
    skipped_cases = models.PositiveIntegerField(default=0, verbose_name='跳过数')
    current_case_name = models.CharField(max_length=255, blank=True, verbose_name='当前执行用例')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    log_content = models.TextField(blank=True, verbose_name='执行日志')
    report_path = models.CharField(max_length=1000, blank=True, verbose_name='报告路径')
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='执行人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'api_automation_runs'
        ordering = ['-created_at']
        verbose_name = 'API自动化执行记录'
        verbose_name_plural = 'API自动化执行记录'


class ApiAutomationNotificationLog(models.Model):
    CHANNEL_CHOICES = [
        ('EMAIL', '邮件'),
        ('WEBHOOK', 'Webhook'),
        ('MULTI', '邮件与Webhook'),
        ('NONE', '未配置渠道'),
    ]
    STATUS_CHOICES = [
        ('DISPATCHED', '已派发'),
        ('SKIPPED', '未派发'),
    ]

    project = models.ForeignKey(ApiAutomationProject, on_delete=models.CASCADE, related_name='notification_logs')
    run = models.ForeignKey(ApiAutomationRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='notification_logs')
    schedule_id = models.IntegerField(null=True, blank=True)
    schedule_name = models.CharField(max_length=200)
    execution_status = models.CharField(max_length=20, choices=ApiAutomationRun.STATUS_CHOICES)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    targets = models.JSONField(default=list, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_automation_notification_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'created_at']),
            models.Index(fields=['run']),
        ]

    def __str__(self):
        return f'{self.schedule_name} - {self.get_status_display()}'


class ApiAutomationCaseResult(models.Model):
    RESULT_STATUS_CHOICES = [
        ('PASSED', '通过'),
        ('SCHEMA_WARNING', '通过（Schema告警）'),
        ('FAILED', '失败'),
        ('SKIPPED', '跳过'),
        ('ERROR', '错误'),
    ]

    run = models.ForeignKey(ApiAutomationRun, on_delete=models.CASCADE, related_name='case_results', verbose_name='所属执行')
    case = models.ForeignKey(ApiAutomationCase, on_delete=models.CASCADE, related_name='results', verbose_name='测试用例')
    status = models.CharField(max_length=20, choices=RESULT_STATUS_CHOICES, verbose_name='执行状态')
    duration_ms = models.FloatField(null=True, blank=True, verbose_name='耗时毫秒')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    trace = models.TextField(blank=True, verbose_name='错误堆栈')
    details = models.JSONField(default=dict, verbose_name='执行详情')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'api_automation_case_results'
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['run', 'case'], name='unique_api_automation_run_case'),
        ]
        verbose_name = 'API自动化用例结果'
        verbose_name_plural = 'API自动化用例结果'