from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django.db.models import Q, Sum
from django.utils import timezone
import os

from .models import (
    KnowledgeBase, KnowledgeCategory, KnowledgeDocument, DocumentVersion, KnowledgeBaseConfig
)
from .serializers import (
    KnowledgeBaseSerializer, KnowledgeBaseCreateSerializer,
    KnowledgeCategorySerializer, KnowledgeCategoryTreeSerializer,
    KnowledgeDocumentSerializer, DocumentUploadSerializer, DocumentVersionSerializer,
    KnowledgeBaseConfigSerializer
)
from .services import (
    knowledge_base_service, DocumentParser, 
    get_knowledge_base_config, check_knowledge_base_config
)
from backend.log_config import get_logger

logger = get_logger(__name__)


class KnowledgeBaseConfigViewSet(viewsets.ModelViewSet):
    """知识库大模型配置视图集"""
    queryset = KnowledgeBaseConfig.objects.all()
    serializer_class = KnowledgeBaseConfigSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        """获取当前激活的配置"""
        config = self.queryset.filter(is_active=True).first()
        if not config:
            return Response({
                'configured': False,
                'id': None,
                'embedding_model': 'text-embedding-v3',
                'refiner_model': 'qwen-plus',
                'refiner_max_tokens': 8192,
                'refiner_temperature': 0.3,
                'vision_base_url': '',
                'vision_model': 'glm-4v-flash',
                'vision_provider': 'zhipu',
                'message': '未找到激活的配置'
            })
        
        serializer = self.get_serializer(config)
        data = serializer.data
        data['configured'] = True
        return Response(data)

    def create(self, request, *args, **kwargs):
        """保存/更新配置（单例模式）"""
        data = request.data
        config = self.queryset.filter(is_active=True).first()
        
        for field in ['embedding_api_key', 'refiner_api_key', 'vision_api_key']:
            if data.get(field) and data[field].startswith('****') or data.get(field) and '****' in data[field]:
                if config:
                    data[field] = getattr(config, field)
                else:
                    data.pop(field, None)

        if config:
            serializer = self.get_serializer(config, data=data, partial=True)
        else:
            data['is_active'] = True
            serializer = self.get_serializer(data=data)
            
        serializer.is_valid(raise_exception=True)
        self.perform_save(serializer)
        return Response(serializer.data)

    def perform_save(self, serializer):
        serializer.save()

    @action(detail=False, methods=['post'])
    def test_connection(self, request):
        """测试模型连接 (可拓展)"""
        # 这里可以实现分别测试三种模型连接的逻辑
        return Response({'message': '测试连接成功', 'status': 'success'})


def extract_text_from_file(file_path, document_type):
    """从文件中提取文本"""
    try:
        if document_type == 'pdf':
            from backend.apps.requirement_analysis.services import DocumentProcessor
            return DocumentProcessor.extract_text_from_pdf(file_path)
        elif document_type in ['doc', 'docx']:
            from backend.apps.requirement_analysis.services import DocumentProcessor
            return DocumentProcessor.extract_text_from_docx(file_path)
        elif document_type == 'txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        elif document_type == 'md':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        logger.error(f"提取文本失败: {e}")
        return ""


