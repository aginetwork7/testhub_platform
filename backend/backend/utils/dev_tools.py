"""开发工具辅助类"""
import logging
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)


class OptimizedModelAdmin(admin.ModelAdmin):
    """优化的 ModelAdmin 基类"""
    
    list_per_page = 20
    list_max_show_all = 100
    show_full_result_count = False
    
    def get_queryset(self, request):
        """优化查询"""
        qs = super().get_queryset(request)
        if self.list_select_related:
            qs = qs.select_related(*self.list_select_related)
        if self.list_prefetch_related:
            qs = qs.prefetch_related(*self.list_prefetch_related)
        return qs
    
    def colored_status(self, obj, field='status', colors=None):
        """彩色状态显示"""
        if colors is None:
            colors = {
                'active': 'green',
                'inactive': 'red',
                'pending': 'orange',
                'completed': 'blue',
            }
        status_value = getattr(obj, field, '')
        color = colors.get(status_value, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            status_value
        )
    
    def link_to_related(self, obj, related_field, link_text=None):
        """链接到相关对象"""
        related_obj = getattr(obj, related_field)
        if related_obj:
            url = reverse(
                f'admin:{related_obj._meta.app_label}_{related_obj._meta.model_name}_change',
                args=[related_obj.id]
            )
            return format_html('<a href="{}">{}</a>', url, link_text or str(related_obj))
        return '-'


class APIResponseFormatter:
    """API 响应格式化器"""
    
    @staticmethod
    def success(data=None, message='Success', status=200):
        return {
            'success': True,
            'message': message,
            'data': data,
            'status': status
        }
    
    @staticmethod
    def error(message='Error', errors=None, status=400):
        return {
            'success': False,
            'message': message,
            'errors': errors,
            'status': status
        }
    
    @staticmethod
    def paginated(data, page, page_size, total_count):
        return {
            'success': True,
            'data': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size
            }
        }
