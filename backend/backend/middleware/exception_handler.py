"""自定义异常处理"""
from django.http import JsonResponse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class TooManyFieldsExceptionHandler:
    """字段数过多异常处理器"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # 检查响应是否为错误响应且包含TooManyFieldsSent信息
        if response.status_code == 400 and hasattr(response, 'content'):
            content = response.content.decode('utf-8') if isinstance(response.content, bytes) else response.content
            
            if 'TooManyFieldsSent' in content or 'The number of GET/POST parameters exceeded' in content:
                # 返回友好的错误提示
                max_fields = getattr(settings, 'DATA_UPLOAD_MAX_NUMBER_FIELDS', 10000)
                error_message = f'最大删除条数不能超过{max_fields}条，请减少选择数量后重试。'
                
                logger.warning(f"检测到字段数过多异常: {error_message}")
                
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'error_type': 'TooManyFieldsSent'
                }, status=400)
        
        return response
