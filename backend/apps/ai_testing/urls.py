from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AiProjectViewSet, AICaseViewSet, AIExecutionRecordViewSet

router = DefaultRouter()
router.register(r'projects', AiProjectViewSet)
router.register(r'ai-cases', AICaseViewSet)
router.register(r'ai-execution-records', AIExecutionRecordViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
