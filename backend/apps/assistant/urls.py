from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .direct_views import AssistantSessionViewSet, ChatViewSet, assistant_view
from .views_config import AgentModelConfigViewSet

router = DefaultRouter()
router.register(r'sessions', AssistantSessionViewSet, basename='assistant-sessions')
router.register(r'chat', ChatViewSet, basename='chat')
router.register(r'config/agent-models', AgentModelConfigViewSet, basename='agent-model-config')

urlpatterns = [
    path('', include(router.urls)),
    path('view/', assistant_view, name='assistant-view'),
]