from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.users.models import User
from apps.projects.models import Project
import json
import os
import re
from pathlib import Path
import httpx
from typing import Dict, Any, List, AsyncIterator, Optional
from asgiref.sync import sync_to_async

from django.core.files.storage import FileSystemStorage
from backend.log_config import get_logger

# 自定义存储类，用于存储需求文档到项目根目录下的 Data/PRD
class RequirementDocsStorage(FileSystemStorage):
    """自定义存储类，将需求文档存储在 Data/PRD 目录下。"""
    def __init__(self, *args, **kwargs):
        # 获取项目根目录
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        # 设置存储位置为 Data/PRD 目录
        location = os.path.join(project_root, 'Data', 'PRD')
        # 设置URL前缀
        base_url = '/media/'
        super().__init__(location=location, base_url=base_url)

# 创建存储实例
requirement_docs_storage = RequirementDocsStorage()


def normalize_prd_directory_name(value: str) -> str:
    text = str(value or '').strip()
    text = re.sub(r'[\\/:*?"<>|]+', '_', text)
    text = re.sub(r'\s+', ' ', text).strip().strip('.')
    if not text or not re.sub(r'[_\-\.\s]+', '', text):
        return 'untitled'
    return text or 'untitled'


def get_prd_storage_root() -> Path:
    return Path(requirement_docs_storage.location).resolve()


def resolve_prd_date_token(created_at=None) -> str:
    if created_at is not None:
        return created_at.strftime('%Y%m%d')

    from datetime import datetime

    return datetime.now().strftime('%Y%m%d')


def requirement_document_relative_dir(instance, filename: str = '') -> str:
    date_token = resolve_prd_date_token(getattr(instance, 'created_at', None))
    title = str(getattr(instance, 'title', '') or '').strip()
    fallback_name = Path(str(filename or 'document')).stem
    directory_name = normalize_prd_directory_name(title or fallback_name)
    return f'{date_token}/{directory_name}'


def build_prd_artifact_relative_path(title: str, created_at, artifact_name: str) -> str:
    directory_name = normalize_prd_directory_name(title)
    safe_artifact_name = Path(str(artifact_name or 'artifact.txt')).name
    return f'{resolve_prd_date_token(created_at)}/{directory_name}/{safe_artifact_name}'


def write_prd_text_artifact(title: str, created_at, artifact_name: str, content: str) -> Path | None:
    text = str(content or '').strip()
    if not text:
        return None

    relative_path = build_prd_artifact_relative_path(title, created_at, artifact_name)
    target_path = get_prd_storage_root() / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(text, encoding='utf-8')
    return target_path


def write_prd_json_artifact(title: str, created_at, artifact_name: str, payload) -> Path | None:
    if payload in (None, '', [], {}):
        return None

    relative_path = build_prd_artifact_relative_path(title, created_at, artifact_name)
    target_path = get_prd_storage_root() / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return target_path


def sync_requirement_document_artifacts(document) -> None:
    write_prd_text_artifact(document.title, document.created_at, 'extracted_text.txt', document.extracted_text)


def sync_requirement_analysis_artifacts(analysis) -> None:
    write_prd_text_artifact(analysis.document.title, analysis.document.created_at, 'analysis_report.md', analysis.analysis_report)


def sync_business_requirements_artifact(analysis) -> None:
    requirements_payload = list(
        analysis.requirements.order_by('requirement_id', 'id').values(
            'requirement_id',
            'requirement_name',
            'requirement_type',
            'module',
            'requirement_level',
            'reviewer',
            'estimated_hours',
            'description',
            'acceptance_criteria',
        )
    )
    write_prd_json_artifact(analysis.document.title, analysis.document.created_at, 'requirements.json', requirements_payload)


def sync_testcase_generation_task_artifacts(task) -> None:
    write_prd_text_artifact(task.title, task.created_at, 'requirement_text.txt', task.requirement_text)
    write_prd_text_artifact(task.title, task.created_at, 'generated_test_cases.md', task.generated_test_cases)
    write_prd_text_artifact(task.title, task.created_at, 'review_feedback.md', task.review_feedback)
    write_prd_text_artifact(task.title, task.created_at, 'final_test_cases.md', task.final_test_cases)
    write_prd_text_artifact(task.title, task.created_at, 'generation_log.txt', task.generation_log)
    write_prd_text_artifact(task.title, task.created_at, 'error_message.txt', task.error_message)

# 自定义上传路径处理函数
def requirement_docs_upload_path(instance, filename):
    """自定义上传路径，将需求文档存储在 Data/PRD/YYYYMMDD/需求文档名/ 子目录下。"""
    relative_dir = requirement_document_relative_dir(instance, filename)
    safe_filename = Path(str(filename or 'document')).name
    return f'{relative_dir}/{safe_filename}'

logger = get_logger(__name__)


class RequirementDocument(models.Model):
    """需求文档模型"""
    DOCUMENT_TYPE_CHOICES = [
        ('pdf', 'PDF文档'),
        ('docx', 'Word文档'),
        ('txt', '文本文档'),
        ('md', 'Markdown文档'),
    ]

    STATUS_CHOICES = [
        ('uploaded', '已上传'),
        ('analyzing', '分析中'),
        ('analyzed', '分析完成'),
        ('failed', '分析失败'),
    ]

    title = models.CharField(max_length=200, verbose_name='文档标题')
    file = models.FileField(upload_to=requirement_docs_upload_path, storage=requirement_docs_storage, verbose_name='文档文件')
    document_type = models.CharField(max_length=10, choices=DOCUMENT_TYPE_CHOICES, verbose_name='文档类型')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded', verbose_name='状态')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_documents',
                                    verbose_name='上传者')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='requirement_documents',
                                verbose_name='关联项目', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    file_size = models.PositiveIntegerField(verbose_name='文件大小(bytes)', null=True, blank=True)
    extracted_text = models.TextField(verbose_name='提取的文本内容', blank=True)

    class Meta:
        db_table = 'requirement_documents'
        verbose_name = '需求文档'
        verbose_name_plural = '需求文档'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sync_requirement_document_artifacts(self)


