from django.contrib import admin
from django.http import HttpResponse
from .models import TestReport, ReportTemplate
from apps.core.admin_mixins import StandardAdminMixin


@admin.register(TestReport)
class TestReportAdmin(StandardAdminMixin, admin.ModelAdmin):
    """测试报告 Admin"""
    
    list_display = [
        'name', 'report_type_display', 'status_display', 'project',
        'total_cases', 'passed_cases', 'failed_cases', 
        'pass_rate_display', 'duration_display', 'created_at'
    ]
    list_filter = ['report_type', 'status', 'created_at']
    search_fields = ['name', 'project__name']
    readonly_fields = [
        'pass_rate_display', 'duration_display', 'created_at', 'updated_at',
        'started_at', 'finished_at'
    ]
    list_per_page = 50
    
    fieldsets = (
        ('基本信息', {
            'fields': (
                'name', 'project', 'report_type', 'status',
                'execution', 'generated_by'
            )
        }),
        ('测试统计', {
            'fields': (
                'total_cases', 'passed_cases', 'failed_cases',
                'skipped_cases', 'error_cases',
                'pass_rate_display', 'duration_display'
            )
        }),
        ('报告链接', {
            'fields': ('allure_report_url',)
        }),
        ('报告数据', {
            'fields': ('summary', 'content', 'environment_info'),
            'classes': ('collapse',)
        }),
        ('HTML报告', {
            'fields': ('html_content',),
            'classes': ('collapse',)
        }),
        ('时间信息', {
            'fields': ('started_at', 'finished_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def report_type_display(self, obj):
        """报告类型显示"""
        return obj.get_report_type_display()
    report_type_display.short_description = '报告类型'
    
    def status_display(self, obj):
        """状态显示"""
        status_colors = {
            'running': 'blue',
            'completed': 'green',
            'failed': 'red'
        }
        from django.utils.html import format_html
        return format_html(
            '<span style="color: {};">{}</span>',
            status_colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_display.short_description = '状态'
    
    def pass_rate_display(self, obj):
        """通过率显示"""
        rate = obj.pass_rate
        if rate >= 80:
            color = 'green'
        elif rate >= 60:
            color = 'orange'
        else:
            color = 'red'
        from django.utils.html import format_html
        rate_str = f'{rate:.1f}%'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, rate_str
        )
    pass_rate_display.short_description = '通过率'
    
    def duration_display(self, obj):
        """执行时长显示"""
        seconds = obj.duration
        if seconds < 60:
            return f'{seconds:.2f}秒'
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f'{minutes}分{secs}秒'
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f'{hours}小时{minutes}分'
    duration_display.short_description = '执行时长'
    
    actions = ['generate_html_reports', 'download_html_report']
    
    def generate_html_reports(self, request, queryset):
        """批量生成HTML报告"""
        count = 0
        for report in queryset:
            report.generate_html_report()
            report.save()
            count += 1
        self.message_user(request, f'成功生成 {count} 个HTML报告')
    generate_html_reports.short_description = '生成HTML报告'
    
    def download_html_report(self, request, queryset):
        """下载HTML报告"""
        if queryset.count() != 1:
            self.message_user(request, '请选择一个报告进行下载')
            return
        
        report = queryset.first()
        if not report.html_content:
            self.message_user(request, '该报告尚未生成HTML内容，请先生成HTML报告')
            return
        
        response = HttpResponse(report.html_content, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="{report.name}.html"'
        return response
    download_html_report.short_description = '下载HTML报告'


@admin.register(ReportTemplate)
class ReportTemplateAdmin(StandardAdminMixin, admin.ModelAdmin):
    """报告模板 Admin"""
    
    list_display = ['name', 'is_default', 'created_by', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'created_by']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'description', 'is_default', 'created_by')
        }),
        ('模板配置', {
            'fields': ('template_config',)
        }),
        ('时间信息', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
