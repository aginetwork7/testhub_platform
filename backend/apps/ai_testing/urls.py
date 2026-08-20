from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AiProjectViewSet, AICaseViewSet, AIExecutionExperienceViewSet, AIExecutionRecordViewSet
from .alpha.views import AlphaRunViewSet
from apps.ui_automation.views_config import AIIntelligentModeConfigViewSet, AIModePromptConfigViewSet

router = DefaultRouter()
router.register(r'projects', AiProjectViewSet)
router.register(r'ai-cases', AICaseViewSet)
router.register(r'ai-execution-records', AIExecutionRecordViewSet)
router.register(r'ai-execution-experiences', AIExecutionExperienceViewSet, basename='ai-execution-experience')
router.register(r'alpha/runs', AlphaRunViewSet, basename='alpha-run')
router.register(r'models', AIIntelligentModeConfigViewSet, basename='ai-testing-model-config')
router.register(r'prompts', AIModePromptConfigViewSet, basename='ai-testing-prompt-config')

urlpatterns = [
    path('', include(router.urls)),
]
