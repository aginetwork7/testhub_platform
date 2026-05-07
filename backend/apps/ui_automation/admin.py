"""UI自动化测试 Admin配置"""
from django.contrib import admin
from .models import (
    UiProject, LocatorStrategy, ElementGroup, Element,
    TestScript, PageObject, PageObjectElement, ScriptStep,
    ScriptElementUsage, TestSuite, TestSuiteScript, TestSuiteTestCase,
    TestExecution, TestEnvironment, Screenshot,
    TestCase, TestCaseStep, TestCaseExecution,
    OperationRecord, UiNotificationLog
)
from apps.core.admin_mixins import StandardAdminMixin


@admin.register(UiProject)
class UiProjectAdmin(StandardAdminMixin, admin.ModelAdmin):
    """UI自动化项目 Admin"""
    list_display = ['name', 'status', 'base_url', 'owner', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['members']
    # date_hierarchy = 'created_at'


@admin.register(LocatorStrategy)
class LocatorStrategyAdmin(StandardAdminMixin, admin.ModelAdmin):
    """定位策略 Admin"""
    list_display = ['name', 'description']
    search_fields = ['name']


@admin.register(ElementGroup)
class ElementGroupAdmin(StandardAdminMixin, admin.ModelAdmin):
    """元素分组 Admin"""
    list_display = ['name', 'project', 'parent_group', 'order', 'created_at']
    list_filter = ['project', 'created_at']
    search_fields = ['name', 'description']


@admin.register(Element)
class ElementAdmin(StandardAdminMixin, admin.ModelAdmin):
    """UI元素 Admin"""
    list_display = ['name', 'project', 'element_type', 'page', 'locator_strategy', 'validation_status', 'usage_count']
    list_filter = ['project', 'element_type', 'validation_status', 'created_at']
    search_fields = ['name', 'description', 'locator_value']
    readonly_fields = ['usage_count', 'last_validated', 'created_at', 'updated_at']


@admin.register(TestScript)
class TestScriptAdmin(StandardAdminMixin, admin.ModelAdmin):
    """UI测试脚本 Admin"""
    list_display = ['name', 'project', 'script_type', 'language', 'framework', 'created_at']
    list_filter = ['project', 'script_type', 'language', 'framework', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PageObject)
class PageObjectAdmin(StandardAdminMixin, admin.ModelAdmin):
    """页面对象 Admin"""
    list_display = ['name', 'class_name', 'project', 'created_at']
    list_filter = ['project', 'created_at']
    search_fields = ['name', 'class_name', 'description']


@admin.register(PageObjectElement)
class PageObjectElementAdmin(StandardAdminMixin, admin.ModelAdmin):
    """页面对象元素关联 Admin"""
    list_display = ['page_object', 'element', 'method_name', 'is_property', 'order']
    list_filter = ['is_property', 'page_object__project']


@admin.register(ScriptStep)
class ScriptStepAdmin(StandardAdminMixin, admin.ModelAdmin):
    """脚本步骤 Admin"""
    list_display = ['script', 'step_order', 'action_type', 'description', 'target_element']
    list_filter = ['script', 'action_type']


@admin.register(ScriptElementUsage)
class ScriptElementUsageAdmin(StandardAdminMixin, admin.ModelAdmin):
    """脚本元素使用记录 Admin"""
    list_display = ['script', 'element', 'usage_type', 'line_number', 'frequency']
    list_filter = ['usage_type']


@admin.register(TestSuite)
class TestSuiteAdmin(StandardAdminMixin, admin.ModelAdmin):
    """UI测试套件 Admin"""
    list_display = ['name', 'project', 'execution_status', 'passed_count', 'failed_count', 'created_at']
    list_filter = ['project', 'execution_status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(TestSuiteScript)
class TestSuiteScriptAdmin(StandardAdminMixin, admin.ModelAdmin):
    """测试套件脚本关联 Admin"""
    list_display = ['test_suite', 'test_script', 'order']
    list_filter = ['test_suite']


@admin.register(TestSuiteTestCase)
class TestSuiteTestCaseAdmin(StandardAdminMixin, admin.ModelAdmin):
    """测试套件用例关联 Admin"""
    list_display = ['test_suite', 'test_case', 'order']
    list_filter = ['test_suite']


@admin.register(TestExecution)
class TestExecutionAdmin(StandardAdminMixin, admin.ModelAdmin):
    """测试执行记录 Admin"""
    list_display = ['project', 'test_suite', 'status', 'environment', 'started_at', 'duration']
    list_filter = ['project', 'status', 'started_at']
    search_fields = ['project__name', 'test_suite__name']
    readonly_fields = ['started_at', 'finished_at', 'duration', 'created_at']


@admin.register(TestEnvironment)
class TestEnvironmentAdmin(StandardAdminMixin, admin.ModelAdmin):
    """测试环境 Admin"""
    list_display = ['name', 'browser_type', 'os_type', 'created_at']
    list_filter = ['browser_type', 'os_type']
    search_fields = ['name']


@admin.register(Screenshot)
class ScreenshotAdmin(StandardAdminMixin, admin.ModelAdmin):
    """截图 Admin"""
    list_display = ['name', 'execution', 'captured_at']
    list_filter = ['execution', 'captured_at']


@admin.register(TestCase)
class TestCaseAdmin(StandardAdminMixin, admin.ModelAdmin):
    """测试用例 Admin"""
    list_display = ['name', 'project', 'priority', 'status', 'created_at']
    list_filter = ['project', 'priority', 'status', 'created_at']
    search_fields = ['name', 'description']


@admin.register(TestCaseStep)
class TestCaseStepAdmin(StandardAdminMixin, admin.ModelAdmin):
    """测试用例步骤 Admin"""
    list_display = ['test_case', 'step_number', 'action_type', 'description']
    list_filter = ['test_case', 'action_type']


@admin.register(TestCaseExecution)
class TestCaseExecutionAdmin(StandardAdminMixin, admin.ModelAdmin):
    """测试用例执行记录 Admin"""
    list_display = ['test_case', 'project', 'status', 'started_at', 'execution_time']
    list_filter = ['status', 'started_at']


@admin.register(OperationRecord)
class OperationRecordAdmin(StandardAdminMixin, admin.ModelAdmin):
    """操作记录 Admin"""
    list_display = ['operation_type', 'resource_type', 'resource_name', 'user', 'created_at']
    list_filter = ['operation_type', 'resource_type', 'created_at']
    search_fields = ['resource_name', 'detail']


@admin.register(UiNotificationLog)
class UiNotificationLogAdmin(StandardAdminMixin, admin.ModelAdmin):
    """UI通知日志 Admin"""
    list_display = ['sender_name', 'notification_type', 'status', 'created_at', 'sent_at']
    list_filter = ['notification_type', 'status', 'created_at']
    search_fields = ['sender_name', 'sender_email']
    readonly_fields = ['created_at', 'sent_at']
    # date_hierarchy = 'created_at'
