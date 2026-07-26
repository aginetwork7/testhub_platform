"""
Core 应用路由
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import SystemHealthAPIView, UnifiedNotificationConfigViewSet
from .views_notification import NotificationTemplateViewSet

router = DefaultRouter()
router.register(r'notification-configs', UnifiedNotificationConfigViewSet, basename='unified-notification-config')
router.register(r'notification-templates', NotificationTemplateViewSet, basename='notification-template')

urlpatterns = [
    path('system-health/', SystemHealthAPIView.as_view(), name='system-health'),
    path('', include(router.urls)),
]