class RequirementAnalysis(models.Model):
    """需求分析记录"""
    document = models.OneToOneField(RequirementDocument, on_delete=models.CASCADE, related_name='analysis',
                                    verbose_name='关联文档')
    analysis_report = models.TextField(verbose_name='分析报告', blank=True)
    requirements_count = models.PositiveIntegerField(verbose_name='需求数量', default=0)
    analysis_time = models.FloatField(verbose_name='分析耗时(秒)', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'requirement_analyses'
        verbose_name = '需求分析'
        verbose_name_plural = '需求分析'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.document.title} - 分析报告"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sync_requirement_analysis_artifacts(self)


class BusinessRequirement(models.Model):
    """业务需求模型"""
    REQUIREMENT_TYPE_CHOICES = [
        ('functional', '功能需求'),
        ('performance', '性能需求'),
        ('security', '安全需求'),
        ('usability', '可用性需求'),
        ('interface', '接口需求'),
        ('other', '其他需求'),
    ]

    REQUIREMENT_LEVEL_CHOICES = [
        ('high', '高'),
        ('medium', '中'),
        ('low', '低'),
    ]

    analysis = models.ForeignKey(RequirementAnalysis, on_delete=models.CASCADE, related_name='requirements',
                                 verbose_name='关联分析')
    requirement_id = models.CharField(max_length=50, verbose_name='需求编号')
    requirement_name = models.CharField(max_length=200, verbose_name='需求名称')
    requirement_type = models.CharField(max_length=20, choices=REQUIREMENT_TYPE_CHOICES, verbose_name='需求类型')
    parent_requirement = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                                           verbose_name='父级需求')
    module = models.CharField(max_length=100, verbose_name='所属模块')
    requirement_level = models.CharField(max_length=10, choices=REQUIREMENT_LEVEL_CHOICES, verbose_name='需求级别')
    reviewer = models.CharField(max_length=50, verbose_name='评审人', default='admin')
    estimated_hours = models.PositiveIntegerField(verbose_name='预计工时', default=8)
    description = models.TextField(verbose_name='需求描述')
    acceptance_criteria = models.TextField(verbose_name='验收标准')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'business_requirements'
        verbose_name = '业务需求'
        verbose_name_plural = '业务需求'
        ordering = ['-created_at']
        unique_together = ['analysis', 'requirement_id']

    def __str__(self):
        return f"{self.requirement_id} - {self.requirement_name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sync_business_requirements_artifact(self.analysis)


class GeneratedTestCase(models.Model):
    """生成的测试用例模型"""
    PRIORITY_CHOICES = [
        ('P0', '最高优先级'),
        ('P1', '高优先级'),
        ('P2', '中优先级'),
        ('P3', '低优先级'),
    ]

    STATUS_CHOICES = [
        ('generated', '已生成'),
        ('reviewing', '评审中'),
        ('reviewed', '已评审'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('adopted', '已采纳'),
        ('discarded', '已弃用'),
    ]

    requirement = models.ForeignKey(BusinessRequirement, on_delete=models.CASCADE, related_name='test_cases',
                                    verbose_name='关联需求')
    case_id = models.CharField(max_length=50, verbose_name='用例编号')
    title = models.CharField(max_length=300, verbose_name='用例标题')
    priority = models.CharField(max_length=5, choices=PRIORITY_CHOICES, verbose_name='优先级')
    precondition = models.TextField(verbose_name='前置条件')
    test_steps = models.TextField(verbose_name='测试步骤')
    expected_result = models.TextField(verbose_name='预期结果')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='generated', verbose_name='状态')
    generated_by_ai = models.CharField(max_length=50, verbose_name='生成AI模型', default='AI-A')
    reviewed_by_ai = models.CharField(max_length=50, verbose_name='评审AI模型', null=True, blank=True)
    review_comments = models.TextField(verbose_name='评审意见', blank=True)
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'generated_test_cases'
        verbose_name = '生成的测试用例'
        verbose_name_plural = '生成的测试用例'
        ordering = ['-created_at']
        unique_together = ['requirement', 'case_id']

    def __str__(self):
        return f"{self.case_id} - {self.title[:50]}"


