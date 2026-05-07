"""
调度器URL配置
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ScheduleViewSet, ScheduleConfigViewSet
from .admin import schedule_execute_now

router = DefaultRouter()
router.register(r'schedules', ScheduleViewSet, basename='schedule')
router.register(r'configs', ScheduleConfigViewSet, basename='schedule-config')

urlpatterns = [
    path('', include(router.urls)),
    path('admin/schedule/<int:schedule_id>/execute/', schedule_execute_now, name='admin_schedule_execute_now'),
]
