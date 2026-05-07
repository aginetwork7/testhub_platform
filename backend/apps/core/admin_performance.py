"""性能监控 Admin"""
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Avg, Max, Min, Count
from django.utils import timezone
from datetime import timedelta
from .models import RequestPerformanceLog, PerformanceStatistics
from .admin_mixins import StandardAdminMixin


@admin.register(RequestPerformanceLog)
class RequestPerformanceLogAdmin(StandardAdminMixin, admin.ModelAdmin):
    """请求性能日志 Admin"""
    
    list_display = ['path', 'method', 'response_time_display', 'status_code_display', 'user_display', 'created_at']
    list_filter = ['method', 'status_code', 'created_at']
    search_fields = ['path', 'user__username']
    readonly_fields = ['path', 'method', 'response_time', 'status_code', 'ip_address', 'user_agent', 'created_at']
    # date_hierarchy = 'created_at'
    list_per_page = 50
    
    def user_display(self, obj):
        """用户显示"""
        return obj.user.username if obj.user else '-'
    user_display.short_description = '用户'
    
    def response_time_display(self, obj):
        """响应时间显示"""
        if obj.response_time > 1000:
            color = 'red'
        elif obj.response_time > 500:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}ms</span>',
            color, f'{obj.response_time:.2f}'
        )
    response_time_display.short_description = '响应时间'
    
    def status_code_display(self, obj):
        """状态码显示"""
        if obj.status_code >= 500:
            color = 'red'
        elif obj.status_code >= 400:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.status_code
        )
    status_code_display.short_description = '状态码'
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(PerformanceStatistics)
class PerformanceStatisticsAdmin(admin.ModelAdmin):
    """性能统计 Admin"""
    
    list_display = ['date', 'total_requests', 'avg_response_time_display', 'error_rate_display', 'slow_rate_display']
    readonly_fields = ['date', 'total_requests', 'avg_response_time', 'max_response_time', 'min_response_time', 
                       'error_count', 'slow_requests', 'error_rate_display', 'slow_rate_display']
    list_per_page = 30
    
    def avg_response_time_display(self, obj):
        """平均响应时间显示"""
        if obj.avg_response_time > 500:
            color = 'red'
        elif obj.avg_response_time > 200:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}ms</span>',
            color, f'{obj.avg_response_time:.2f}'
        )
    avg_response_time_display.short_description = '平均响应时间'
    
    def error_rate_display(self, obj):
        """错误率显示"""
        rate = obj.error_rate
        if rate > 5:
            color = 'red'
        elif rate > 1:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span>',
            color, f'{rate:.2f}'
        )
    error_rate_display.short_description = '错误率'
    
    def slow_rate_display(self, obj):
        """慢请求率显示"""
        rate = obj.slow_rate
        if rate > 10:
            color = 'red'
        elif rate > 5:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span>',
            color, f'{rate:.2f}'
        )
    slow_rate_display.short_description = '慢请求率'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def changelist_view(self, request, extra_context=None):
        """添加统计概览"""
        extra_context = extra_context or {}
        
        today = timezone.now().date()
        last_7_days = today - timedelta(days=7)
        
        stats = PerformanceStatistics.objects.filter(
            date__gte=last_7_days
        ).aggregate(
            total_requests=Count('total_requests'),
            avg_response=Avg('avg_response_time'),
            total_errors=Count('error_count'),
            total_slow=Count('slow_requests')
        )
        
        extra_context['stats_overview'] = {
            'total_requests': stats['total_requests'] or 0,
            'avg_response': stats['avg_response'] or 0,
            'total_errors': stats['total_errors'] or 0,
            'total_slow': stats['total_slow'] or 0,
        }
        
        return super().changelist_view(request, extra_context)
