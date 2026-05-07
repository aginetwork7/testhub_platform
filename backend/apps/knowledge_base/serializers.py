from rest_framework import serializers
from django.db.models import Sum
from .models import (
    KnowledgeBase, KnowledgeCategory, KnowledgeDocument, DocumentVersion, KnowledgeBaseConfig
)

class KnowledgeBaseConfigSerializer(serializers.ModelSerializer):
    """知识库配置序列化器"""
    class Meta:
        model = KnowledgeBaseConfig
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        for field in ['embedding_api_key', 'refiner_api_key', 'vision_api_key']:
            if ret.get(field):
                key = ret[field]
                if len(key) > 8:
                    ret[f'{field}_masked'] = f"{key[:4]}****{key[-4:]}"
                else:
                    ret[f'{field}_masked'] = "****"
            else:
                ret[f'{field}_masked'] = ""
        return ret


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    """知识库序列化器"""
    project_name = serializers.CharField(source='project.name', read_only=True)
    document_count = serializers.SerializerMethodField()
    total_size = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    category_count = serializers.SerializerMethodField()
    vectorization_status_display = serializers.CharField(
        source='get_vectorization_status_display', read_only=True
    )

    class Meta:
        model = KnowledgeBase
        fields = [
            'id', 'name', 'description', 'project', 'project_name',
            'is_active', 'document_count', 'total_size', 'category_count',
            'chunk_size', 'chunk_overlap', 'enable_vectorization',
            'vectorization_status', 'vectorization_status_display',
            'vectorization_error', 'collection_name',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_by', 'updated_at', 'vectorization_status',
            'vectorization_error', 'collection_name'
        ]

    def get_document_count(self, obj):
        return obj.documents.count()

    def get_total_size(self, obj):
        total = obj.documents.aggregate(total=Sum('file_size'))['total'] or 0
        return total

    def get_category_count(self, obj):
        return obj.categories.count()


class KnowledgeBaseCreateSerializer(serializers.ModelSerializer):
    """知识库创建序列化器 - 支持同时上传初始文档"""
    file = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = KnowledgeBase
        fields = [
            'id', 'name', 'description', 'project', 'is_active',
            'chunk_size', 'chunk_overlap', 'enable_vectorization',
            'file'
        ]

    def validate_file(self, value):
        """验证上传的文件"""
        if value:
            allowed_extensions = ['.pdf', '.doc', '.docx', '.txt', '.md']
            filename = value.name.lower()
            if not any(filename.endswith(ext) for ext in allowed_extensions):
                raise serializers.ValidationError(
                    "不支持的文件格式，请上传 PDF、Word、TXT 或 Markdown 文件"
                )
            # 检查文件大小 (最大 50MB)
            if value.size > 50 * 1024 * 1024:
                raise serializers.ValidationError("文件大小不能超过 50MB")
        return value

    def validate_chunk_size(self, value):
        """验证分块大小"""
        if value < 100 or value > 5000:
            raise serializers.ValidationError("分块大小必须在 100-5000 之间")
        return value

    def validate_chunk_overlap(self, value):
        """验证分块重叠"""
        try:
            chunk_size = int(self.initial_data.get('chunk_size', 500))
        except (ValueError, TypeError):
            chunk_size = 500
        if value >= chunk_size:
            raise serializers.ValidationError("分块重叠必须小于分块大小")
        if value < 0:
            raise serializers.ValidationError("分块重叠不能为负数")
        return value

    def create(self, validated_data):
        """创建知识库"""
        file = validated_data.pop('file', None)
        knowledge_base = super().create(validated_data)

        # 如果有上传文件，创建初始文档记录
        if file:
            from .models import KnowledgeDocument
            import os

            # 确定文档类型
            filename = file.name.lower()
            if filename.endswith('.pdf'):
                doc_type = 'pdf'
            elif filename.endswith('.doc') or filename.endswith('.docx'):
                doc_type = 'docx'
            elif filename.endswith('.txt'):
                doc_type = 'txt'
            elif filename.endswith('.md'):
                doc_type = 'md'
            else:
                doc_type = 'txt'

            # 创建文档记录
            document = KnowledgeDocument.objects.create(
                title=os.path.splitext(file.name)[0],
                knowledge_base=knowledge_base,
                file=file,
                document_type=doc_type,
                file_size=file.size,
                source='initial',
                uploaded_by=validated_data.get('created_by'),
                status='published'
            )

            # 保存文档ID供后续处理
            knowledge_base._initial_document = document

        return knowledge_base


