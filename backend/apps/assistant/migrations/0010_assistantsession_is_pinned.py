from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('assistant', '0009_seed_default_agent_prompts'),
    ]

    operations = [
        migrations.AddField(
            model_name='assistantsession',
            name='is_pinned',
            field=models.BooleanField(default=False, verbose_name='是否置顶'),
        ),
        migrations.AlterModelOptions(
            name='assistantsession',
            options={
                'ordering': ['-is_pinned', '-updated_at'],
                'verbose_name': '智能助手会话',
                'verbose_name_plural': '智能助手会话',
            },
        ),
    ]