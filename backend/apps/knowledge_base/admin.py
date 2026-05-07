from django.contrib import admin
from .models import (
    KnowledgeBase, KnowledgeCategory, KnowledgeDocument, DocumentVersion
)


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    """知识库管理"""
    list_display = ['name', 'project', 'is_active', 'created_by', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    raw_id_fields = ['project', 'created_by']


@admin.register(KnowledgeCategory)
class KnowledgeCategoryAdmin(admin.ModelAdmin):
    """知识库分类管理"""
    list_display = ['name', 'knowledge_base', 'parent', 'sort_order', 'created_at']
    list_filter = ['knowledge_base', 'created_at']
    search_fields = ['name', 'description']
    raw_id_fields = ['knowledge_base', 'parent']


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    """知识库文档管理"""
    list_display = ['title', 'knowledge_base', 'category', 'document_type', 'status', 'version_number', 'created_at']
    list_filter = ['document_type', 'status', 'knowledge_base', 'created_at']
    search_fields = ['title', 'description', 'content', 'tags']
    raw_id_fields = ['knowledge_base', 'category', 'uploaded_by']


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    """文档版本管理"""
    list_display = ['document', 'version_number', 'created_by', 'created_at']
    list_filter = ['created_at']
    search_fields = ['document__title', 'change_log']
    raw_id_fields = ['document', 'created_by']
