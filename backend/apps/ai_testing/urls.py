from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AiProjectViewSet, AICaseViewSet, AIExecutionExperienceViewSet, AIExecutionRecordViewSet

router = DefaultRouter()
router.register(r'projects', AiProjectViewSet)
router.register(r'ai-cases', AICaseViewSet)
router.register(r'ai-execution-records', AIExecutionRecordViewSet)
router.register(r'ai-execution-experiences', AIExecutionExperienceViewSet, basename='ai-execution-experience')

urlpatterns = [
    path('', include(router.urls)),
]
