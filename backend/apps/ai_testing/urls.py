from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AiProjectViewSet, AICaseViewSet, AIExecutionExperienceViewSet, AIExecutionRecordViewSet
from .alpha.views import AlphaRunViewSet

router = DefaultRouter()
router.register(r'projects', AiProjectViewSet)
router.register(r'ai-cases', AICaseViewSet)
router.register(r'ai-execution-records', AIExecutionRecordViewSet)
router.register(r'ai-execution-experiences', AIExecutionExperienceViewSet, basename='ai-execution-experience')
router.register(r'alpha/runs', AlphaRunViewSet, basename='alpha-run')

urlpatterns = [
    path('', include(router.urls)),
]
