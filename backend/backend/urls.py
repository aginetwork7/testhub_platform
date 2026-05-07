from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import csrf_exempt
from django.views.static import serve
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from apps.scheduler.admin import schedule_execute_now

urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin/scheduler/schedule/<int:schedule_id>/execute/', schedule_execute_now, name='admin_schedule_execute'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/auth/', include('apps.users.urls')),
    path('api/projects/', include('apps.projects.urls')),
    path('api/testcases/', include('apps.testcases.urls')),
    path('api/testsuites/', include('apps.testsuites.urls')),
    path('api/executions/', include('apps.executions.urls')),
    path('api/reports/', include('apps.reports.urls')),
    path('api/reviews/', include('apps.reviews.urls')),
    path('api/versions/', include('apps.versions.urls')),
    path('api/assistant/', include('apps.assistant.urls')),
    path('api/users/', include('apps.users.urls')),
    path('api/requirement-analysis/', include('apps.requirement_analysis.urls')),
    path('api/ui-automation/', include('apps.ui_automation.urls')),
    path('api/app-automation/', include('apps.app_automation.urls')),
    path('api/ai-testing/', include('apps.ai_testing.urls')),
    path('api/', include('apps.api_testing.urls')),
    path('api/core/', include('apps.core.urls')),
    path('api/scheduler/', include('apps.scheduler.urls')),
    path('api/data-factory/', include('apps.data_factory.urls')),
    path('api/knowledge-base/', include('apps.knowledge_base.urls')),
    path('api/meta-projects/', include('apps.unified_projects.urls')),
]

# 媒体文件服务（不受DEBUG限制）
urlpatterns += [
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_FILES_URL, document_root=settings.STATIC_FILES_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# APP自动化 Template 目录静态访问
import os
urlpatterns += [
    path('app-automation-templates/<path:path>',
         serve,
         {'document_root': os.path.join(settings.BASE_DIR, 'apps', 'app_automation', 'Template')}),
]

# APP自动化 Allure 报告访问 - 使用配置项
urlpatterns += [
    path('app-automation-reports/<path:path>',
         serve,
         {'document_root': os.path.join(settings.MEDIA_ROOT, settings.ALLURE_APP_AUTOMATION, settings.ALLURE_REPORTS_DIR)}),
]

# API测试 Allure 报告访问 - 使用配置项
urlpatterns += [
    path('api-testing-reports/<path:path>',
         serve,
         {'document_root': os.path.join(settings.MEDIA_ROOT, settings.ALLURE_API_TESTING, settings.ALLURE_REPORTS_DIR)}),
]
