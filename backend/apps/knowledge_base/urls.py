from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    KnowledgeBaseViewSet, KnowledgeCategoryViewSet, KnowledgeDocumentViewSet, KnowledgeBaseConfigViewSet
)

router = DefaultRouter()
# 注意：具体路径要先注册，根路径最后注册
router.register(r'configs', KnowledgeBaseConfigViewSet, basename='knowledge-base-config')
router.register(r'categories', KnowledgeCategoryViewSet, basename='knowledge-category')
router.register(r'documents', KnowledgeDocumentViewSet, basename='knowledge-document')
router.register(r'', KnowledgeBaseViewSet, basename='knowledge-base')

urlpatterns = [
    path('', include(router.urls)),
]
