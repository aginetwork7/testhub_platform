# -*- coding: utf-8 -*-
"""APP自动化定时任务视图"""
import logging

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .test_case_views import AppPagination
from ..models import AppNotificationLog
from ..serializers import AppNotificationLogSerializer

logger = logging.getLogger(__name__)


class AppNotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """APP通知日志视图集（只读）"""
    queryset = AppNotificationLog.objects.all()
    serializer_class = AppNotificationLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'notification_type']
    search_fields = ['task_name', 'notification_content']
    ordering_fields = ['created_at', 'sent_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        log = self.get_object()
        if log.status == 'failed':
            log.retry_count += 1
            log.is_retried = True
            log.save(update_fields=['retry_count', 'is_retried'])
            return Response({'success': True, 'message': '通知已加入重试队列'})
        return Response({'success': False, 'message': '只能重试失败的通知'},
                        status=status.HTTP_400_BAD_REQUEST)
