"""异步中间件"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

logger = logging.getLogger(__name__)


class AsyncRequestTimingMiddleware(MiddlewareMixin):
    """请求计时中间件"""
    
    SLOW_REQUEST_THRESHOLD = 1000
    
    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        end_time = time.time()
        response_time = (end_time - start_time) * 1000
        
        response['X-Response-Time'] = f'{response_time:.2f}ms'
        
        self._save_performance_log(request, response, response_time)
        
        return response
    
    def _save_performance_log(self, request, response, response_time):
        """保存性能日志到数据库"""
        try:
            if request.path.startswith('/admin/') or request.path.startswith('/static/'):
                return
            
            if request.path.startswith('/api/') or request.path.startswith('/ws/'):
                from apps.core.models import RequestPerformanceLog
                
                user = None
                if hasattr(request, 'user') and request.user.is_authenticated:
                    user = request.user
                
                ip_address = self._get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
                
                RequestPerformanceLog.objects.create(
                    path=request.path[:500],
                    method=request.method,
                    response_time=response_time,
                    status_code=response.status_code,
                    user=user,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                
                if response_time > self.SLOW_REQUEST_THRESHOLD:
                    logger.warning(
                        f"慢请求: {request.method} {request.path} - {response_time:.2f}ms"
                    )
        except Exception as e:
            logger.error(f"保存性能日志失败: {e}")
    
    def _get_client_ip(self, request):
        """获取客户端IP地址"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
