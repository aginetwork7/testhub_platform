from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class ApiProject(models.Model):
    """API项目模型"""
    PROJECT_TYPE_CHOICES = [
        ('HTTP', 'HTTP'),
        ('WEBSOCKET', 'WebSocket'),
    ]

    STATUS_CHOICES = [
        ('not_started', '未开始'),
        ('active', '进行中'),
        ('paused', '暂停'),
        ('completed', '已完成'),
        ('archived', '已归档'),
    ]

    name = models.CharField(max_length=200, verbose_name='项目名称')
    description = models.TextField(blank=True, verbose_name='项目描述')
    project_type = models.CharField(max_length=20, choices=PROJECT_TYPE_CHOICES, verbose_name='项目类型')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name='项目状态')
    start_date = models.DateField(null=True, blank=True, verbose_name='开始日期')
    end_date = models.DateField(null=True, blank=True, verbose_name='结束日期')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_api_projects', verbose_name='负责人')
    members = models.ManyToManyField(User, blank=True, related_name='api_projects', verbose_name='团队成员')
    unified_meta_project = models.OneToOneField(
        'unified_projects.MetaProject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='api_project',
        verbose_name='统一元项目'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_projects'
        verbose_name = 'API项目'
        verbose_name_plural = 'API项目'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class ApiCollection(models.Model):
    """API集合模型"""
    name = models.CharField(max_length=200, verbose_name='集合名称')
    description = models.TextField(blank=True, verbose_name='集合描述')
    order = models.IntegerField(default=0, verbose_name='排序')
    project = models.ForeignKey(ApiProject, on_delete=models.CASCADE, related_name='collections',
                                verbose_name='所属项目')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children',
                               verbose_name='父级集合')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_collections'
        verbose_name = 'API集合'
        verbose_name_plural = 'API集合'
        ordering = ['order', 'created_at']

    def __str__(self):
        return self.name


class ApiRequest(models.Model):
    """API请求模型"""
    REQUEST_TYPE_CHOICES = [
        ('HTTP', 'HTTP'),
        ('WEBSOCKET', 'WebSocket'),
    ]

    HTTP_METHODS = [
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('DELETE', 'DELETE'),
        ('PATCH', 'PATCH'),
        ('HEAD', 'HEAD'),
        ('OPTIONS', 'OPTIONS'),
    ]

    collection = models.ForeignKey(ApiCollection, on_delete=models.CASCADE, null=True, blank=True,
                                   related_name='requests', verbose_name='所属集合')
    name = models.CharField(max_length=200, verbose_name='请求名称')
    description = models.TextField(blank=True, verbose_name='请求描述')
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES, default='HTTP',
                                    verbose_name='请求类型')
    method = models.CharField(max_length=10, choices=HTTP_METHODS, default='GET', verbose_name='请求方法')
    url = models.TextField(verbose_name='请求URL')
    headers = models.JSONField(default=dict, verbose_name='请求头')
    params = models.JSONField(default=dict, verbose_name='URL参数')
    body = models.JSONField(default=dict, verbose_name='请求体')
    auth = models.JSONField(default=dict, verbose_name='认证信息')
    pre_request_script = models.TextField(blank=True, verbose_name='请求前脚本')
    post_request_script = models.TextField(blank=True, verbose_name='请求后脚本')
    assertions = models.JSONField(default=list, verbose_name='断言规则')
    order = models.IntegerField(default=0, verbose_name='排序')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_requests'
        verbose_name = 'API请求'
        verbose_name_plural = 'API请求'
        ordering = ['order', 'created_at']

    def __str__(self):
        return self.name


class Environment(models.Model):
    """环境变量模型"""
    SCOPE_CHOICES = [
        ('GLOBAL', '全局环境变量'),
        ('LOCAL', '局部环境变量'),
    ]

    name = models.CharField(max_length=200, verbose_name='环境名称')
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, verbose_name='作用域')
    variables = models.JSONField(default=dict, verbose_name='环境变量')
    is_active = models.BooleanField(default=False, verbose_name='是否激活')
    project = models.ForeignKey(ApiProject, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='environments', verbose_name='关联项目')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_environments'
        verbose_name = '环境变量'
        verbose_name_plural = '环境变量'

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()})"


