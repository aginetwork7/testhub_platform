from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


AI_TEST_MODEL_ROLES = ('planner_text', 'planner_vision', 'executor_text', 'executor_vision', 'hermes_agent')
PROMPT_ROLE_MAP = {
    'browser_use_text': 'executor_text',
    'browser_use_vision': 'executor_vision',
    'hermes_agent': 'hermes_agent',
}
PLANNER_VISION_PROMPT_CONTENT = '''Create actions:
Return only one JSON object: {"actions":[...]}. No prose. Actions allowed: click, wait, assert, assert_text_contains, assert_url_contains. A click needs selector or loc="(x,y)". For camera lists use {"action":"assert","assert_kind":"camera_list","expected":"true"}. For live streams use {"action":"assert","assert_kind":"stream_active","expected":"true"}. When opening Cameras from an icon-only sidebar, return two actions: click the sidebar icon with loc, then {"action":"assert","assert_kind":"site_list","expected":"true"}. Do not click a Cameras text menu item unless it is actually visible in the screenshot. Each navigation sequence must be followed by an assertion.

Assess playback advance:
Compare two playback screenshots. Read the burned-in HH:MM:SS timestamps. Return only JSON: {"before_time":"HH:MM:SS","after_time":"HH:MM:SS","advanced_seconds":number,"confidence":number}. No prose.'''


def migrate_legacy_configurations(apps, schema_editor):
    LegacyModelConfig = apps.get_model('requirement_analysis', 'AIModelConfig')
    LegacyPromptConfig = apps.get_model('requirement_analysis', 'PromptConfig')
    AITestModelConfig = apps.get_model('ai_testing', 'AITestModelConfig')
    AITestPromptConfig = apps.get_model('ai_testing', 'AITestPromptConfig')

    for config in LegacyModelConfig.objects.filter(role__in=AI_TEST_MODEL_ROLES).iterator():
        copied_config = AITestModelConfig.objects.create(
            name=config.name,
            role=config.role,
            model_type=config.model_type,
            model_name=config.model_name,
            base_url=config.base_url,
            api_key=config.api_key or '',
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            is_active=config.is_active,
            created_by_id=config.created_by_id,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
        AITestModelConfig.objects.filter(pk=copied_config.pk).update(
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    for config in LegacyPromptConfig.objects.filter(prompt_type__in=PROMPT_ROLE_MAP).iterator():
        copied_config = AITestPromptConfig.objects.create(
            name=config.name,
            prompt_type=PROMPT_ROLE_MAP[config.prompt_type],
            content=config.content,
            is_active=config.is_active,
            created_by_id=config.created_by_id,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
        AITestPromptConfig.objects.filter(pk=copied_config.pk).update(
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    if not AITestPromptConfig.objects.filter(prompt_type='planner_vision', is_active=True).exists():
        AITestPromptConfig.objects.create(
            name='Planner Vision 默认提示词',
            prompt_type='planner_vision',
            content=PLANNER_VISION_PROMPT_CONTENT,
            is_active=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ai_testing', '0016_add_alpha_reflection_task'),
        ('requirement_analysis', '0010_add_alpha_model_roles'),
    ]

    operations = [
        migrations.CreateModel(
            name='AITestModelConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='配置名称')),
                ('model_type', models.CharField(choices=[('deepseek', 'DeepSeek'), ('qwen', '通义千问'), ('gemini', 'Google Gemini'), ('siliconflow', '硅基流动'), ('zhipu', '智谱'), ('other', '其他')], max_length=20, verbose_name='模型类型')),
                ('role', models.CharField(choices=[('planner_text', 'Planner 文本模型'), ('planner_vision', 'Planner 视觉模型'), ('executor_text', 'Executor 文本模型'), ('executor_vision', 'Executor 视觉模型'), ('hermes_agent', 'Hermes Agent 模型')], max_length=20, verbose_name='角色')),
                ('api_key', models.CharField(blank=True, default='', max_length=200, verbose_name='API Key')),
                ('base_url', models.URLField(blank=True, default='', verbose_name='API Base URL')),
                ('model_name', models.CharField(max_length=100, verbose_name='模型名称')),
                ('max_tokens', models.IntegerField(default=4096, verbose_name='最大Token数')),
                ('temperature', models.FloatField(default=0.7, verbose_name='温度参数')),
                ('top_p', models.FloatField(default=0.9, verbose_name='Top P参数')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_test_model_configs', to=settings.AUTH_USER_MODEL, verbose_name='创建者')),
            ],
            options={'db_table': 'ai_testing_model_configs', 'ordering': ['role', '-updated_at']},
        ),
        migrations.CreateModel(
            name='AITestPromptConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='配置名称')),
                ('prompt_type', models.CharField(choices=[('planner_text', 'Planner 文本提示词'), ('planner_vision', 'Planner 视觉提示词'), ('executor_text', 'Executor 文本提示词'), ('executor_vision', 'Executor 视觉提示词'), ('hermes_agent', 'Hermes Agent 提示词')], max_length=20, verbose_name='提示词类型')),
                ('content', models.TextField(verbose_name='提示词内容')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_test_prompt_configs', to=settings.AUTH_USER_MODEL, verbose_name='创建者')),
            ],
            options={'db_table': 'ai_testing_prompt_configs', 'ordering': ['prompt_type', '-updated_at']},
        ),
        migrations.RunPython(migrate_legacy_configurations, migrations.RunPython.noop),
    ]