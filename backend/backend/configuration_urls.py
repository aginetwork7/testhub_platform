from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api_automation.views import ApiAutomationConfigurationViewSet
from apps.assistant.views_config import AgentModelConfigViewSet, AgentPromptConfigViewSet
from apps.app_automation.views.config_views import AppConfigViewSet
from apps.ui_automation.views_config import AIIntelligentModeConfigViewSet, AIModePromptConfigViewSet, EnvironmentConfigViewSet


router = DefaultRouter()
router.register(r'env', ApiAutomationConfigurationViewSet, basename='environment-config')
router.register(r'ai-test/models', AIIntelligentModeConfigViewSet, basename='ai-test-model-config')
router.register(r'ai-test/prompts', AIModePromptConfigViewSet, basename='ai-test-prompt-config')
router.register(r'ai-agent/models', AgentModelConfigViewSet, basename='ai-agent-model-config')
router.register(r'ai-agent/prompts', AgentPromptConfigViewSet, basename='ai-agent-prompt-config')


urlpatterns = [
    path('ui-setting/check/', EnvironmentConfigViewSet.as_view({'get': 'check_environment'}), name='ui-setting-check'),
    path('ui-setting/install_driver/', EnvironmentConfigViewSet.as_view({'post': 'install_driver'}), name='ui-setting-install-driver'),
    path('app-setting/check/', AppConfigViewSet.as_view({'get': 'current'}), name='app-setting-check'),
    path('app-setting/save/', AppConfigViewSet.as_view({'post': 'save'}), name='app-setting-save'),
    path('', include(router.urls)),
]