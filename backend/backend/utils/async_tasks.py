"""异步任务管理器"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


class AsyncTaskManager:
    """异步任务管理器"""
    
    def __init__(self):
        self.tasks = {}
    
    async def run_in_executor(self, func, *args, **kwargs):
        """在线程池中运行同步函数"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, functools.partial(func, *args, **kwargs))
    
    async def run_with_timeout(self, coro, timeout):
        """带超时的异步任务执行"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f'Task timed out after {timeout} seconds')
            raise
    
    async def run_parallel(self, *coros):
        """并行执行多个异步任务"""
        return await asyncio.gather(*coros, return_exceptions=True)
    
    def get_task_status(self, task_id):
        """获取任务状态"""
        return cache.get(f'async_task_{task_id}')
    
    def set_task_status(self, task_id, status, ttl=3600):
        """设置任务状态"""
        cache.set(f'async_task_{task_id}', status, ttl)


import functools


async_task_manager = AsyncTaskManager()
