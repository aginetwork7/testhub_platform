from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

from .views import (
    UiProjectViewSet,
    LocatorStrategyViewSet,
    ElementGroupViewSet,
    ElementViewSet,
    PageObjectViewSet,
    TestScriptViewSet,
    TestSuiteViewSet,
    TestExecutionViewSet,
    TestCaseViewSet,
    TestCaseStepViewSet,
    TestCaseExecutionViewSet,
    RecordingSessionViewSet,
    OperationRecordViewSet,
    UiNotificationLogViewSet,
    dashboard_stats
)

router = DefaultRouter()
router.register(r'projects', UiProjectViewSet)
router.register(r'locator-strategies', LocatorStrategyViewSet)
router.register(r'element-groups', ElementGroupViewSet)
router.register(r'elements', ElementViewSet)
router.register(r'test-scripts', TestScriptViewSet)
router.register(r'page-objects', PageObjectViewSet)
router.register(r'test-suites', TestSuiteViewSet)
router.register(r'test-executions', TestExecutionViewSet)
router.register(r'test-cases', TestCaseViewSet)
router.register(r'test-case-steps', TestCaseStepViewSet)
router.register(r'test-case-executions', TestCaseExecutionViewSet)
router.register(r'recordings', RecordingSessionViewSet)
router.register(r'ui-notification-logs', UiNotificationLogViewSet)
router.register(r'operation-records', OperationRecordViewSet)

urlpatterns = [
    path('dashboard/stats/', dashboard_stats, name='ui-dashboard-stats'),
    path('', include(router.urls)),
]

# 添加媒体文件路由
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)