class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    """知识库视图集"""
    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    filterset_fields = ['name', 'description', 'project', 'is_active']
    search_fields = ['name', 'description']
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        """根据操作类型选择序列化器"""
        if self.action == 'create':
            return KnowledgeBaseCreateSerializer
        return KnowledgeBaseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # 只在参数有值时才进行过滤
        project_id = self.request.query_params.get('project_id')
        if project_id and project_id.strip():
            queryset = queryset.filter(project_id=project_id)
        is_active = self.request.query_params.get('is_active')
        if is_active is not None and is_active != '':
            is_active = is_active.lower() == 'true'
            queryset = queryset.filter(is_active=is_active)
        search = self.request.query_params.get('search')
        if search and search.strip():
            queryset = queryset.filter(name__icontains=search)
        return queryset

    def perform_create(self, serializer):
        """创建知识库，支持同时上传初始文档"""
        knowledge_base = serializer.save(created_by=self.request.user)

        if knowledge_base.enable_vectorization:
            is_valid, error_msg = check_knowledge_base_config(require_embedding=True)
            if not is_valid:
                knowledge_base.vectorization_status = 'failed'
                knowledge_base.vectorization_error = error_msg
                knowledge_base.enable_vectorization = False
                knowledge_base.save(update_fields=['vectorization_status', 'vectorization_error', 'enable_vectorization'])
                logger.warning(f"知识库创建时 Embedding 配置检查失败: {error_msg}")
            else:
                collection_name = knowledge_base_service.create_knowledge_base_collection(
                    knowledge_base
                )
                if collection_name:
                    knowledge_base.vectorization_status = 'processing'
                    knowledge_base.save(update_fields=['vectorization_status'])
                else:
                    knowledge_base.vectorization_status = 'failed'
                    knowledge_base.vectorization_error = '创建向量集合失败'
                    knowledge_base.save(update_fields=['vectorization_status', 'vectorization_error'])

        # 如果有初始上传的文档，异步处理
        initial_document = getattr(knowledge_base, '_initial_document', None)
        if initial_document:
            # 保存 ID 而不是对象引用，避免跨线程问题
            kb_id = knowledge_base.pk
            doc_id = initial_document.pk

            # 使用线程异步处理文档
            def process_in_background():
                from django.db import connection
                from .models import KnowledgeBase, KnowledgeDocument
                import traceback

                try:
                    # 重新获取对象（新线程需要新的数据库连接）
                    kb = KnowledgeBase.objects.get(pk=kb_id)
                    doc = KnowledgeDocument.objects.get(pk=doc_id)

                    # 处理文档：提取文本、分块、向量化
                    result = knowledge_base_service.process_document(
                        document=doc,
                        chunk_size=kb.chunk_size,
                        chunk_overlap=kb.chunk_overlap,
                        enable_vectorization=kb.enable_vectorization,
                        use_vision_direct=getattr(kb, 'use_vision_direct', True)
                    )
                    logger.info(f"初始文档处理完成: {result}")

                    # 更新知识库向量化状态
                    if kb.enable_vectorization:
                        docs = kb.documents.all()
                        if docs.exists():
                            all_completed = all(
                                d.vector_status == 'completed' for d in docs
                            )
                            any_failed = any(
                                d.vector_status == 'failed' for d in docs
                            )
                            if all_completed:
                                kb.vectorization_status = 'completed'
                            elif any_failed:
                                kb.vectorization_status = 'failed'
                            kb.save(update_fields=['vectorization_status'])
                        else:
                            kb.vectorization_status = 'completed'
                            kb.save(update_fields=['vectorization_status'])
                except KnowledgeBase.DoesNotExist:
                    logger.warning(f"知识库 {kb_id} 已被删除，跳过文档处理")
                except KnowledgeDocument.DoesNotExist:
                    logger.warning(f"文档 {doc_id} 已被删除，跳过处理")
                except Exception as e:
                    logger.error(f"初始文档处理失败: {e}")
                    logger.error(traceback.format_exc())
                    try:
                        kb = KnowledgeBase.objects.get(pk=kb_id)
                        kb.vectorization_status = 'failed'
                        kb.vectorization_error = str(e)
                        kb.save(update_fields=['vectorization_status', 'vectorization_error'])
                    except KnowledgeBase.DoesNotExist:
                        pass  # 知识库已被删除，无需更新状态
                    except Exception:
                        pass

            # 使用 transaction.on_commit 确保事务提交后再启动后台线程
            from django.db import transaction
            import threading

            def start_thread():
                thread = threading.Thread(target=process_in_background)
                thread.daemon = True
                thread.start()

            transaction.on_commit(start_thread)
        elif knowledge_base.enable_vectorization:
            # 没有初始文档，直接标记为完成
            knowledge_base.vectorization_status = 'completed'
            knowledge_base.save(update_fields=['vectorization_status'])

    def perform_destroy(self, instance):
        """删除知识库时，同时删除向量数据"""
        # 删除向量集合
        if instance.collection_name:
            knowledge_base_service.delete_knowledge_base_vectors(instance)
        # 删除知识库
        instance.delete()

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """获取知识库统计信息"""
        kb = self.get_object()
        return Response({
            'total_documents': kb.documents.count(),
            'total_categories': kb.categories.count(),
            'total_size': kb.documents.aggregate(
                total=Sum('file_size')
            )['total'] or 0,
            'published_count': kb.documents.filter(status='published').count(),
            'draft_count': kb.documents.filter(status='draft').count(),
            'archived_count': kb.documents.filter(status='archived').count(),
        })

    @action(detail=False, methods=['get'])
    def check_config(self, request):
        """检查知识库配置状态"""
        config_status = get_knowledge_base_config()
        return Response({
            'configured': config_status['configured'],
            'has_embedding': config_status['has_embedding'],
            'has_vision': config_status['has_vision'],
            'has_refiner': config_status['has_refiner'],
            'message': config_status['message']
        })

    @action(detail=True, methods=['get'])
    def categories_tree(self, request, pk=None):
        """获取知识库分类树形结构"""
        kb = self.get_object()
        categories = KnowledgeCategory.objects.filter(knowledge_base=kb)
        tree = self._build_tree(categories, None)
        return Response(tree)

    @action(detail=True, methods=['post'], parser_classes=[JSONParser])
    def semantic_search(self, request, pk=None):
        """语义搜索 - 召回检索"""
        kb = self.get_object()

        query = request.data.get('query', '')
        top_k = request.data.get('top_k', 5)
        similarity_threshold = request.data.get('similarity_threshold', 0)

        if not query:
            return Response(
                {'error': '请输入搜索内容'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not kb.enable_vectorization or not kb.collection_name:
            return Response(
                {'error': '知识库未启用向量化或未完成向量化'},
                status=status.HTTP_400_BAD_REQUEST
            )

        is_valid, error_msg = check_knowledge_base_config(require_embedding=True)
        if not is_valid:
            return Response(
                {'error': error_msg},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            results = knowledge_base_service.search_similar(
                knowledge_base=kb,
                query=query,
                n_results=top_k
            )

            # 格式化返回结果
            formatted_results = []
            for result in results:
                # 将距离转换为相似度 (cosine distance -> similarity)
                distance = result.get('distance', 0)
                similarity = 1 - distance  # cosine distance 转换为相似度
                similarity = max(0, min(1, similarity))  # 确保在 0-1 范围内

                # 根据相似度阈值过滤
                if similarity < similarity_threshold:
                    continue

                metadata = result.get('metadata', {})
                formatted_results.append({
                    'id': result.get('id'),
                    'content': result.get('text', ''),
                    'document_id': metadata.get('document_id'),
                    'document_title': metadata.get('title', ''),
                    'chunk_index': metadata.get('start_index', 0),
                    'similarity': similarity,
                    'file_url': None,
                    'full_content': None
                })

            return Response({
                'query': query,
                'total': len(formatted_results),
                'results': formatted_results
            })
        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return Response(
                {'error': f'搜索失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], parser_classes=[JSONParser])
    def hybrid_search(self, request, pk=None):
        """混合检索 - 结合关键词检索和语义检索"""
        kb = self.get_object()

        query = request.data.get('query', '')
        top_k = request.data.get('top_k', 5)
        similarity_threshold = request.data.get('similarity_threshold', 0)
        keyword_weight = request.data.get('keyword_weight', 0.3)
        semantic_weight = request.data.get('semantic_weight', 0.7)

        if not query:
            return Response(
                {'error': '请输入搜索内容'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if kb.enable_vectorization:
            is_valid, error_msg = check_knowledge_base_config(require_embedding=True)
            if not is_valid:
                return Response(
                    {'error': error_msg},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            results = knowledge_base_service.hybrid_search(
                knowledge_base=kb,
                query=query,
                n_results=top_k,
                keyword_weight=keyword_weight,
                semantic_weight=semantic_weight
            )

            # 根据相似度阈值过滤
            formatted_results = []
            for result in results:
                combined_score = result.get('combined_score', 0)
                if combined_score < similarity_threshold:
                    continue

                formatted_results.append({
                    'id': result.get('chunk_id') or result.get('id'),
                    'content': result.get('text', ''),
                    'document_id': result.get('document_id'),
                    'document_title': result.get('document_title', ''),
                    'chunk_index': result.get('chunk_index', 0),
                    'similarity': combined_score,
                    'combined_score': combined_score,
                    'semantic_score': result.get('semantic_score', 0),
                    'keyword_score': result.get('keyword_score', 0),
                    'source': result.get('source', 'hybrid'),
                    'file_url': result.get('file_url'),
                    'full_content': result.get('full_content')
                })

            return Response({
                'query': query,
                'total': len(formatted_results),
                'results': formatted_results,
                'search_type': 'hybrid'
            })
        except Exception as e:
            logger.error(f"混合检索失败: {e}")
            return Response(
                {'error': f'搜索失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _build_tree(self, categories, parent_id):
        """递归构建树形结构"""
        nodes = categories.filter(parent_id=parent_id)
        result = []
        for node in nodes:
            item = KnowledgeCategoryTreeSerializer(node).data
            item['children'] = self._build_tree(categories, node.id)
            result.append(item)
        return result


class KnowledgeCategoryViewSet(viewsets.ModelViewSet):
    """知识库分类视图集"""
    queryset = KnowledgeCategory.objects.all()
    serializer_class = KnowledgeCategorySerializer
    filterset_fields = ['name', 'knowledge_base', 'parent', 'sort_order']

    def get_queryset(self):
        queryset = super().get_queryset()
        knowledge_base_id = self.request.query_params.get('knowledge_base_id')
        if knowledge_base_id:
            queryset = queryset.filter(knowledge_base_id=knowledge_base_id)
        return queryset

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """获取分类树形结构"""
        kb_id = request.query_params.get('knowledge_base_id')
        if not kb_id:
            return Response(
                {'error': '缺少knowledge_base_id参数'},
                status=status.HTTP_400_BAD_REQUEST
            )
        categories = KnowledgeCategory.objects.filter(knowledge_base_id=kb_id)
        tree = self._build_category_tree(categories, None)
        return Response(tree)

    def _build_category_tree(self, categories, parent_id):
        """递归构建分类树形结构"""
        nodes = categories.filter(parent_id=parent_id)
        result = []
        for node in nodes:
            item = KnowledgeCategorySerializer(node).data
            item['children'] = self._build_category_tree(categories, node.id)
            result.append(item)
        return result


class KnowledgeDocumentViewSet(viewsets.ModelViewSet):
    """知识库文档视图集"""
    queryset = KnowledgeDocument.objects.all()
    serializer_class = KnowledgeDocumentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return DocumentUploadSerializer
        return KnowledgeDocumentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        knowledge_base_id = self.request.query_params.get('knowledge_base_id')
        category_id = self.request.query_params.get('category_id')
        doc_status = self.request.query_params.get('status')
        search = self.request.query_params.get('search')
        document_type = self.request.query_params.get('document_type')

        if knowledge_base_id:
            queryset = queryset.filter(knowledge_base_id=knowledge_base_id)
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        if doc_status:
            queryset = queryset.filter(status=doc_status)
        if document_type:
            queryset = queryset.filter(document_type=document_type)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search) |
                Q(description__icontains=search) |
                Q(tags__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        """创建文档时自动提取文本内容"""
        document = serializer.save()
        # 提取文本
        if document.file:
            try:
                file_path = document.file.path
                if os.path.exists(file_path):
                    content = extract_text_from_file(
                        file_path,
                        document.document_type
                    )
                    if content:
                        KnowledgeDocument.objects.filter(pk=document.pk).update(
                            content=content
                        )
            except Exception as e:
                logger.warning(f"文本提取失败: {e}")

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """下载文档"""
        document = self.get_object()
        if not document.file:
            return Response(
                {'error': '文件不存在'},
                status=status.HTTP_404_NOT_FOUND
            )
        try:
            response = FileResponse(
                document.file.open('rb'),
                content_type='application/octet-stream'
            )
            filename = os.path.basename(document.file.name)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            return Response(
                {'error': f'文件下载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """预览文档"""
        document = self.get_object()
        return Response({
            'id': document.id,
            'title': document.title,
            'content': document.content,
            'document_type': document.document_type,
            'file_url': document.file.url if document.file else None,
            'description': document.description,
            'tags': document.tags,
            'status': document.status,
            'version_number': document.version_number,
            'created_at': document.created_at,
            'updated_at': document.updated_at
        })

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        """获取文档版本列表"""
        document = self.get_object()
        versions = document.versions.all()
        serializer = DocumentVersionSerializer(versions, many=True)
        return Response({
            'versions': serializer.data,
            'total': versions.count()
        })

    @action(detail=True, methods=['post'])
    def restore_version(self, request, pk=None):
        """恢复到指定版本"""
        document = self.get_object()
        version_number = request.data.get('version_number')
        try:
            version = DocumentVersion.objects.get(
                document=document,
                version_number=version_number
            )
        except DocumentVersion.DoesNotExist:
            return Response(
                {'error': '版本不存在'},
                status=status.HTTP_404_NOT_FOUND
            )
        # 恢复版本
        document.file = version.file
        document.content = version.content
        document.version_number = version.version_number
        document.file_size = version.file_size
        document.save()
        serializer = KnowledgeDocumentSerializer(document)
        return Response({
            'message': f'已恢复到版本 {version_number}',
            'document': serializer.data
        })

    @action(detail=False, methods=['get'])
    def search(self, request):
        """全文搜索"""
        keyword = request.query_params.get('keyword', '')
        knowledge_base_id = request.query_params.get('knowledge_base_id')

        if not keyword:
            return Response(
                {'error': '缺少keyword参数'},
                status=status.HTTP_400_BAD_REQUEST
            )
        queryset = KnowledgeDocument.objects.all()
        if knowledge_base_id:
            queryset = queryset.filter(knowledge_base_id=knowledge_base_id)
        queryset = queryset.filter(
            Q(title__icontains=keyword) |
            Q(content__icontains=keyword) |
            Q(description__icontains=keyword) |
            Q(tags__icontains=keyword)
        )
        serializer = KnowledgeDocumentSerializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'total': queryset.count(),
            'keyword': keyword
        })