class AnalysisTask(models.Model):
    """分析任务模型"""
    TASK_TYPE_CHOICES = [
        ('requirement_analysis', '需求分析'),
        ('testcase_generation', '测试用例生成'),
        ('testcase_review', '测试用例评审'),
    ]

    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('running', '运行中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    ]

    task_id = models.CharField(max_length=100, unique=True, verbose_name='任务ID')
    task_type = models.CharField(max_length=30, choices=TASK_TYPE_CHOICES, verbose_name='任务类型')
    document = models.ForeignKey(RequirementDocument, on_delete=models.CASCADE, related_name='tasks',
                                 verbose_name='关联文档')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    progress = models.PositiveIntegerField(default=0, verbose_name='进度百分比')
    result = models.JSONField(verbose_name='任务结果', null=True, blank=True)
    error_message = models.TextField(verbose_name='错误信息', blank=True)
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')

    class Meta:
        db_table = 'analysis_tasks'
        verbose_name = '分析任务'
        verbose_name_plural = '分析任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task_id} - {self.get_task_type_display()}"


class AIModelConfig(models.Model):
    """AI模型配置模型"""
    MODEL_CHOICES = [
        ('deepseek', 'DeepSeek'),
        ('qwen', '通义千问'),
        ('gemini', 'Google Gemini'),
        ('siliconflow', '硅基流动'),
        ('zhipu', '智谱'),
        ('other', '其他'),
    ]

    ROLE_CHOICES = [
        ('writer', '测试用例编写专家'),
        ('reviewer', '测试评审专家'),
        ('browser_use_text', 'Browser Use - 文本模式'),
        ('browser_use_vision', 'Browser Use - 视觉模式'),
        ('hermes_agent', 'Hermes Agent'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称')
    model_type = models.CharField(max_length=20, choices=MODEL_CHOICES, verbose_name='模型类型')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name='角色')
    api_key = models.CharField(max_length=200, verbose_name='API Key', blank=True, null=True)
    base_url = models.URLField(verbose_name='API Base URL')
    model_name = models.CharField(max_length=100, verbose_name='模型名称')
    max_tokens = models.IntegerField(default=4096, verbose_name='最大Token数')
    temperature = models.FloatField(default=0.7, verbose_name='温度参数')
    top_p = models.FloatField(default=0.9, verbose_name='Top P参数')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'ai_model_config'
        verbose_name = 'AI模型配置'
        verbose_name_plural = 'AI模型配置'
        # 移除 unique_together 约束，允许同一个 role 有多个配置
        # 在应用层面通过代码控制：每个 role 只能有一个 is_active=True 的配置

    def __str__(self):
        return f"{self.get_model_type_display()} - {self.get_role_display()}"

    @classmethod
    def get_active_config(cls, model_type: str, role: str):
        """获取活跃的配置"""
        return cls.objects.filter(
            model_type=model_type,
            role=role,
            is_active=True
        ).first()


class PromptConfig(models.Model):
    """提示词配置模型"""
    PROMPT_CHOICES = [
        ('writer', '用例编写提示词'),
        ('reviewer', '用例评审提示词'),
        ('browser_use_text', 'AI智能模式-文本提示词'),
        ('browser_use_vision', 'AI智能模式-视觉提示词'),
        ('hermes_agent', 'Hermes Agent提示词'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称')
    prompt_type = models.CharField(max_length=20, choices=PROMPT_CHOICES, verbose_name='提示词类型')
    content = models.TextField(verbose_name='提示词内容')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'prompt_config'
        verbose_name = '提示词配置'
        verbose_name_plural = '提示词配置'

    def __str__(self):
        return f"{self.get_prompt_type_display()} - {self.name}"

    @classmethod
    def get_active_config(cls, prompt_type: str):
        """获取活跃的提示词配置"""
        return cls.objects.filter(
            prompt_type=prompt_type,
            is_active=True
        ).first()


class GenerationConfig(models.Model):
    """生成行为配置模型"""
    OUTPUT_MODE_CHOICES = [
        ('stream', '实时流式输出'),
        ('complete', '完整输出'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称', default='默认生成配置')
    default_output_mode = models.CharField(
        max_length=10,
        choices=OUTPUT_MODE_CHOICES,
        default='stream',
        verbose_name='默认输出模式',
        help_text='测试用例生成的默认输出方式'
    )

    # 扩展配置字段
    enable_auto_review = models.BooleanField(
        default=True,
        verbose_name='启用AI评审和改进',
        help_text='生成完成后自动进行AI评审，并根据评审意见改进测试用例'
    )
    review_timeout = models.IntegerField(
        default=120,
        verbose_name='评审和改进超时时间（秒）',
        help_text='AI评审和改进的最大等待时间（总时长）'
    )

    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'generation_config'
        verbose_name = '生成行为配置'
        verbose_name_plural = '生成行为配置'

    def __str__(self):
        return self.name

    @classmethod
    def get_active_config(cls):
        """获取活跃的生成配置"""
        return cls.objects.filter(is_active=True).first()


class TestCaseGenerationTask(models.Model):
    """测试用例生成任务模型"""
    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('generating', '生成中'),
        ('reviewing', '评审中'),
        ('revising', '改进中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]

    OUTPUT_MODE_CHOICES = [
        ('stream', '实时流式输出'),
        ('complete', '完整输出'),
    ]

    task_id = models.CharField(max_length=50, unique=True, verbose_name='任务ID')
    title = models.CharField(max_length=200, verbose_name='任务标题')
    requirement_text = models.TextField(verbose_name='需求描述')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    progress = models.IntegerField(default=0, verbose_name='进度百分比')

    # 流式输出配置
    output_mode = models.CharField(
        max_length=10,
        choices=OUTPUT_MODE_CHOICES,
        default='stream',
        verbose_name='输出模式'
    )

    # 流式缓冲区和状态跟踪
    stream_buffer = models.TextField(blank=True, verbose_name='流式输出缓冲区')
    stream_position = models.IntegerField(default=0, verbose_name='流式输出位置')
    last_stream_update = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后流式更新时间'
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generation_tasks',
        verbose_name='关联项目'
    )

    # 配置参数
    writer_model_config = models.ForeignKey(
        AIModelConfig, on_delete=models.SET_NULL, null=True,
        related_name='writer_tasks', verbose_name='编写模型配置'
    )
    reviewer_model_config = models.ForeignKey(
        AIModelConfig, on_delete=models.SET_NULL, null=True,
        related_name='reviewer_tasks', verbose_name='评审模型配置'
    )
    writer_prompt_config = models.ForeignKey(
        PromptConfig, on_delete=models.SET_NULL, null=True,
        related_name='writer_tasks', verbose_name='编写提示词配置'
    )
    reviewer_prompt_config = models.ForeignKey(
        PromptConfig, on_delete=models.SET_NULL, null=True,
        related_name='reviewer_tasks', verbose_name='评审提示词配置'
    )

    # 生成结果
    generated_test_cases = models.TextField(blank=True, verbose_name='生成的测试用例')
    review_feedback = models.TextField(blank=True, verbose_name='评审反馈')
    final_test_cases = models.TextField(blank=True, verbose_name='最终测试用例')

    # 元数据
    generation_log = models.TextField(blank=True, verbose_name='生成日志')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    is_saved_to_records = models.BooleanField(default=False, verbose_name='是否已保存到记录')
    saved_at = models.DateTimeField(null=True, blank=True, verbose_name='保存到记录时间')

    class Meta:
        db_table = 'testcase_generation_task'
        verbose_name = '测试用例生成任务'
        verbose_name_plural = '测试用例生成任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sync_testcase_generation_task_artifacts(self)


class AIModelService:
    """AI模型服务类"""

    @staticmethod
    def _load_task_with_related(task_id: int) -> TestCaseGenerationTask:
        return TestCaseGenerationTask.objects.select_related(
            'writer_model_config',
            'reviewer_model_config',
            'writer_prompt_config',
            'reviewer_prompt_config',
        ).get(id=task_id)

    @staticmethod
    async def _get_task_with_related(task: TestCaseGenerationTask) -> TestCaseGenerationTask:
        return await sync_to_async(AIModelService._load_task_with_related)(task.id)

    @staticmethod
    def _build_writer_user_message(requirement_text: str) -> str:
        return (
            f"请根据以下需求文档直接输出测试用例结果，不要输出分析过程、思考过程、推理步骤、说明文字或开场白。\n\n"
            f"【生成指令】\n"
            f"1. 数量原则：请根据需求内容的实际复杂度，自动决定生成用例的数量。务必覆盖所有功能点、异常场景和边界条件，不设数量上限，应写尽写。\n"
            f"2. 深度遍历策略：\n"
            f"   - 请按文档结构逐章节分析，不要遗漏末尾的功能点。\n"
            f"   - 对每个功能点，必须设计1个正常场景和2-3个异常或边界场景。\n"
            f"3. 拒绝合并：严禁将多个验证点合并在一条用例中。例如“验证输入框”应拆分为“输入为空”“输入超长”“输入特殊字符”等独立用例。\n"
            f"4. 场景扩展库：\n"
            f"   - 数据完整性（必填项、默认值、数据类型）\n"
            f"   - 业务逻辑约束（状态流转、权限控制、重复操作）\n"
            f"   - 外部接口异常（超时、断网、返回错误）\n"
            f"   - UI交互体验（提示文案、跳转逻辑、防误触）\n"
            f"5. 输出顺序要求：\n"
            f"   - 必须按用例编号从小到大的顺序输出。\n"
            f"   - 绝对不能跳号、重复或乱序输出。\n"
            f"   - 编号必须连续，中间不能有遗漏。\n"
            f"6. 特殊字符处理：如果在表格内容中出现管道符 |，请使用 HTML 实体 &#124; 代替，不要使用反斜杠转义。\n"
            f"7. 格式约束：\n"
            f"   - 绝对禁止输出任何思考过程或类似 Here's a thinking process、分析如下、推理过程 等内容。\n"
            f"   - 绝对禁止输出 Markdown 加粗语法。\n"
            f"   - 只允许输出最终测试用例 Markdown 表格。\n"
            f"   - 不要输出表格之外的任何额外文本。\n\n"
            f"【需求文档内容】\n{requirement_text}"
        )

    @staticmethod
    def _build_request_payload(
            config: AIModelConfig,
            messages: List[Dict[str, str]],
            max_tokens: int,
            stream: bool,
            response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            'model': config.model_name,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': config.temperature,
            'top_p': config.top_p,
            'stream': stream,
        }

        if config.model_type == 'qwen':
            data['chat_template_kwargs'] = {'enable_thinking': False}

        if response_format is not None and not stream:
            data['response_format'] = response_format

        return data

    @staticmethod
    def _build_chat_completions_url(config: AIModelConfig) -> str:
        base_url = config.base_url.rstrip('/')
        if base_url.endswith('/chat/completions'):
            return base_url

        if config.model_type in {'gemini', 'google_gemini'}:
            return f'{base_url}/chat/completions'

        version_match = re.search(r'/v(\d+)/?$', base_url)
        if version_match:
            return f'{base_url}/chat/completions'
        return f'{base_url}/v1/chat/completions'

    @staticmethod
    async def call_openai_compatible_api(
            config: AIModelConfig,
            messages: List[Dict[str, str]],
            max_tokens: int = None,
            response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        调用OpenAI兼容格式的API

        Args:
            config: AI模型配置
            messages: 消息列表
            max_tokens: 可选的最大token数，如果不指定则使用config.max_tokens

        Returns:
            API响应字典
        """
        headers = {
            'Authorization': f'Bearer {config.api_key}',
            'Content-Type': 'application/json'
        }

        # 使用传入的max_tokens或默认使用config.max_tokens
        actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens

        data = AIModelService._build_request_payload(
            config=config,
            messages=messages,
            max_tokens=actual_max_tokens,
            stream=False,
            response_format=response_format,
        )

        url = AIModelService._build_chat_completions_url(config)

        logger.info(f"=== API调用详情 ===")
        logger.info(f"原始base_url: {config.base_url}")
        logger.info(f"最终请求URL: {url}")
        logger.info(f"模型名称: {config.model_name}")
        logger.info(f"请求参数: max_tokens={actual_max_tokens}, temperature={config.temperature}, top_p={config.top_p}")

        try:
            # 增加HTTP超时时间到900秒（15分钟），支持大文档生成
            # 禁用HTTP/2，使用HTTP/1.1以提高兼容性
            # 显式设置所有超时参数，避免默认的连接超时导致请求失败
            timeout_config = httpx.Timeout(
                connect=60.0,  # 连接超时：60秒
                read=900.0,  # 读取超时：900秒（15分钟）
                write=60.0,  # 写入超时：60秒
                pool=60.0  # 连接池超时：60秒
            )
            async with httpx.AsyncClient(timeout=timeout_config, http2=False) as client:
                logger.info(f"发送POST请求到: {url}")
                response = await client.post(
                    url,
                    headers=headers,
                    json=data
                )

                logger.info(f"收到响应: status_code={response.status_code}")

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"API调用返回错误: Status={response.status_code}, Body={error_detail}")

                response.raise_for_status()
                result = response.json()
                logger.info(f"API调用成功，响应内容: {str(result)[:200]}...")
                return result
        except httpx.HTTPStatusError as e:
            provider_name = config.get_model_type_display()
            error_msg = f"{provider_name} API返回错误 {e.response.status_code}: {e.response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except httpx.TimeoutException as e:
            provider_name = config.get_model_type_display()
            logger.error(f"{provider_name} API请求超时: {repr(e)}")
            raise Exception(f"{provider_name} API请求超时，请稍后再试或检查网络连接")
        except Exception as e:
            provider_name = config.get_model_type_display()
            # Use repr(e) to capture the full exception type and message, especially if str(e) is empty
            logger.error(f"{provider_name} API调用失败: {repr(e)}")
            raise Exception(f"{provider_name} API调用失败: {str(e) or repr(e)}")

    @staticmethod
    async def call_deepseek_api(config: AIModelConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """调用DeepSeek API (兼容OpenAI格式)"""
        return await AIModelService.call_openai_compatible_api(config, messages)

    @staticmethod
    async def call_qwen_api(config: AIModelConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """调用千问API (兼容OpenAI格式)"""
        return await AIModelService.call_openai_compatible_api(config, messages)

    @staticmethod
    async def call_openai_compatible_api_stream(
            config: AIModelConfig,
            messages: List[Dict[str, str]],
            callback=None,
            max_tokens: int = None
    ) -> AsyncIterator[str]:
        """
        流式调用OpenAI兼容格式的API，支持自动续写
        """
        headers = {
            'Authorization': f'Bearer {config.api_key}',
            'Content-Type': 'application/json'
        }

        # 使用传入的max_tokens或默认使用config.max_tokens
        actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens

        url = AIModelService._build_chat_completions_url(config)

        # 续写控制
        current_messages = list(messages)  # 浅拷贝
        continuation_count = 0
        MAX_CONTINUATIONS = 5  # 最大续写次数，防止死循环

        while continuation_count <= MAX_CONTINUATIONS:
            data = AIModelService._build_request_payload(
                config=config,
                messages=current_messages,
                max_tokens=actual_max_tokens,
                stream=True,
            )

            logger.info(f"发起流式请求 (第{continuation_count + 1}次), messages数量: {len(current_messages)}")

            chunk_content_buffer = ""  # 本次请求生成的完整内容缓存
            finish_reason = None

            try:
                # 显式设置所有超时参数
                timeout_config = httpx.Timeout(
                    connect=60.0,  # 连接超时：60秒
                    read=900.0,  # 读取超时：900秒（15分钟）
                    write=60.0,  # 写入超时：60秒
                    pool=60.0  # 连接池超时：60秒
                )
                async with httpx.AsyncClient(timeout=timeout_config, http2=False) as client:
                    async with client.stream('POST', url, headers=headers, json=data) as response:
                        if response.status_code != 200:
                            error_detail = await response.aread()
                            error_msg = error_detail.decode('utf-8')
                            logger.error(f"流式API调用返回错误: Status={response.status_code}, Body={error_msg}")
                            response.raise_for_status()
                        
                        line_count = 0
                        async for line in response.aiter_lines():
                            line_count += 1
                            if line_count <= 5:
                                logger.info(f"原始响应行 {line_count}: {line[:200]}")
                            
                            if not line.strip():
                                continue

                            if line.startswith('data:'):
                                if line.startswith('data: '):
                                    data_str = line[6:]
                                else:
                                    data_str = line[5:]
                                
                                if data_str.strip() == '[DONE]':
                                    logger.info("收到 [DONE] 信号")
                                    break

                                try:
                                    chunk_data = json.loads(data_str)
                                    
                                    if 'status' in chunk_data and chunk_data.get('status') != '200':
                                        error_msg = chunk_data.get('msg', 'Unknown error')
                                        logger.error(f"API返回错误: status={chunk_data.get('status')}, msg={error_msg}")
                                        raise ValueError(f"API错误: {error_msg}")
                                    
                                    if 'error' in chunk_data:
                                        error_info = chunk_data['error']
                                        error_msg = error_info.get('message', str(error_info)) if isinstance(error_info, dict) else str(error_info)
                                        logger.error(f"API返回错误: {error_msg}")
                                        raise ValueError(f"API错误: {error_msg}")
                                    
                                    if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                        choice = chunk_data['choices'][0]
                                        delta = choice.get('delta', {})
                                        finish_reason = choice.get('finish_reason', None)
                                        content = delta.get('content', '')

                                        if content:
                                            chunk_content_buffer += content
                                            if callback:
                                                await callback(content)
                                            yield content

                                        if finish_reason:
                                            logger.info(f"收到 finish_reason: {finish_reason}")

                                except json.JSONDecodeError as e:
                                    logger.warning(f"JSON解析失败: {e}, data_str={data_str[:100]}")
                                    continue
                            else:
                                logger.debug(f"非data行: {line[:100]}")

                # 本次请求结束
                # 检查 finish_reason
                if finish_reason == 'length':
                    logger.warning(
                        f"检测到生成被截断 (finish_reason='length')，准备自动续写。当前已续写 {continuation_count} 次。")
                    continuation_count += 1

                    # 将本次生成的内容作为 assistant 回复加入历史
                    # 注意：如果之前已经有assistant消息，需要追加内容而不是新增消息
                    if current_messages[-1]['role'] == 'assistant':
                        current_messages[-1]['content'] += chunk_content_buffer
                    else:
                        current_messages.append({"role": "assistant", "content": chunk_content_buffer})

                    # 只有当上一条不是user的续写指令时，才添加新的user指令
                    # 防止多次续写时堆叠重复的 user 指令
                    if current_messages[-1]['role'] != 'user':
                        current_messages.append(
                            {"role": "user", "content": "请继续输出剩余的内容，不要重复已输出的部分，紧接着上文继续。"})

                    # 发送换行符以分隔续写内容（可选，视模型而定，通常不需要，但为了保险）
                    # yield "\n"
                    continue
                else:
                    logger.info(f"流式生成正常结束 (finish_reason={finish_reason})")
                    break

            except Exception as e:
                logger.error(f"流式请求异常: {e}")
                # 如果是超时或其他网络错误，可能需要重试机制，这里暂时直接抛出
                raise e

    @staticmethod
    async def generate_test_cases(task: TestCaseGenerationTask) -> str:
        """生成测试用例"""
        task = await AIModelService._get_task_with_related(task)
        writer_prompt = task.writer_prompt_config.content
        user_message = AIModelService._build_writer_user_message(task.requirement_text)

        messages = [
            {"role": "system", "content": writer_prompt},
            {"role": "user", "content": user_message}
        ]

        # 所有支持的模型都使用兼容OpenAI的接口
        # 使用配置的max_tokens，不硬编码限制
        response = await AIModelService.call_openai_compatible_api(
            task.writer_model_config,
            messages
            # 不再硬编码max_tokens，使用配置文件中的值（如32000）
        )

        return response['choices'][0]['message']['content']

    @staticmethod
    async def review_test_cases(task: TestCaseGenerationTask, test_cases: str) -> str:
        """评审测试用例"""
        try:
            task = await AIModelService._get_task_with_related(task)
            reviewer_prompt = task.reviewer_prompt_config.content

            # 增强的评审指令
            user_message = (
                f"请对以下生成的测试用例进行严格的专家级评审。\n\n"
                f"【评审重点】\n"
                f"1. **覆盖率漏洞**：请仔细比对用例集是否覆盖了常见的异常场景（如断网、超时、数据冲突）和边界条件。\n"
                f"2. **逻辑严密性**：检查预期结果是否具体、可验证（例如'提示错误'是不够的，需说明具体错误码或文案）。\n"
                f"3. **冗余检查**：指出是否有重复或无效的用例。\n\n"
                f"【待评审用例】\n{test_cases}\n\n"
                f"【输出格式要求】\n"
                f"请输出一份包含评分、问题列表和改进建议的详细评审报告。"
                f"**重要**：输出格式要求紧凑，不要在段落之间添加多余的空行，每个问题点之间用单空行分隔即可，用例展示仍为markdown形式。"
            )

            messages = [
                {"role": "system", "content": reviewer_prompt},
                {"role": "user", "content": user_message}
            ]

            # 所有支持的模型都使用兼容OpenAI的接口
            response = await AIModelService.call_openai_compatible_api(task.reviewer_model_config, messages)

            return response['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"评审测试用例时出错: {e}")
            # 返回一个默认的评审结果
            return f"评审过程中出现错误: {str(e)}\n\n建议：测试用例结构完整，可以使用。"

    @staticmethod
    async def generate_test_cases_stream(
            task: TestCaseGenerationTask,
            callback=None
    ) -> str:
        """
        流式生成测试用例

        Args:
            task: 生成任务对象
            callback: 可选的回调函数，每收到一个chunk就调用，用于实时保存到数据库

        Returns:
            str: 完整的测试用例内容
        """
        task = await AIModelService._get_task_with_related(task)
        writer_prompt = task.writer_prompt_config.content
        user_message = AIModelService._build_writer_user_message(task.requirement_text)

        messages = [
            {"role": "system", "content": writer_prompt},
            {"role": "user", "content": user_message}
        ]

        # 记录请求信息
        logger.info(f"流式生成测试用例 - 模型: {task.writer_model_config.model_name}, base_url: {task.writer_model_config.base_url}")
        logger.info(f"流式生成测试用例 - 需求文本长度: {len(task.requirement_text)}, max_tokens: {task.writer_model_config.max_tokens}")

        # 流式调用API，确保正确关闭生成器
        # 使用配置的max_tokens，不硬编码限制
        generator = AIModelService.call_openai_compatible_api_stream(
            task.writer_model_config,
            messages,
            callback=callback
            # 不再硬编码max_tokens，使用配置文件中的值（如32000）
        )

        full_content = ""
        chunk_count = 0
        try:
            async for chunk in generator:
                full_content += chunk
                chunk_count += 1
        except Exception as e:
            logger.error(f"流式生成测试用例时出错: {e}")
            raise
        finally:
            # 确保生成器被正确关闭
            try:
                await generator.aclose()
            except Exception as close_error:
                logger.warning(f"关闭generator时出错: {close_error}")

        logger.info(f"流式生成完成: 总chunk数={chunk_count}, 总字符数={len(full_content)}")

        # 如果生成内容为空，记录警告
        if not full_content:
            logger.warning(f"流式生成返回空内容! chunk数={chunk_count}, 检查API配置和网络连接")

        # 统计生成的用例数量
        case_count = full_content.count('TC-') + full_content.count('TEST-') + full_content.count('测试用例')
        logger.info(f"生成用例统计: 约检测到{case_count}个用例编号标记")

        return full_content

    @staticmethod
    async def review_test_cases_stream(
            task: TestCaseGenerationTask,
            test_cases: str,
            callback=None
    ) -> str:
        """
        流式评审测试用例

        Args:
            task: 生成任务对象
            test_cases: 待评审的测试用例
            callback: 可选的回调函数，每收到一个chunk就调用

        Returns:
            str: 完整的评审反馈
        """
        task = await AIModelService._get_task_with_related(task)
        reviewer_prompt = task.reviewer_prompt_config.content

        # 增强的评审指令
        user_message = (
            f"请对以下生成的测试用例进行严格的专家级评审。\n\n"
            f"【评审重点】\n"
            f"1. **覆盖率漏洞**：请仔细比对用例集是否覆盖了常见的异常场景（如断网、超时、数据冲突）和边界条件。\n"
            f"2. **逻辑严密性**：检查预期结果是否具体、可验证（例如'提示错误'是不够的，需说明具体错误码或文案）。\n"
            f"3. **冗余检查**：指出是否有重复或无效的用例。\n\n"
            f"【待评审用例】\n{test_cases}\n\n"
            f"【输出格式要求】\n"
            f"请输出一份包含评分、问题列表和改进建议的详细评审报告。"
            f"**重要**：输出格式要求紧凑，不要在段落之间添加多余的空行，每个问题点之间用单空行分隔即可，用例展示仍为markdown形式。"
        )

        messages = [
            {"role": "system", "content": reviewer_prompt},
            {"role": "user", "content": user_message}
        ]

        # 流式调用API，确保正确关闭生成器
        generator = AIModelService.call_openai_compatible_api_stream(
            task.reviewer_model_config,
            messages,
            callback=callback
        )

        full_content = ""
        chunk_count = 0
        try:
            async for chunk in generator:
                full_content += chunk
                chunk_count += 1
        except Exception as e:
            logger.error(f"流式评审测试用例时出错: {e}")
            return f"评审过程中出现错误: {str(e)}\n\n建议：测试用例结构完整，可以使用。"
        finally:
            # 确保生成器被正确关闭
            try:
                await generator.aclose()
            except Exception as close_error:
                logger.warning(f"关闭generator时出错: {close_error}")

        logger.info(f"流式评审完成: 总chunk数={chunk_count}, 总字符数={len(full_content)}")
        return full_content

    @staticmethod
    async def revise_test_cases_based_on_review(
            task: TestCaseGenerationTask,
            original_test_cases: str,
            review_feedback: str,
            callback=None
    ) -> str:
        """
        根据评审意见改进测试用例

        Args:
            task: 生成任务对象
            original_test_cases: 原始生成的测试用例
            review_feedback: AI评审意见
            callback: 可选的回调函数，每收到一个chunk就调用

        Returns:
            str: 改进后的测试用例
        """
        task = await AIModelService._get_task_with_related(task)
        writer_prompt = task.writer_prompt_config.content

        # 构建改进指令
        user_message = (
            f"请根据以下专家评审意见，改进和完善测试用例。\n\n"
            f"【原始测试用例】\n{original_test_cases}\n\n"
            f"【评审意见】\n{review_feedback}\n\n"
            f"【改进要求】\n"
            f"1. 严格根据评审意见指出的问题进行修改\n"
            f"2. 补充缺失的测试场景\n"
            f"3. 修正不合理的预期结果\n"
            f"4. 删除冗余的测试用例\n"
            f"5. 保持测试用例的格式规范\n"
            f"6. **⚠️ 输出顺序要求（必须严格执行）**：\n"
            f"   - **必须按用例编号从小到大的顺序输出**（如：001, 002, 003...或LOGIN_001, LOGIN_002, LOGIN_003...）\n"
            f"   - **绝对不能跳号、重复或乱序输出**\n"
            f"   - **编号必须连续，中间不能有遗漏**\n"
            f"   - **所有用例必须一次性完整输出，不能中断**\n"
            f"7. **必须输出完整**：请确保输出所有改进后的测试用例，不要因为篇幅原因省略任何用例，"
            f"即使是第30条、第40条甚至更多的用例，也必须完整输出。\n"
            f"8. **测试用例编号规则**：新增的测试用例必须按照原有编号规则继续编号（例如原最后一个用例是TC-003，新增的第一个用例应该是TC-004），"
            f"绝不能使用'新增'、'用例1'等作为编号，必须是正式的测试用例编号。\n"
            rf"9. **⚠️ 特殊字符处理（关键）**：\n"
            rf"   - **如果在表格内容（如操作步骤、预期结果）中出现管道符 '|'，请使用HTML实体 '&#124;' 代替**。\n"
            rf"   - **绝对不要使用反斜杠转义（如 '\|'），这会导致输出混乱**。\n"
            rf"   - 示例：应输入 'a&#124;b' 而不是 'a|b' 或 'a\|b'。\n"
            f"10. **⚠️ 格式禁止事项（必须严格执行）**：\n"
            f"   - **绝对禁止使用 Markdown 加粗语法（即 **文字** 格式）**\n"
            f"   - 测试用例标题、步骤、预期结果等内容都不要加粗\n"
            f"   - 正确示例：验证回车键触发登录\n"
            f"   - 错误示例：**验证回车键触发登录**\n\n"
            f"请直接输出改进后的完整测试用例，不要包含任何说明性文字。"
        )

        messages = [
            {"role": "system", "content": writer_prompt},
            {"role": "user", "content": user_message}
        ]

        # 流式调用API，确保正确关闭生成器
        # 使用配置的max_tokens，不硬编码限制
        generator = AIModelService.call_openai_compatible_api_stream(
            task.writer_model_config,
            messages,
            callback=callback
            # 不再硬编码max_tokens，使用配置文件中的值（如32000）
        )

        full_content = ""
        chunk_count = 0
        try:
            async for chunk in generator:
                full_content += chunk
                chunk_count += 1
        except Exception as e:
            logger.error(f"根据评审意见改进测试用例时出错: {e}")
            # 改进失败时返回原始用例
            return original_test_cases
        finally:
            # 确保生成器被正确关闭
            try:
                await generator.aclose()
            except Exception as close_error:
                logger.warning(f"关闭generator时出错: {close_error}")

        logger.info(f"流式改进完成: 总chunk数={chunk_count}, 总字符数={len(full_content)}")

        # 统计改进后的用例数量
        case_count = full_content.count('TC-') + full_content.count('**TC-') + full_content.count('测试用例')
        logger.info(f"改进用例统计: 约检测到{case_count}个用例编号标记")

        return full_content

    @staticmethod
    def sort_test_cases_by_id(test_cases_content: str) -> str:
        """
        按照测试用例编号排序测试用例内容

        Args:
            test_cases_content: 测试用例内容（字符串）

        Returns:
            str: 排序后的测试用例内容
        """
        if not test_cases_content:
            return test_cases_content

        import re

        # 按行分割内容
        lines = test_cases_content.split('\n')

        # 识别用例块：每个用例从包含编号的行开始
        # 支持多种编号格式：TC-001, TC001, TEST-001, 测试用例1, 1. 等
        case_pattern = re.compile(r'^(#{1,6}\s+)?(?:TC[-_]?\d+|TEST[-_]?\d+|测试用例\d+|\d+[\.\、]\s*[:：]?\s*\S+)',
                                  re.IGNORECASE | re.MULTILINE)

        # 找到所有用例块的起始位置
        case_starts = []
        for i, line in enumerate(lines):
            if case_pattern.match(line):
                case_starts.append(i)

        # 如果没有找到编号，返回原内容
        if len(case_starts) < 2:
            logger.info(f"未检测到足够的用例编号（只找到{len(case_starts)}个），保持原顺序")
            return test_cases_content

        # 提取每个用例块
        case_blocks = []
        for i in range(len(case_starts)):
            start = case_starts[i]
            # 下一个用例的开始位置，或者文件末尾
            end = case_starts[i + 1] if i + 1 < len(case_starts) else len(lines)
            block_lines = lines[start:end]
            block_content = '\n'.join(block_lines)
            case_blocks.append({
                'start': start,
                'content': block_content,
                'first_line': block_lines[0] if block_lines else ''
            })

        # 提取编号用于排序
        def extract_case_id(block):
            first_line = block['first_line']
            # 尝试匹配各种编号格式
            # TC-001, TC001, TEST-001, 测试用例1, 1. xxx 等
            match = re.search(r'(?:TC[-_]?|TEST[-_]?|测试用例)?(\d+)', first_line, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return 0

        # 按编号排序
        try:
            case_blocks.sort(key=extract_case_id)
            logger.info(f"成功对{len(case_blocks)}个测试用例按编号排序")
        except Exception as e:
            logger.warning(f"排序失败: {e}，保持原顺序")

        # 重新组合内容
        sorted_content = '\n'.join([block['content'] for block in case_blocks])

        return sorted_content

    @staticmethod
    def fix_incomplete_last_case(test_cases_content: str) -> str:
        """
        检测并修复不完整的最后一条测试用例

        Args:
            test_cases_content: 测试用例内容

        Returns:
            str: 修复后的测试用例内容
        """
        if not test_cases_content:
            return test_cases_content

        lines = test_cases_content.split('\n')

        # 检查最后几行，找到最后一个表格行
        table_lines = []
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith('|') and line.endswith('|'):
                table_lines.insert(0, (i, line))
                # 只检查最后10行
                if len(table_lines) >= 10:
                    break

        if not table_lines:
            return test_cases_content

        # 检查最后一个表格行是否完整（应该有7个|，即7列）
        last_line_index, last_line = table_lines[-1]
        column_count = last_line.count('|')

        # 正常的表格应该有7个|（开头+结尾+5个分隔符）
        if column_count < 7:
            logger.warning(f"检测到最后一条用例不完整: 只有{column_count}列，应该是7列")
            # 删除不完整的最后一条用例
            # 找到完整的上一条用例
            for i in range(len(table_lines) - 2, -1, -1):
                prev_index, prev_line = table_lines[i]
                if prev_line.count('|') >= 7:
                    # 截断到上一条完整用例的位置
                    fixed_content = '\n'.join(lines[:prev_index + 1])
                    logger.info(f"已删除不完整的最后一条用例，保留了{prev_index + 1}行")
                    return fixed_content

            # 如果找不到完整的上一条，直接删除最后5行
            fixed_content = '\n'.join(lines[:-5])
            logger.info(f"删除最后5行不完整的内容")
            return fixed_content

        return test_cases_content

    @staticmethod
    def renumber_test_cases(test_cases_content: str) -> str:
        """
        重新编号测试用例，使其编号连续

        Args:
            test_cases_content: 测试用例内容（字符串）

        Returns:
            str: 重新编号后的测试用例内容
        """
        if not test_cases_content:
            return test_cases_content

        import re

        lines = test_cases_content.split('\n')

        # 找到表格分隔线（支持多种格式：| --- |, |:---|, |---|）
        separator_line = None
        separator_index = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('|') and (':' in stripped or '---' in stripped):
                # 检查是否是分隔线（包含 --- 或 :---）
                if re.search(r'\|[\s]*:?-+:?[\s]*\|', stripped):
                    separator_line = line
                    separator_index = i
                    break

        if not separator_line:
            logger.warning("未找到表格分隔线，无法重新编号")
            return test_cases_content

        # 计算列数
        column_count = separator_line.count('|')

        # 找到第一个数据行（包含编号的行）
        first_data_index = -1
        for i in range(separator_index + 1, len(lines)):
            line = lines[i]
            if line.strip().startswith('|') and line.count('|') == column_count:
                first_data_index = i
                break

        if first_data_index == -1:
            logger.warning("未找到任何数据行")
            return test_cases_content

        # 从第一个数据行中提取编号格式
        first_line = lines[first_data_index]
        parts = first_line.split('|')
        if len(parts) < 2:
            logger.warning("无法解析第一列")
            return test_cases_content

        # 获取第一列的编号（例如：IMMSG001, LOGIN_001, TC-001）
        first_id = parts[1].strip()

        # 提取编号格式前缀和分隔符（例如：IMMSG, LOGIN, TC）
        # 支持多种格式：IMMSG001, LOGIN_001, TC-001
        id_match = re.match(r'^([A-Z]+)([-_]?)(\d+)$', first_id)
        if not id_match:
            logger.warning(f"无法识别编号格式: {first_id}")
            return test_cases_content

        prefix = id_match.group(1)  # 例如：IMMSG, LOGIN, TC
        separator = id_match.group(2)  # 分隔符：'', '_', '-'
        total_cases = 0

        # 重新编号所有数据行
        result_lines = lines[:first_data_index]
        i = first_data_index

        while i < len(lines):
            line = lines[i]

            # 检查是否是数据行
            if not line.strip().startswith('|'):
                # 不是表格行，添加并继续
                result_lines.append(line)
                i += 1
                continue

            # 检查列数是否正确
            if line.count('|') != column_count:
                # 列数不对，可能是空行或其他内容
                result_lines.append(line)
                i += 1
                continue

            # 这是一个数据行，重新编号
            total_cases += 1
            new_id = f"{prefix}{separator}{total_cases:03d}"  # 格式：IMMSG001, LOGIN_001, TC-001

            # 替换第一列的编号，保持原有格式
            parts = line.split('|')
            if len(parts) >= 2:
                # 保持第一列（空）和第二列（编号）之间的空格
                # 只替换编号部分
                parts[1] = f" {new_id} "
                new_line = '|'.join(parts)
                result_lines.append(new_line)

            i += 1

        renumbered_content = '\n'.join(result_lines)
        logger.info(f"重新编号完成: 共{total_cases}条测试用例，编号范围: {prefix}001-{prefix}{total_cases:03d}")

        return renumbered_content
