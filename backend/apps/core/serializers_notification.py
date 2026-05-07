"""通知模板序列化器"""
from rest_framework import serializers
from apps.core.models import NotificationTemplate


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """通知模板序列化器"""
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)
    
    class Meta:
        model = NotificationTemplate
        fields = [
            'id', 'name', 'template_type', 'template_type_display', 'content', 'variables',
            'is_default', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'template_type_display']
    
    def validate_name(self, value):
        """验证模板名称"""
        template_type = self.initial_data.get('template_type')
        if template_type:
            # 检查同类型模板名称是否重复
            existing = NotificationTemplate.objects.filter(
                name=value,
                template_type=template_type
            )
            if self.instance:
                existing = existing.exclude(id=self.instance.id)
            if existing.exists():
                raise serializers.ValidationError(f'该类型的模板名称 "{value}" 已存在')
        return value
    
    def validate_is_default(self, value):
        """验证默认模板"""
        if value:
            template_type = self.initial_data.get('template_type') or getattr(self.instance, 'template_type', None)
            if template_type:
                # 设置默认模板时，将同类型其他模板设为非默认
                NotificationTemplate.objects.filter(
                    template_type=template_type,
                    is_default=True
                ).update(is_default=False)
        return value
