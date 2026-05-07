from django.db import models
from django.conf import settings
import os
from datetime import datetime

logger = None


def get_logger(name):
    """延迟获取logger"""
    global logger
    if logger is None:
        try:
            from backend.log_config import get_logger as _get_logger
            logger = _get_logger(name)
        except Exception:
            import logging
            logger = logging.getLogger(name)
    return logger


def get_default_tags():
    """返回默认标签列表"""
    return []


class KnowledgeBaseConfig(models.Model):
    """知识库与大模型配置模型 (用于替代 config.yaml 中的 LLM 配置)"""
    
    # 基础设置
    is_active = models.BooleanField(default=True, verbose_name='是否启用该配置')
    
    # Embedding 模型配置
    embedding_api_key = models.CharField(max_length=200, verbose_name='Embedding API Key', blank=True, null=True)
    embedding_base_url = models.CharField(max_length=200, verbose_name='Embedding API Base URL', blank=True, null=True)
    embedding_model = models.CharField(max_length=100, default='text-embedding-v3', verbose_name='Embedding 模型名称')
    
    # Refiner (文档结构化) 模型配置
    refiner_api_key = models.CharField(max_length=200, verbose_name='Refiner API Key', blank=True, null=True)
    refiner_base_url = models.CharField(max_length=200, verbose_name='Refiner API Base URL', blank=True, null=True)
    refiner_model = models.CharField(max_length=100, default='qwen-plus', verbose_name='Refiner 模型名称')
    refiner_max_tokens = models.IntegerField(default=8192, verbose_name='Refiner 最大Token数')
    refiner_temperature = models.FloatField(default=0.3, verbose_name='Refiner 温度参数')
    
    # Vision (视觉模型文档解析) 配置 - 支持任意兼容 OpenAI 接口的视觉模型
    vision_api_key = models.CharField(max_length=200, verbose_name='Vision API Key', blank=True, null=True)
    vision_base_url = models.CharField(max_length=200, verbose_name='Vision API Base URL', blank=True, null=True, help_text='留空则使用默认值，智谱: https://open.bigmodel.cn/api/paas/v4, OpenAI: https://api.openai.com/v1')
    vision_model = models.CharField(max_length=100, default='glm-4v-flash', verbose_name='Vision 模型名称', help_text='支持任意兼容 OpenAI 接口的视觉模型，如: gpt-4o, gpt-4-vision-preview, qwen-vl-max, glm-4v-flash 等')
    vision_provider = models.CharField(
        max_length=20, 
        default='zhipu', 
        verbose_name='Vision 服务商',
        help_text='用于选择文档解析方式: zhipu 使用智谱文件解析API，openai 使用通用视觉模型逐页解析',
        choices=[
            ('zhipu', '智谱 (使用文件解析API)'),
            ('openai', 'OpenAI兼容 (使用视觉模型逐页解析)'),
        ]
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'knowledge_base_configs'
        verbose_name = '知识库模型配置'
        verbose_name_plural = '知识库模型配置'

    def save(self, *args, **kwargs):
        # 保证只有一个 active 的配置
        if self.is_active:
            KnowledgeBaseConfig.objects.filter(is_active=True).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"知识库配置 ({'启用' if self.is_active else '禁用'})"


def knowledge_docs_upload_path(instance, filename):
    """自定义上传路径，将知识库文档存储在kb_{id}/YYYY/MM/子目录下"""
    now = datetime.now()
    kb_id = instance.knowledge_base.id if instance.knowledge_base else 0
    return f'knowledge_base/kb_{kb_id}/{now.strftime("%Y/%m")}/{filename}'


def document_version_upload_path(instance, filename):
    """文档版本上传路径"""
    doc_id = instance.document.id if instance.document else 0
    return f'knowledge_base/versions/{doc_id}/{filename}'


class KnowledgeBase(models.Model):
    """知识库模型"""
    name = models.CharField(max_length=200, verbose_name='知识库名称')
    description = models.TextField(blank=True, verbose_name='描述')
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='kb_knowledge_bases',
        verbose_name='关联项目'
    )
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    # 向量化相关配置
    chunk_size = models.PositiveIntegerField(
        default=500,
        verbose_name='分块大小',
        help_text='文档分块时每个块的最大字符数'
    )
    chunk_overlap = models.PositiveIntegerField(
        default=50,
        verbose_name='分块重叠',
        help_text='文档分块时相邻块之间的重叠字符数'
    )
    enable_vectorization = models.BooleanField(
        default=True,
        verbose_name='是否向量化',
        help_text='是否将文档内容向量化存储到向量数据库'
    )
    # 文档解析方式
    use_vision_direct = models.BooleanField(
        default=True,
        verbose_name='使用视觉模型直接解析',
        help_text='是否直接使用视觉模型解析整个文档（推荐），否则使用本地解析+图片识别'
    )
    # 向量化状态
    vectorization_status = models.CharField(
        max_length=20,
        default='pending',
        verbose_name='向量化状态',
        choices=[
            ('pending', '待处理'),
            ('processing', '处理中'),
            ('completed', '已完成'),
            ('failed', '处理失败'),
        ]
    )
    vectorization_error = models.TextField(blank=True, verbose_name='向量化错误信息')
    # 向量集合名称 (用于 ChromaDB)
    collection_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='向量集合名称'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='创建者'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'knowledge_bases'
        verbose_name = '知识库'
        verbose_name_plural = '知识库'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name}"

    @property
    def document_count(self):
        """获取文档数量"""
        return self.documents.count()

    @property
    def total_size(self):
        """获取总文件大小"""
        return self.documents.aggregate(
            total=models.Sum('file_size')
        )['total'] or 0


