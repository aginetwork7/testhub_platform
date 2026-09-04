"""
Core 应用模型
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from base64 import urlsafe_b64encode
from hashlib import sha256
import json

from cryptography.fernet import Fernet, InvalidToken

User = get_user_model()


class EnvironmentConfiguration(models.Model):
    """Global environment configuration shared by all testing modules."""

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
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='创建人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'environment_configurations'
        ordering = ['-is_default', 'name']
        verbose_name = '全局环境配置'
        verbose_name_plural = '全局环境配置'

    @staticmethod
    def _event_device_key_cipher():
        encryption_key = urlsafe_b64encode(sha256(settings.SECRET_KEY.encode('utf-8')).digest())
        return Fernet(encryption_key)

    def get_event_device_key(self, device):
        if device not in {'main', 'backup'} or not self.event_device_keys_encrypted:
            return ''
        try:
            payload = self._event_device_key_cipher().decrypt(self.event_device_keys_encrypted.encode('utf-8'))
            device_keys = json.loads(payload.decode('utf-8'))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
            return ''
        return str(device_keys.get(device, '')) if isinstance(device_keys, dict) else ''

    def set_event_device_keys(self, main_device_key=None, backup_device_key=None):
        device_keys = {
            'main': self.get_event_device_key('main'),
            'backup': self.get_event_device_key('backup'),
        }
        if main_device_key is not None:
            device_keys['main'] = main_device_key.strip()
        if backup_device_key is not None:
            device_keys['backup'] = backup_device_key.strip()
        self.event_device_keys_encrypted = self._event_device_key_cipher().encrypt(
            json.dumps(device_keys, ensure_ascii=False).encode('utf-8')
        ).decode('utf-8')


class UnifiedNotificationConfig(models.Model):
    """统一通知配置模型 - 每条记录代表一个机器人/通知渠道"""

    CONFIG_TYPE_CHOICES = [
        ('webhook_feishu', '飞书机器人'),
        ('webhook_wechat', '企业微信机器人'),
        ('webhook_dingtalk', '钉钉机器人'),
        ('webhook_generic', '通用Webhook'),
        ('email', '邮件通知'),
    ]

    BUSINESS_TYPE_CHOICES = [
        ('ui_automation', 'UI自动化测试'),
        ('api_testing', '接口测试'),
        ('app_automation', 'APP自动化测试'),
    ]

    name = models.CharField(max_length=100, verbose_name='名称', help_text='用于标识该配置的名称')
    config_type = models.CharField(max_length=20, choices=CONFIG_TYPE_CHOICES, default='webhook_feishu',
                                   verbose_name='配置类型')
    
    webhook_url = models.URLField(max_length=500, blank=True, default='', verbose_name='Webhook URL', 
                                   help_text='机器人Webhook地址（飞书/企微/钉钉/通用Webhook需要）')
    secret = models.CharField(max_length=200, blank=True, default='', verbose_name='签名密钥',
                              help_text='钉钉机器人签名密钥（可选）')
    
    email_recipients = models.JSONField(default=list, blank=True, verbose_name='邮件收件人',
                                        help_text='邮件收件人列表，可包含用户ID或邮箱地址')
    email_attach_report = models.BooleanField(default=False, verbose_name='邮件附带测试报告',
                                              help_text='启用后邮件将附带HTML格式的测试报告附件')
    
    business_types = models.JSONField(default=list, blank=True, verbose_name='业务类型',
                                      help_text='适用的业务类型列表')
    
    enable_ui_automation = models.BooleanField(default=True, verbose_name='启用UI自动化测试通知')
    enable_api_testing = models.BooleanField(default=True, verbose_name='启用接口测试通知')
    enable_app_automation = models.BooleanField(default=True, verbose_name='启用APP自动化测试通知')
    
    notification_template = models.ForeignKey(
        'NotificationTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='通知模板',
        related_name='notification_configs',
        help_text='选择通知模板，用于发送通知时使用'
    )
    
    is_default = models.BooleanField(default=False, verbose_name='是否默认配置')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')

    class Meta:
        db_table = 'unified_notification_configs'
        verbose_name = '通知配置'
        verbose_name_plural = '通知配置'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['config_type']),
            models.Index(fields=['is_default']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f"{self.name} - {self.get_config_type_display()}"

    def get_business_types_display(self):
        """获取业务类型的显示文本"""
        business_type_map = dict(self.BUSINESS_TYPE_CHOICES)
        return [business_type_map.get(bt, bt) for bt in self.business_types]

    def is_enabled_for_business(self, business_type):
        """检查是否启用了指定业务类型的通知"""
        if business_type == 'ui_automation':
            return self.enable_ui_automation
        elif business_type == 'api_testing':
            return self.enable_api_testing
        elif business_type == 'app_automation':
            return self.enable_app_automation
        return False
    
    def get_email_recipients(self):
        """获取邮件收件人列表（解析用户ID和邮箱地址）"""
        import re
        recipients = []
        for item in self.email_recipients:
            if isinstance(item, dict):
                if item.get('type') == 'user':
                    try:
                        user = User.objects.get(id=item.get('id'))
                        if user.email:
                            recipients.append(user.email)
                    except User.DoesNotExist:
                        pass
                elif item.get('type') == 'email':
                    recipients.append(item.get('email', ''))
            elif isinstance(item, str):
                if '@' in item:
                    # 检查是否是 "用户名 (邮箱)" 格式
                    paren_pattern = r'\(([\w\.-]+@[\w\.-]+\.\w+)\)'
                    paren_match = re.search(paren_pattern, item)
                    if paren_match:
                        recipients.append(paren_match.group(1))
                    else:
                        # 直接是邮箱地址
                        recipients.append(item)
        return list(set(filter(None, recipients)))
    
    def get_webhook_bots(self):
        """获取Webhook机器人配置列表"""
        if self.config_type not in ['webhook_wechat', 'webhook_feishu', 'webhook_dingtalk', 'webhook_generic']:
            return []
        
        bot_type_map = {
            'webhook_wechat': 'wechat',
            'webhook_feishu': 'feishu',
            'webhook_dingtalk': 'dingtalk',
            'webhook_generic': 'generic'
        }
        
        return [{
            'name': self.name,
            'type': bot_type_map.get(self.config_type, 'generic'),
            'webhook_url': self.webhook_url,
            'secret': self.secret,
            'enabled': self.is_active,
            'enable_api_testing': self.enable_api_testing,
            'enable_ui_automation': self.enable_ui_automation,
            'enable_app_automation': self.enable_app_automation,
            'notification_template_id': self.notification_template_id if self.notification_template else None
        }]


class RequestPerformanceLog(models.Model):
    """请求性能日志"""
    
    path = models.CharField(max_length=500, verbose_name='请求路径')
    method = models.CharField(max_length=10, verbose_name='请求方法')
    response_time = models.FloatField(verbose_name='响应时间(ms)')
    status_code = models.IntegerField(verbose_name='状态码')
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='用户'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP地址')
    user_agent = models.CharField(max_length=500, blank=True, verbose_name='用户代理')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        db_table = 'request_performance_logs'
        verbose_name = '请求性能日志'
        verbose_name_plural = '请求性能日志'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['path', 'created_at']),
            models.Index(fields=['response_time']),
        ]
    
    def __str__(self):
        return f"{self.method} {self.path} - {self.response_time:.2f}ms"


class PerformanceStatistics(models.Model):
    """性能统计"""
    
    date = models.DateField(unique=True, verbose_name='日期')
    total_requests = models.IntegerField(default=0, verbose_name='总请求数')
    avg_response_time = models.FloatField(default=0, verbose_name='平均响应时间(ms)')
    max_response_time = models.FloatField(default=0, verbose_name='最大响应时间(ms)')
    min_response_time = models.FloatField(default=0, verbose_name='最小响应时间(ms)')
    error_count = models.IntegerField(default=0, verbose_name='错误请求数')
    slow_requests = models.IntegerField(default=0, verbose_name='慢请求数(>1s)')
    
    class Meta:
        db_table = 'performance_statistics'
        verbose_name = '性能统计'
        verbose_name_plural = '性能统计'
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.date} - {self.total_requests} requests"
    
    @property
    def error_rate(self):
        """错误率"""
        if self.total_requests == 0:
            return 0
        return (self.error_count / self.total_requests) * 100
    
    @property
    def slow_rate(self):
        """慢请求率"""
        if self.total_requests == 0:
            return 0
        return (self.slow_requests / self.total_requests) * 100


class NotificationTemplate(models.Model):
    """通知模板模型"""
    
    TEMPLATE_TYPE_CHOICES = [
        ('markdown', 'Markdown'),
        ('html', 'HTML'),
        ('text', '纯文本'),
    ]
    
    name = models.CharField(max_length=100, verbose_name='模板名称')
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPE_CHOICES, default='markdown',
                                     verbose_name='模板类型')
    subject = models.CharField(max_length=200, blank=True, verbose_name='邮件主题',
                               help_text='邮件通知时使用的主题')
    content = models.TextField(verbose_name='模板内容',
                               help_text='支持变量替换，使用{{变量名}}格式')
    variables = models.JSONField(default=list, blank=True, verbose_name='模板变量',
                                 help_text='模板中使用的变量列表')
    description = models.TextField(blank=True, verbose_name='模板描述')
    is_default = models.BooleanField(default=False, verbose_name='是否默认模板')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE,
        verbose_name='创建者',
        null=True, blank=True,
        help_text='系统自动创建的模板无创建者'
    )
    
    class Meta:
        db_table = 'notification_templates'
        verbose_name = '通知模板'
        verbose_name_plural = '通知模板'
        ordering = ['-created_at']
        unique_together = ['name', 'template_type']
    
    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"
    
    def render(self, context):
        """渲染模板"""
        content = self.content
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value) if value is not None else '')
        return content
    
    @classmethod
    def get_default_template(cls, template_type):
        """获取默认模板
        
        Args:
            template_type: 模板类型 ('email', 'webhook', 'markdown', 'html', 'text')
        
        Returns:
            NotificationTemplate: 默认模板实例，如果没有则返回None
        """
        try:
            return cls.objects.filter(
                template_type=template_type,
                is_default=True,
                is_active=True
            ).first()
        except Exception:
            return None
