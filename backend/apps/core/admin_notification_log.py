"""通知日志 Admin"""
from django.contrib import admin
from django.utils.html import format_html
from apps.api_testing.models import NotificationLog as ApiNotificationLog
from apps.app_automation.models import AppNotificationLog
from .admin_mixins import StandardAdminMixin


@admin.register(ApiNotificationLog)
class ApiNotificationLogAdmin(StandardAdminMixin, admin.ModelAdmin):
    """API测试通知日志 Admin"""
    
    list_display = ['task_name', 'notification_type_display', 'status_display', 'sender_email', 'created_at', 'sent_at']
    list_filter = ['notification_type', 'status', 'created_at']
    search_fields = ['task_name', 'sender_email', 'notification_content']
    readonly_fields = ['task_id', 'task_name', 'task_type', 'notification_type', 'sender_name', 'sender_email',
                       'recipient_info', 'webhook_bot_info', 'notification_content', 'status', 'error_message',
                       'response_info', 'created_at', 'sent_at', 'retry_count', 'is_retried']
    date_hierarchy = 'created_at'
    list_per_page = 50
    
    fieldsets = (
        ('基本信息', {
            'fields': ('task_id', 'task_name', 'task_type', 'notification_type')
        }),
        ('发送信息', {
            'fields': ('sender_name', 'sender_email', 'recipient_info', 'webhook_bot_info')
        }),
        ('通知内容', {
            'fields': ('notification_content',)
        }),
        ('状态信息', {
            'fields': ('status', 'error_message', 'response_info', 'sent_at', 'retry_count', 'is_retried')
        }),
        ('时间信息', {
            'fields': ('created_at',)
        }),
    )
    
    def notification_type_display(self, obj):
        """通知类型显示"""
        return obj.get_notification_type_display()
    notification_type_display.short_description = '通知类型'
    
    def status_display(self, obj):
        """状态显示"""
        colors = {
            'pending': 'gray',
            'sending': 'blue',
            'success': 'green',
            'failed': 'red',
            'cancelled': 'orange'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = '状态'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AppNotificationLog)
class AppNotificationLogAdmin(StandardAdminMixin, admin.ModelAdmin):
    """APP自动化通知日志 Admin"""
    
    list_display = ['task_name', 'notification_type_display', 'status_display', 'sender_email', 'created_at', 'sent_at']
    list_filter = ['notification_type', 'status', 'created_at']
    search_fields = ['task_name', 'sender_email', 'notification_content']
    readonly_fields = ['task_id', 'task_name', 'task_type', 'notification_type', 'sender_name', 'sender_email',
                       'recipient_info', 'webhook_bot_info', 'notification_content', 'status', 'error_message',
                       'response_info', 'created_at', 'sent_at', 'retry_count', 'is_retried']
    date_hierarchy = 'created_at'
    list_per_page = 50
    
    def notification_type_display(self, obj):
        """通知类型显示"""
        return obj.get_notification_type_display()
    notification_type_display.short_description = '通知类型'
    
    def status_display(self, obj):
        """状态显示"""
        colors = {
            'pending': 'gray',
            'sending': 'blue',
            'success': 'green',
            'failed': 'red',
            'cancelled': 'orange'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = '状态'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
