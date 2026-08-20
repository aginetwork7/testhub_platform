from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('assistant', '0006_remove_dify_integration'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentPromptConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='配置名称')),
                ('role', models.CharField(choices=[('chat', 'Chat 提示词'), ('agent', 'Agent 提示词')], max_length=16, verbose_name='配置角色')),
                ('content', models.TextField(verbose_name='提示词内容')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_at', models.DateTimeField(default=timezone.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='agent_prompt_configs', to=settings.AUTH_USER_MODEL, verbose_name='创建者')),
            ],
            options={'db_table': 'assistant_agent_prompt_configs', 'ordering': ['role', '-updated_at']},
        ),
    ]