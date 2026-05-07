"""
调度器序列化器
"""
from rest_framework import serializers
from django_q.models import Schedule
from .models import ScheduleConfig
from apps.core.models import NotificationTemplate, UnifiedNotificationConfig


class ScheduleConfigSerializer(serializers.ModelSerializer):
    """任务配置序列化器"""
    module_display = serializers.CharField(source='get_module_display', read_only=True)
    task_type_display = serializers.CharField(source='get_task_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    schedule_name = serializers.CharField(source='schedule.name', read_only=True)
    success_count = serializers.IntegerField(read_only=True)
    failure_count = serializers.IntegerField(read_only=True)
    notification_template_name = serializers.SerializerMethodField()
    notification_config_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=UnifiedNotificationConfig.objects.all(),
        required=False,
        source='notification_configs'
    )
    
    class Meta:
        model = ScheduleConfig
        fields = [
            'id', 'schedule', 'module', 'task_type', 'project_id', 'target_id', 
            'environment_id', 'task_config', 'status', 'description',
            'notify_on_success', 'notify_on_failure', 'notify_on_email', 'notify_on_webhook',
            'notify_emails', 'use_webhook', 'webhook_url', 'notification_template',
            'created_by', 'created_at', 'updated_at', 'last_run_time',
            'success_count', 'failure_count',
            'module_display', 'task_type_display', 'status_display', 'created_by_name',
            'schedule_name', 'notification_template_name', 'notification_config_ids'
        ]
        read_only_fields = ('created_at', 'updated_at')
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if 'notification_config_ids' in data:
            data['notification_config_ids'] = [obj.id for obj in instance.notification_configs.all()]
        return data
    
    def get_notification_template_name(self, obj):
        """获取通知模板名称"""
        if hasattr(obj, 'notification_template') and obj.notification_template:
            return obj.notification_template.name
        return None


class ScheduleSerializer(serializers.ModelSerializer):
    """Django-Q Schedule 序列化器"""
    config = ScheduleConfigSerializer(read_only=True)
    schedule_type_display = serializers.SerializerMethodField()
    next_run_display = serializers.SerializerMethodField()
    last_run_display = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    notification_type_display = serializers.SerializerMethodField()
    notification_config_name = serializers.SerializerMethodField()
    notify_on_email = serializers.SerializerMethodField()
    notify_on_webhook = serializers.SerializerMethodField()
    module = serializers.SerializerMethodField()
    task_type = serializers.SerializerMethodField()
    target_name = serializers.SerializerMethodField()
    engine = serializers.SerializerMethodField()
    browser = serializers.SerializerMethodField()
    device_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Schedule
        fields = [
            'id', 'name', 'func', 'hook', 'args', 'kwargs',
            'schedule_type', 'schedule_type_display', 'minutes', 'cron',
            'repeats', 'next_run', 'next_run_display', 'last_run_display', 
            'cluster', 'task', 'config', 'status_display', 
            'notification_type_display', 'notification_config_name', 'notify_on_email', 'notify_on_webhook',
            'module', 'task_type', 'target_name',
            'engine', 'browser', 'device_name'
        ]
        read_only_fields = ('id', 'task')
    
    def get_schedule_type_display(self, obj):
        type_map = {
            'O': '单次',
            'I': '分钟间隔',
            'H': '每小时',
            'D': '每天',
            'W': '每周',
            'BW': '双周',
            'M': '每月',
            'BM': '双月',
            'Q': '每季度',
            'Y': '每年',
            'C': 'Cron',
        }
        return type_map.get(obj.schedule_type, obj.schedule_type)
    
    def get_next_run_display(self, obj):
        if obj.next_run:
            from django.utils import timezone
            return timezone.localtime(obj.next_run).strftime('%Y-%m-%d %H:%M:%S')
        return None
    
    def get_status_display(self, obj):
        if hasattr(obj, 'config') and obj.config:
            return obj.config.get_status_display()
        return '-'
    
    def get_notification_type_display(self, obj):
        if hasattr(obj, 'config') and obj.config:
            config = obj.config
            notification_types = []
            if getattr(config, 'notify_on_email', False):
                notification_types.append('邮箱通知')
            if getattr(config, 'notify_on_webhook', False):
                notification_types.append('Webhook')
            if notification_types:
                return ' + '.join(notification_types)
        return '未配置'
    
    def get_notify_on_email(self, obj):
        """获取是否启用邮箱通知"""
        if hasattr(obj, 'config') and obj.config:
            return getattr(obj.config, 'notify_on_email', False)
        return False
    
    def get_notify_on_webhook(self, obj):
        """获取是否启用Webhook通知"""
        if hasattr(obj, 'config') and obj.config:
            return getattr(obj.config, 'notify_on_webhook', False)
        return False
    
    def get_notification_config_name(self, obj):
        if hasattr(obj, 'config') and obj.config:
            config = obj.config
            try:
                if hasattr(config, 'notification_configs') and config.notification_configs.exists():
                    return ', '.join([nc.name for nc in config.notification_configs.all()])
            except Exception as e:
                pass
        return None
    
    def get_last_run_display(self, obj):
        """获取上次执行时间"""
        if hasattr(obj, 'config') and obj.config:
            from django_q.models import Success
            try:
                last_run = Success.objects.filter(
                    name=obj.name,
                    func=obj.func
                ).order_by('-stopped').first()
                if last_run and last_run.stopped:
                    from django.utils import timezone
                    return timezone.localtime(last_run.stopped).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
        return '-'
    
    def get_module(self, obj):
        """获取模块"""
        if hasattr(obj, 'config') and obj.config:
            return obj.config.get_module_display()
        return '-'
    
    def get_task_type(self, obj):
        """获取任务类型"""
        if hasattr(obj, 'config') and obj.config:
            return obj.config.get_task_type_display()
        return '-'
    
    def get_target_name(self, obj):
        """获取目标名称（测试套件/用例名称）"""
        if hasattr(obj, 'config') and obj.config:
            config = obj.config
            task_config = config.task_config or {}
            
            if config.task_type == 'UI_TEST_SUITE':
                from apps.ui_automation.models import TestSuite
                try:
                    suite = TestSuite.objects.get(id=config.target_id)
                    return suite.name
                except TestSuite.DoesNotExist:
                    return '-'
            elif config.task_type == 'UI_TEST_CASE':
                from apps.ui_automation.models import TestCase
                try:
                    test_case = TestCase.objects.get(id=config.target_id)
                    return test_case.name
                except TestCase.DoesNotExist:
                    return '-'
            elif config.task_type == 'APP_TEST_SUITE':
                from apps.app_automation.models import AppTestSuite
                try:
                    suite = AppTestSuite.objects.get(id=config.target_id)
                    return suite.name
                except AppTestSuite.DoesNotExist:
                    return '-'
            elif config.task_type == 'APP_TEST_CASE':
                from apps.app_automation.models import AppTestCase
                try:
                    test_case = AppTestCase.objects.get(id=config.target_id)
                    return test_case.name
                except AppTestCase.DoesNotExist:
                    return '-'
            elif config.task_type == 'API_TEST_SUITE':
                from apps.api_testing.models import TestSuite as ApiTestSuite
                try:
                    suite = ApiTestSuite.objects.get(id=config.target_id)
                    return suite.name
                except ApiTestSuite.DoesNotExist:
                    return '-'
            elif config.task_type == 'API_REQUEST':
                return task_config.get('request_name', '-')
        return '-'
    
    def get_engine(self, obj):
        """获取执行引擎"""
        if hasattr(obj, 'config') and obj.config:
            config = obj.config
            task_config = config.task_config or {}
            return task_config.get('engine', 'playwright')
        return 'playwright'
    
    def get_browser(self, obj):
        """获取浏览器"""
        if hasattr(obj, 'config') and obj.config:
            config = obj.config
            task_config = config.task_config or {}
            return task_config.get('browser', 'chrome')
        return 'chrome'
    
    def get_device_name(self, obj):
        """获取设备名称"""
        if hasattr(obj, 'config') and obj.config:
            config = obj.config
            task_config = config.task_config or {}
            device_id = task_config.get('device_id')
            if device_id:
                try:
                    from apps.app_automation.models import AppDevice
                    device = AppDevice.objects.get(id=device_id)
                    return device.name
                except AppDevice.DoesNotExist:
                    return '-'
            return '-'
        return '-'


