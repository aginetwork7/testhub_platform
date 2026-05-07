"""数据库查询优化工具"""
from django.db import models
from django.db.models import Prefetch, Q
from functools import lru_cache


class QueryOptimizer:
    """查询优化器"""
    
    @staticmethod
    def optimize_queryset(queryset, select_related=None, prefetch_related=None):
        """优化查询集"""
        if select_related:
            queryset = queryset.select_related(*select_related)
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)
        return queryset
    
    @staticmethod
    def bulk_create_optimized(model, objects, batch_size=1000):
        """批量创建优化"""
        return model.objects.bulk_create(objects, batch_size=batch_size)
    
    @staticmethod
    def bulk_update_optimized(queryset, fields, batch_size=1000):
        """批量更新优化"""
        return queryset.bulk_update(batch_size=batch_size, fields=fields)


class JSONFieldQueryHelper:
    """JSON 字段查询辅助类"""
    
    @staticmethod
    def contains(field, key, value):
        """JSON 字段包含查询"""
        return models.Q(**{f'{field}__contains': {key: value}})
    
    @staticmethod
    def has_key(field, key):
        """JSON 字段包含键查询"""
        return models.Q(**{f'{field}__has_key': key})
    
    @staticmethod
    def has_any_keys(field, keys):
        """JSON 字段包含任意键查询"""
        return models.Q(**{f'{field}__has_any_keys': keys})
    
    @staticmethod
    def has_all_keys(field, keys):
        """JSON 字段包含所有键查询"""
        return models.Q(**{f'{field}__has_all_keys': keys})


class DatabaseIndexHelper:
    """数据库索引辅助类"""
    
    @staticmethod
    def get_index_hints():
        """获取索引提示"""
        return {
            'api_request': ['collection', 'created_by', 'method'],
            'test_execution': ['test_suite', 'status', 'executed_at'],
            'request_history': ['request', 'executed_by', 'executed_at'],
        }


query_optimizer = QueryOptimizer()
json_field_helper = JSONFieldQueryHelper()
