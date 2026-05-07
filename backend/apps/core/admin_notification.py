"""通知模板 Admin"""
from django.contrib import admin
from .models import NotificationTemplate
from .admin_mixins import StandardAdminMixin


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(StandardAdminMixin, admin.ModelAdmin):
    """通知模板 Admin"""
    
    list_display = ['name', 'template_type_display', 'is_default', 'is_active', 'created_at', 'updated_at']
    list_filter = ['template_type', 'is_default', 'is_active', 'created_at']
    search_fields = ['name', 'description', 'content']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    list_per_page = 50
    
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'template_type', 'subject', 'is_default', 'is_active', 'description', 'created_by')
        }),
        ('模板内容', {
            'fields': ('content',)
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def template_type_display(self, obj):
        """模板类型显示"""
        return obj.get_template_type_display()
    template_type_display.short_description = '模板类型'
    
    def save_model(self, request, obj, form, change):
        """保存时处理默认模板逻辑"""
        if not obj.created_by_id:
            obj.created_by = request.user
        
        if obj.is_default:
            NotificationTemplate.objects.filter(
                template_type=obj.template_type,
                is_default=True
            ).exclude(pk=obj.pk).update(is_default=False)
        super().save_model(request, obj, form, change)
