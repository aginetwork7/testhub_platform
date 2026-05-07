"""
Core 应用序列化器
"""
from rest_framework import serializers
from .models import UnifiedNotificationConfig, NotificationTemplate


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """通知模板序列化器"""
    
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = NotificationTemplate
        fields = [
            'id', 'name', 'template_type', 'template_type_display',
            'subject', 'content', 'description',
            'is_default', 'is_active', 'created_at', 'updated_at',
            'created_by', 'created_by_name'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']


class UnifiedNotificationConfigSerializer(serializers.ModelSerializer):
    """统一通知配置序列化器"""
    
    config_type_display = serializers.CharField(source='get_config_type_display', read_only=True)
    notification_template_name = serializers.CharField(source='notification_template.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = UnifiedNotificationConfig
        fields = [
            'id', 'name', 'config_type', 'config_type_display',
            'webhook_url', 'secret', 'email_recipients', 'email_attach_report',
            'business_types',
            'enable_ui_automation', 'enable_api_testing', 'enable_app_automation',
            'notification_template', 'notification_template_name',
            'is_default', 'is_active', 'created_at', 'updated_at',
            'created_by', 'created_by_name'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']
    
    def validate_webhook_url(self, value):
        """验证webhook URL"""
        config_type = self.initial_data.get('config_type')
        if config_type in ['webhook_feishu', 'webhook_wechat', 'webhook_dingtalk', 'webhook_generic']:
            if not value:
                raise serializers.ValidationError('Webhook URL不能为空')
        return value
    
    def validate_email_recipients(self, value):
        """验证邮件收件人"""
        if not isinstance(value, list):
            raise serializers.ValidationError('邮件收件人必须是列表格式')
        
        for item in value:
            if isinstance(item, dict):
                if item.get('type') not in ['user', 'email']:
                    raise serializers.ValidationError('收件人类型必须是 user 或 email')
                if item.get('type') == 'email' and '@' not in item.get('email', ''):
                    raise serializers.ValidationError('邮箱地址格式不正确')
            elif isinstance(item, str):
                if '@' not in item:
                    raise serializers.ValidationError(f'邮箱地址格式不正确: {item}')
            else:
                raise serializers.ValidationError('收件人格式不正确')
        return value
    
    def validate(self, data):
        """验证数据"""
        config_type = data.get('config_type')
        webhook_url = data.get('webhook_url', '')
        email_recipients = data.get('email_recipients', [])
        notification_template = data.get('notification_template')
        
        if config_type == 'email':
            if not email_recipients:
                raise serializers.ValidationError({'email_recipients': '邮件通知必须配置收件人'})
        elif config_type in ['webhook_feishu', 'webhook_wechat', 'webhook_dingtalk', 'webhook_generic']:
            if not webhook_url:
                raise serializers.ValidationError({'webhook_url': 'Webhook URL不能为空'})
        
        # 所有平台类型都需要消息模板
        if not notification_template:
            raise serializers.ValidationError({'notification_template': '请前往后端先创建消息通知模板'})
        
        return data
