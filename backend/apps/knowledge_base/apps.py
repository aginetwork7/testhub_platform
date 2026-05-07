from django.apps import AppConfig


class KnowledgeBaseConfig(AppConfig):
    """知识库应用配置"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.knowledge_base'
    verbose_name = '知识库管理'
