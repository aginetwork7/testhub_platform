from django.contrib import admin
from .models import (
    ApiProject, ApiCollection, ApiRequest, Environment, RequestHistory,
    TestSuite, TestExecution, NotificationLog, AIServiceConfig
)
from apps.core.admin_mixins import StandardAdminMixin


@admin.register(ApiProject)
class ApiProjectAdmin(StandardAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'project_type', 'status', 'owner', 'start_date', 'end_date', 'created_at']
    list_filter = ['project_type', 'status', 'created_at']
    search_fields = ['name', 'description']
    filter_horizontal = ['members']


@admin.register(ApiCollection)
class ApiCollectionAdmin(StandardAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'project', 'parent', 'order', 'created_at']
    list_filter = ['project', 'created_at']
    search_fields = ['name', 'description']


@admin.register(ApiRequest)
class ApiRequestAdmin(StandardAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'method', 'request_type', 'collection', 'created_by', 'created_at']
    list_filter = ['method', 'request_type', 'created_at']
    search_fields = ['name', 'url']


@admin.register(Environment)
class EnvironmentAdmin(StandardAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'scope', 'project', 'is_active', 'created_by', 'created_at']
    list_filter = ['scope', 'is_active', 'created_at']
    search_fields = ['name']


@admin.register(RequestHistory)
class RequestHistoryAdmin(StandardAdminMixin, admin.ModelAdmin):
    list_display = ['request', 'status_code', 'response_time', 'executed_by', 'executed_at']
    list_filter = ['status_code', 'executed_at']
    search_fields = ['request__name']


@admin.register(TestSuite)
class TestSuiteAdmin(StandardAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'project', 'environment', 'created_by', 'created_at']
    list_filter = ['project', 'created_at']
    search_fields = ['name', 'description']


@admin.register(TestExecution)
class TestExecutionAdmin(StandardAdminMixin, admin.ModelAdmin):
    list_display = ['test_suite', 'status', 'total_requests', 'passed_requests', 'failed_requests', 'executed_by', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['test_suite__name']


@admin.register(AIServiceConfig)
class AIServiceConfigAdmin(StandardAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'service_type', 'role', 'model_name', 'is_active', 'created_by', 'created_at']
    list_filter = ['service_type', 'role', 'is_active', 'created_at']
    search_fields = ['name', 'model_name']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_queryset(self, request):
        """根据用户权限过滤配置"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(created_by=request.user)
