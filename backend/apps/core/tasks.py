from django.utils import timezone
from datetime import timedelta
from django_q.tasks import schedule
from apps.core.models import RequestPerformanceLog, PerformanceStatistics
import logging

logger = logging.getLogger(__name__)


def aggregate_daily_performance_stats():
    """
    统计前一天的请求性能数据
    """
    from django.utils import timezone
    from datetime import timedelta
    from apps.core.models import RequestPerformanceLog, PerformanceStatistics
    
    target_date = (timezone.now() - timedelta(days=1)).date()
    
    start_time = timezone.make_aware(
        timezone.datetime.combine(target_date, timezone.datetime.min.time())
    )
    end_time = start_time + timedelta(days=1)
    
    logs = RequestPerformanceLog.objects.filter(
        created_at__gte=start_time,
        created_at__lt=end_time
    )
    
    total_requests = logs.count()
    
    if total_requests == 0:
        logger.info(f'{target_date} 没有请求记录')
        return
    
    avg_response_time = sum(log.response_time for log in logs) / total_requests
    max_response_time = max(log.response_time for log in logs)
    min_response_time = min(log.response_time for log in logs)
    error_count = logs.filter(status_code__gte=400).count()
    slow_requests = logs.filter(response_time__gt=1000).count()
    
    stats, created = PerformanceStatistics.objects.update_or_create(
        date=target_date,
        defaults={
            'total_requests': total_requests,
            'avg_response_time': avg_response_time,
            'max_response_time': max_response_time,
            'min_response_time': min_response_time,
            'error_count': error_count,
            'slow_requests': slow_requests,
        }
    )
    
    action = '创建' if created else '更新'
    logger.info(
        f'{action}性能统计: {target_date} - 总请求: {total_requests}, '
        f'平均响应时间: {avg_response_time:.2f}ms'
    )


def aggregate_current_day_stats():
    """
    统计当天请求的性能数据
    """
    from django.utils import timezone
    from datetime import timedelta
    from apps.core.models import RequestPerformanceLog, PerformanceStatistics
    
    target_date = timezone.now().date()
    
    start_time = timezone.make_aware(
        timezone.datetime.combine(target_date, timezone.datetime.min.time())
    )
    end_time = timezone.now()
    
    logs = RequestPerformanceLog.objects.filter(
        created_at__gte=start_time,
        created_at__lte=end_time
    )
    
    total_requests = logs.count()
    
    if total_requests == 0:
        logger.info(f'{target_date} 今天还没有请求记录')
        return
    
    avg_response_time = sum(log.response_time for log in logs) / total_requests
    max_response_time = max(log.response_time for log in logs)
    min_response_time = min(log.response_time for log in logs)
    error_count = logs.filter(status_code__gte=400).count()
    slow_requests = logs.filter(response_time__gt=1000).count()
    
    stats, created = PerformanceStatistics.objects.update_or_create(
        date=target_date,
        defaults={
            'total_requests': total_requests,
            'avg_response_time': avg_response_time,
            'max_response_time': max_response_time,
            'min_response_time': min_response_time,
            'error_count': error_count,
            'slow_requests': slow_requests,
        }
    )
    
    action = '创建' if created else '更新'
    logger.info(
        f'{action}今日性能统计: {target_date} - 总请求: {total_requests}, '
        f'平均响应时间: {avg_response_time:.2f}ms'
    )