class RequestHistory(models.Model):
    """请求历史模型"""
    request = models.ForeignKey(ApiRequest, on_delete=models.CASCADE, related_name='histories', verbose_name='关联请求')
    environment = models.ForeignKey(Environment, on_delete=models.SET_NULL, null=True, blank=True,
                                    verbose_name='使用环境')
    request_data = models.JSONField(verbose_name='请求数据')
    response_data = models.JSONField(null=True, blank=True, verbose_name='响应数据')
    status_code = models.IntegerField(null=True, blank=True, verbose_name='状态码')
    response_time = models.FloatField(null=True, blank=True, verbose_name='响应时间(ms)')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    assertions_results = models.JSONField(null=True, blank=True, verbose_name='断言结果')
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='执行者')
    executed_at = models.DateTimeField(auto_now_add=True, verbose_name='执行时间')

    class Meta:
        db_table = 'api_request_histories'
        verbose_name = '请求历史'
        verbose_name_plural = '请求历史'
        ordering = ['-executed_at']

    def __str__(self):
        return f"{self.request.name} - {self.executed_at}"


class TestSuite(models.Model):
    """测试套件模型（自动化测试）"""
    project = models.ForeignKey(ApiProject, on_delete=models.CASCADE, related_name='test_suites',
                                verbose_name='所属项目')
    name = models.CharField(max_length=200, verbose_name='套件名称')
    description = models.TextField(blank=True, verbose_name='套件描述')
    requests = models.ManyToManyField(ApiRequest, through='TestSuiteRequest', verbose_name='包含请求')
    environment = models.ForeignKey(Environment, on_delete=models.SET_NULL, null=True, blank=True,
                                    verbose_name='执行环境')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_test_suites',
                                   verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_test_suites'
        verbose_name = '测试套件'
        verbose_name_plural = '测试套件'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class TestSuiteRequest(models.Model):
    """测试套件中的请求关联模型"""
    test_suite = models.ForeignKey(TestSuite, on_delete=models.CASCADE, verbose_name='测试套件')
    request = models.ForeignKey(ApiRequest, on_delete=models.CASCADE, verbose_name='API请求')
    order = models.IntegerField(default=0, verbose_name='执行顺序')
    assertions = models.JSONField(default=list, verbose_name='断言规则')
    enabled = models.BooleanField(default=True, verbose_name='是否启用')

    class Meta:
        db_table = 'api_test_suite_requests'
        verbose_name = '套件请求'
        verbose_name_plural = '套件请求'
        unique_together = ['test_suite', 'request']
        ordering = ['order']

    def __str__(self):
        return f"{self.test_suite.name} - {self.request.name}"


class TestExecution(models.Model):
    """测试执行模型"""
    EXECUTION_STATUS_CHOICES = [
        ('PENDING', '待执行'),
        ('RUNNING', '执行中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '执行失败'),
        ('CANCELLED', '已取消'),
    ]

    test_suite = models.ForeignKey(TestSuite, on_delete=models.CASCADE, related_name='executions',
                                   verbose_name='测试套件')
    status = models.CharField(max_length=20, choices=EXECUTION_STATUS_CHOICES, default='PENDING',
                              verbose_name='执行状态')
    start_time = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    total_requests = models.IntegerField(default=0, verbose_name='总请求数')
    passed_requests = models.IntegerField(default=0, verbose_name='通过请求数')
    failed_requests = models.IntegerField(default=0, verbose_name='失败请求数')
    results = models.JSONField(default=dict, verbose_name='执行结果')
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='执行者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'api_test_executions'
        verbose_name = '测试执行'
        verbose_name_plural = '测试执行'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.test_suite.name} - {self.created_at}"


# ================ 通知管理相关模型 ================


