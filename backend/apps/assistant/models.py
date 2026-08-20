from django.db import models
from django.utils import timezone
from apps.users.models import User


class AgentModelConfig(models.Model):
    """OpenAI-compatible model settings dedicated to the AI Agent experience."""

    ROLE_CHOICES = [
        ('chat', 'Chat 模型'),
        ('agent', 'Agent 模型'),
        ('alpha_planner', 'Alpha Planner 模型'),
        ('alpha_reflection', 'Alpha Reflection 模型'),
    ]
    MODEL_TYPE_CHOICES = [
        ('openai', 'OpenAI'),
        ('azure_openai', 'Azure OpenAI'),
        ('anthropic', 'Anthropic Claude'),
        ('deepseek', 'DeepSeek'),
        ('qwen', '通义千问'),
        ('gemini', 'Google Gemini'),
        ('moonshot', 'Moonshot / Kimi'),
        ('baichuan', '百川智能'),
        ('minimax', 'MiniMax'),
        ('siliconflow', '硅基流动'),
        ('zhipu', '智谱'),
        ('openrouter', 'OpenRouter'),
        ('together', 'Together AI'),
        ('groq', 'Groq'),
        ('ollama', 'Ollama'),
        ('vllm', 'vLLM'),
        ('other', '其他 OpenAI 兼容模型'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, verbose_name='配置角色')
    model_type = models.CharField(max_length=20, choices=MODEL_TYPE_CHOICES, default='other', verbose_name='模型提供商')
    api_key = models.CharField(max_length=500, blank=True, default='', verbose_name='API Key')
    base_url = models.URLField(max_length=500, verbose_name='API Base URL')
    model_name = models.CharField(max_length=100, verbose_name='模型名称')
    max_tokens = models.PositiveIntegerField(default=4096, verbose_name='最大 Token 数')
    temperature = models.FloatField(default=0.7, verbose_name='温度参数')
    top_p = models.FloatField(default=0.9, verbose_name='Top P 参数')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='agent_model_configs', verbose_name='创建者')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'assistant_agent_model_configs'
        verbose_name = 'AI Agent 模型配置'
        verbose_name_plural = 'AI Agent 模型配置'
        ordering = ['role', '-updated_at']

    def __str__(self):
        return f'{self.get_role_display()} - {self.name}'


class AgentPromptConfig(models.Model):
    """Prompt settings dedicated to AI Agent Chat and Alpha workflows."""

    ROLE_CHOICES = [
        ('chat', 'Chat 提示词'),
        ('agent', 'Agent 提示词'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, verbose_name='配置角色')
    content = models.TextField(verbose_name='提示词内容')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='agent_prompt_configs', verbose_name='创建者')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'assistant_agent_prompt_configs'
        ordering = ['role', '-updated_at']


class AssistantSession(models.Model):
    """智能助手会话记录"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assistant_sessions', verbose_name='用户')
    session_id = models.CharField(max_length=200, verbose_name='会话ID')
    title = models.CharField(max_length=500, blank=True, verbose_name='会话标题')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'assistant_sessions'
        verbose_name = '智能助手会话'
        verbose_name_plural = '智能助手会话'
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.title or self.session_id}"


class ChatMessage(models.Model):
    """聊天消息记录"""
    ROLE_CHOICES = [
        ('user', '用户'),
        ('assistant', '助手'),
    ]
    
    session = models.ForeignKey(AssistantSession, on_delete=models.CASCADE, related_name='chat_messages', verbose_name='会话')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name='角色')
    content = models.TextField(verbose_name='消息内容')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    
    class Meta:
        db_table = 'chat_messages'
        verbose_name = '聊天消息'
        verbose_name_plural = '聊天消息'
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.get_role_display()}: {self.content[:50]}"


class AssistantMessage(models.Model):
    """智能助手消息记录（保留用于向后兼容）"""
    MESSAGE_TYPE_CHOICES = [
        ('user', '用户消息'),
        ('assistant', '助手回复'),
    ]
    
    session = models.ForeignKey(AssistantSession, on_delete=models.CASCADE, related_name='messages', verbose_name='会话')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, verbose_name='消息类型')
    content = models.TextField(verbose_name='消息内容')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    
    class Meta:
        db_table = 'assistant_messages'
        verbose_name = '智能助手消息'
        verbose_name_plural = '智能助手消息'
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.get_message_type_display()}: {self.content[:50]}"
