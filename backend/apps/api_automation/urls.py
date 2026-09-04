from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ApiAutomationCaseViewSet,
    ApiAutomationCoverageViewSet,
    ApiAutomationEndpointViewSet,
    ApiAutomationNotificationLogViewSet,
    ApiAutomationProjectViewSet,
    ApiAutomationRunViewSet,
    ApiAutomationSuiteViewSet,
)


router = DefaultRouter()
router.register(r'projects', ApiAutomationProjectViewSet, basename='api-automation-project')
router.register(r'suites', ApiAutomationSuiteViewSet, basename='api-automation-suite')
router.register(r'cases', ApiAutomationCaseViewSet, basename='api-automation-case')
router.register(r'endpoints', ApiAutomationEndpointViewSet, basename='api-automation-endpoint')
router.register(r'notification-logs', ApiAutomationNotificationLogViewSet, basename='api-automation-notification-log')
router.register(r'coverage', ApiAutomationCoverageViewSet, basename='api-automation-coverage')
router.register(r'runs', ApiAutomationRunViewSet, basename='api-automation-run')

urlpatterns = [
    path('', include(router.urls)),
]