class NotificationLog(models.Model):
    """通知日志模型"""
    NOTIFICATION_TYPES = [
        ('task_execution', '定时任务执行'),
        ('test_suite_execution', '测试套件执行'),
        ('api_request_execution', 'API请求执行'),
        ('system_alert', '系统警告'),
        ('manual', '手动通知'),
    ]

    STATUS_CHOICES = [
        ('pending', '待发送'),
        ('sending', '发送中'),
        ('success', '发送成功'),
        ('failed', '发送失败'),
        ('cancelled', '已取消'),
    ]

    task_id = models.IntegerField(null=True, blank=True, verbose_name='关联任务ID')
    task_name = models.CharField(max_length=200, verbose_name='任务名称', help_text='相关任务的名称')
    task_type = models.CharField(max_length=20, blank=True, null=True, verbose_name='任务类型快照', help_text='发送通知时的任务类型')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, verbose_name='通知类型')
    sender_name = models.CharField(max_length=100, verbose_name='发件人姓名')
    sender_email = models.EmailField(verbose_name='发件人邮箱')
    recipient_info = models.JSONField(verbose_name='收件人信息', help_text='接收通知的用户信息')
    webhook_bot_info = models.JSONField(default=dict, blank=True, null=True, verbose_name='Webhook机器人信息')
    notification_content = models.TextField(verbose_name='通知内容', help_text='发送的通知内容')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='发送状态')
    error_message = models.TextField(blank=True, null=True, verbose_name='错误信息', help_text='发送失败时的错误信息')
    response_info = models.JSONField(default=dict, blank=True, null=True, verbose_name='响应信息',
                                     help_text='接收方返回的响应信息')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='发送时间')
    retry_count = models.IntegerField(default=0, verbose_name='重试次数', help_text='已重试的次数')
    is_retried = models.BooleanField(default=False, verbose_name='是否已重试')

    class Meta:
        db_table = 'api_notification_logs'
        verbose_name = '通知日志'
        verbose_name_plural = '通知日志'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.task_name} - {self.get_notification_type_display()} - {self.status}"

    def get_recipient_names(self):
        """获取收件人姓名列表"""
        if self.recipient_info:
            if isinstance(self.recipient_info, list):
                recipient_list = []
                for rec in self.recipient_info:
                    email = rec.get('email', '')
                    name = rec.get('name', '')
                    if name and email:
                        recipient_list.append(f"{name}（{email}）")
                    elif email:
                        recipient_list.append(email)
                    else:
                        recipient_list.append('未知用户')
                return ', '.join(recipient_list)
            elif isinstance(self.recipient_info, dict):
                email = self.recipient_info.get('email', '')
                name = self.recipient_info.get('name', '')
                if name and email:
                    return f"{name}（{email}）"
                elif email:
                    return email
                else:
                    return '未知用户'
        return "未知收件人"

    def get_retry_status(self):
        """获取重试状态"""
        if self.is_retried:
            return f"已重试 {self.retry_count} 次"
        return "未重试"


class OperationLog(models.Model):
    """操作日志模型"""
    OPERATION_TYPE_CHOICES = [
        ('create', '新增'),
        ('edit', '编辑'),
        ('delete', '删除'),
        ('execute', '执行'),
        ('run', '运行'),
        ('save', '保存'),
    ]

    RESOURCE_TYPE_CHOICES = [
        ('project', '项目'),
        ('collection', '集合'),
        ('request', '请求'),
        ('suite', '测试套件'),
        ('environment', '环境'),
        ('task', '定时任务'),
        ('execution', '执行记录'),
    ]

    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPE_CHOICES, verbose_name='操作类型')
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPE_CHOICES, verbose_name='资源类型')
    resource_id = models.IntegerField(verbose_name='资源ID')
    resource_name = models.CharField(max_length=200, verbose_name='资源名称')
    description = models.TextField(verbose_name='操作描述')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='操作用户')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'api_operation_logs'
        verbose_name = 'API操作日志'
        verbose_name_plural = 'API操作日志'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_operation_type_display()} - {self.resource_name}"


class AIServiceConfig(models.Model):
    """AI服务配置模型"""
    SERVICE_TYPE_CHOICES = [
        ('openai', 'OpenAI'),
        ('azure', 'Azure OpenAI'),
        ('anthropic', 'Anthropic'),
        ('deepseek', 'DeepSeek'),
        ('qwen', '通义千问'),
        ('siliconflow', '硅基流动'),
        ('other', '其他'),
    ]

    ROLE_CHOICES = [
        ('doc_extractor', 'API文档提取'),
        ('naming', '参数命名规范化'),
        ('mock_data', '模拟数据生成'),
        ('description', '参数描述补全'),
    ]

    name = models.CharField(max_length=200, verbose_name='配置名称')
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES, verbose_name='服务类型')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name='角色类型')
    api_key = models.CharField(max_length=500, verbose_name='API Key')
    base_url = models.CharField(max_length=500, verbose_name='API Base URL')
    model_name = models.CharField(max_length=200, verbose_name='模型名称')
    max_tokens = models.IntegerField(default=4096, verbose_name='最大Token数')
    temperature = models.FloatField(default=0.7, verbose_name='温度参数')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_ai_service_configs'
        verbose_name = 'AI服务配置'
        verbose_name_plural = 'AI服务配置'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['service_type', 'role']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name
