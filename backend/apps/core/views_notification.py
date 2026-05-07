"""通知模板视图集"""
from rest_framework import viewsets, permissions
from apps.core.models import NotificationTemplate
from apps.core.serializers_notification import NotificationTemplateSerializer


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    """通知模板视图集"""
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['template_type', 'is_default']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """获取查询集"""
        queryset = super().get_queryset()
        # 可以根据用户权限过滤
        return queryset
    
    def perform_create(self, serializer):
        """创建模板"""
        serializer.save()
    
    def perform_update(self, serializer):
        """更新模板"""
        serializer.save()
    
    def perform_destroy(self, instance):
        """删除模板"""
        # 防止删除默认模板
        if instance.is_default:
            from rest_framework.exceptions import ValidationError
            raise ValidationError('默认模板不能删除')
        instance.delete()
