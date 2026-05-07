"""异步视图工具"""
import asyncio
import functools
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import classonlymethod
from asgiref.sync import sync_to_async


class AsyncAPIView(View):
    """异步 API 视图基类"""
    
    @classonlymethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        view._is_coroutine = asyncio.coroutines._is_coroutine
        return view
    
    async def get(self, request, *args, **kwargs):
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    async def post(self, request, *args, **kwargs):
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    async def put(self, request, *args, **kwargs):
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    async def delete(self, request, *args, **kwargs):
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    async def patch(self, request, *args, **kwargs):
        return JsonResponse({'error': 'Method not allowed'}, status=405)


def async_api_response(data=None, error=None, status=200):
    """异步 API 响应辅助函数"""
    if error:
        return JsonResponse({
            'success': False,
            'error': error
        }, status=status)
    return JsonResponse({
        'success': True,
        'data': data
    }, status=status)


def run_async(coro):
    """在同步上下文中运行异步函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