class ScheduleCreateSerializer(serializers.Serializer):
    """创建定时任务序列化器"""
    name = serializers.CharField(max_length=100)
    module = serializers.ChoiceField(choices=['API', 'UI', 'APP'])
    task_type = serializers.ChoiceField(choices=[
        'API_TEST_SUITE', 'API_REQUEST',
        'UI_TEST_SUITE', 'UI_TEST_CASE',
        'APP_TEST_SUITE', 'APP_TEST_CASE',
    ])
    schedule_type = serializers.ChoiceField(choices=[
        'O', 'I', 'H', 'D', 'W', 'BW', 'M', 'BM', 'Q', 'Y', 'C'
    ])
    
    target_id = serializers.IntegerField(required=False, allow_null=True)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    environment_id = serializers.IntegerField(required=False, allow_null=True)
    task_config = serializers.DictField(required=False, default=dict)
    
    cron = serializers.CharField(max_length=100, required=False, allow_blank=True)
    minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    next_run = serializers.DateTimeField(required=False, allow_null=True)
    repeats = serializers.IntegerField(default=-1)
    
    description = serializers.CharField(required=False, allow_blank=True, default='')
    
    notify_on_success = serializers.BooleanField(default=False, help_text='成功时通知')
    notify_on_failure = serializers.BooleanField(default=True, help_text='失败时通知')
    notify_on_email = serializers.BooleanField(default=False, help_text='邮箱通知')
    notify_on_webhook = serializers.BooleanField(default=False, help_text='Webhook机器人通知')
    
    notification_config_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text='统一通知配置ID列表'
    )
    notification_template_id = serializers.IntegerField(required=False, allow_null=True)
    
    def validate(self, data):
        schedule_type = data.get('schedule_type')
        
        if schedule_type == 'C' and not data.get('cron'):
            raise serializers.ValidationError({'cron': 'Cron类型必须提供cron表达式'})
        
        if schedule_type == 'I' and not data.get('minutes'):
            raise serializers.ValidationError({'minutes': '分钟间隔类型必须提供分钟数'})
        
        return data


class ScheduleExecuteSerializer(serializers.Serializer):
    """立即执行任务序列化器"""
    pass


class ScheduleToggleSerializer(serializers.Serializer):
    """暂停/恢复任务序列化器"""
    action = serializers.ChoiceField(choices=['pause', 'resume'])