class KnowledgeCategorySerializer(serializers.ModelSerializer):
    """知识库分类序列化器"""
    knowledge_base_name = serializers.CharField(source='knowledge_base.name', read_only=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    document_count = serializers.SerializerMethodField()
    full_path = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeCategory
        fields = [
            'id', 'name', 'knowledge_base', 'knowledge_base_name',
            'parent', 'parent_name', 'sort_order', 'description',
            'document_count', 'full_path',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['knowledge_base', 'created_at', 'updated_at']

    def get_document_count(self, obj):
        return obj.documents.count()

    def get_full_path(self, obj):
        if obj.parent:
            return f"{obj.parent.full_path} > {obj.name}"
        return obj.name

    def get_parent_name(self, obj):
        return obj.parent.name if obj.parent else None


class KnowledgeCategoryTreeSerializer(serializers.ModelSerializer):
    """知识库分类树形结构序列化器"""
    children = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeCategory
        fields = ['id', 'name', 'parent', 'children', 'sort_order', 'document_count', 'full_path']
        read_only_fields = ['knowledge_base', 'created_at', 'updated_at']

    def get_children(self, obj):
        children = obj.knowledge_base.categories.filter(parent=obj)
        return KnowledgeCategoryTreeSerializer(children, many=True).data


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    """知识库文档序列化器"""
    knowledge_base_name = serializers.CharField(source='knowledge_base.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    tags_display = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source='uploaded_by.username', read_only=True)
    file_url = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()
    category_info = serializers.SerializerMethodField()
    vector_status_display = serializers.CharField(source='get_vector_status_display', read_only=True)

    created_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M', read_only=True)
    updated_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M', read_only=True)

    class Meta:
        model = KnowledgeDocument
        fields = [
            'id', 'title', 'knowledge_base', 'knowledge_base_name', 'category', 'category_name', 'category_info',
            'file', 'file_url', 'document_type', 'document_type_display',
            'status', 'status_display',
            'description', 'tags', 'tags_display',
            'version_number', 'version_count', 'file_size', 'uploaded_by', 'uploaded_by_name',
            'vector_status', 'vector_status_display', 'vector_error', 'chunk_count', 'source',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'knowledge_base', 'file', 'content', 'created_by', 'updated_at',
            'vector_status', 'vector_error', 'chunk_count'
        ]

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None

    def get_category_info(self, obj):
        if obj.category:
            return {
                'id': obj.category.id,
                'name': obj.category.name,
                'full_path': obj.category.full_path
            }
        return None

    def get_version_count(self, obj):
        return obj.versions.count()

    def get_tags_display(self, obj):
        return ', '.join(obj.tags) if obj.tags else ''


class DocumentUploadSerializer(serializers.ModelSerializer):
    """文档上传专用序列化器"""
    class Meta:
        model = KnowledgeDocument
        fields = ['id', 'title', 'file', 'knowledge_base', 'category', 'description', 'tags', 'status']

    def create(self, validated_data):
        # 自动设置上传者
        user = self.context['request'].user
        if user.is_authenticated:
            validated_data['uploaded_by'] = user
        else:
            # 如果是匿名用户，使用第一个超级用户作为默认用户
            from apps.users.models import User
            default_user = User.objects.filter(is_superuser=True).first()
            if not default_user:
                default_user = User.objects.first()
            validated_data['uploaded_by'] = default_user

        # 自动设置文档类型
        file = validated_data.get('file')
        if file:
            filename = file.name.lower()
            if filename.endswith('.pdf'):
                validated_data['document_type'] = 'pdf'
            elif filename.endswith('.doc') or filename.endswith('.docx'):
                validated_data['document_type'] = 'docx'
            elif filename.endswith('.txt'):
                validated_data['document_type'] = 'txt'
            elif filename.endswith('.md'):
                validated_data['document_type'] = 'md'
            else:
                raise serializers.ValidationError("不支持的文件格式，请上传 PDF、Word、TXT 或 Markdown 文件")

        # 自动设置文件大小
        if file:
            validated_data['file_size'] = file.size

        return super().create(validated_data)

    def update(self, instance, validated_data):
        # 更新时保留原有文件（用于版本记录)
        old_file = instance.file
        instance.file = validated_data.get('file', instance.file)
        # 重新设置文件大小
        if instance.file:
            instance.file_size = instance.file.size
        instance.save()
        return instance


class DocumentVersionSerializer(serializers.ModelSerializer):
    """文档版本序列化器"""
    document_title = serializers.CharField(source='document.title', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    file_url = serializers.SerializerMethodField()
    document_type_display = serializers.CharField(source='document.get_document_type_display', read_only=True)

    class Meta:
        model = DocumentVersion
        fields = [
            'id', 'document', 'document_title',
            'version_number', 'file', 'file_url',
            'content', 'change_log', 'file_size',
            'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['document', 'file', 'content', 'created_by']

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None