class KnowledgeCategory(models.Model):
    """知识库分类模型 - 支持多级树形结构"""
    name = models.CharField(max_length=100, verbose_name='分类名称')
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name='categories',
        verbose_name='所属知识库'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父级分类'
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='排序')
    description = models.TextField(blank=True, verbose_name='分类描述')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'knowledge_categories'
        verbose_name = '知识库分类'
        verbose_name_plural = '知识库分类'
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return f"{self.name}"

    @property
    def document_count(self):
        """获取分类下文档数量"""
        return self.documents.count()

    @property
    def full_path(self):
        """获取分类完整路径"""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name


class KnowledgeDocument(models.Model):
    """知识库文档模型"""
    DOCUMENT_TYPE_CHOICES = [
        ('pdf', 'PDF文档'),
        ('docx', 'Word文档'),
        ('doc', 'Word文档(旧版)'),
        ('txt', '文本文档'),
        ('md', 'Markdown文档'),
    ]

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('published', '已发布'),
        ('archived', '已归档'),
    ]

    VECTOR_STATUS_CHOICES = [
        ('pending', '待处理'),
        ('processing', '处理中'),
        ('completed', '已完成'),
        ('failed', '处理失败'),
    ]

    title = models.CharField(max_length=300, verbose_name='文档标题')
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='所属知识库'
    )
    category = models.ForeignKey(
        KnowledgeCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        verbose_name='所属分类'
    )
    file = models.FileField(
        upload_to=knowledge_docs_upload_path,
        verbose_name='文档文件',
        null=True,
        blank=True
    )
    document_type = models.CharField(
        max_length=10,
        choices=DOCUMENT_TYPE_CHOICES,
        verbose_name='文档类型',
        blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='状态'
    )
    content = models.TextField(blank=True, verbose_name='文档内容(纯文本)')
    description = models.TextField(blank=True, verbose_name='文档描述')
    tags = models.JSONField(default=get_default_tags, verbose_name='标签列表')
    version_number = models.PositiveIntegerField(default=1, verbose_name='当前版本号')
    file_size = models.PositiveIntegerField(
        verbose_name='文件大小(bytes)',
        null=True,
        blank=True
    )
    # 向量化相关字段
    vector_status = models.CharField(
        max_length=20,
        choices=VECTOR_STATUS_CHOICES,
        default='pending',
        verbose_name='向量化状态'
    )
    vector_error = models.TextField(blank=True, verbose_name='向量化错误信息')
    chunk_count = models.PositiveIntegerField(default=0, verbose_name='分块数量')
    # 文档来源: upload(上传) 或 initial(创建知识库时上传)
    source = models.CharField(
        max_length=20,
        default='upload',
        verbose_name='文档来源',
        choices=[
            ('upload', '后续上传'),
            ('initial', '创建时上传'),
        ]
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kb_documents',
        verbose_name='上传者'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'knowledge_documents'
        verbose_name = '知识库文档'
        verbose_name_plural = '知识库文档'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - v{self.version_number}"

    def save(self, *args, **kwargs):
        # 更新时自动更新版本号
        if self.pk:
            try:
                old_version = KnowledgeDocument.objects.get(pk=self.pk)
                if old_version and old_version.file != self.file:
                    # 文件发生变化，创建版本记录
                    DocumentVersion.objects.create(
                        document=old_version,
                        version_number=old_version.version_number,
                        file=old_version.file,
                        content=old_version.content,
                        change_log='文档更新',
                        created_by=self.uploaded_by
                    )
                    self.version_number = old_version.version_number + 1
            except KnowledgeDocument.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    @property
    def file_url(self):
        """获取文件URL"""
        if self.file:
            return self.file.url
        return None

    @property
    def tags_display(self):
        """获取标签显示"""
        return ', '.join(self.tags) if self.tags else ''

    @property
    def document_type_display(self):
        """获取文档类型显示"""
        return self.get_document_type_display()


class DocumentVersion(models.Model):
    """文档版本记录模型"""
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name='versions',
        verbose_name='关联文档'
    )
    version_number = models.PositiveIntegerField(verbose_name='版本号')
    file = models.FileField(
        upload_to=document_version_upload_path,
        verbose_name='版本文件快照'
    )
    content = models.TextField(blank=True, verbose_name='版本内容快照')
    change_log = models.TextField(blank=True, verbose_name='变更说明')
    file_size = models.PositiveIntegerField(
        verbose_name='文件大小(bytes)',
        null=True,
        blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='创建者'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'document_versions'
        verbose_name = '文档版本'
        verbose_name_plural = '文档版本'
        ordering = ['-version_number']
        unique_together = ['document', 'version_number']

    def __str__(self):
        return f"{self.document.title} - v{self.version_number}"
