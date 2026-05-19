from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('requirement_analysis', '0005_alter_aimodelconfig_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='promptconfig',
            name='prompt_type',
            field=models.CharField(
                choices=[
                    ('writer', '用例编写提示词'),
                    ('reviewer', '用例评审提示词'),
                    ('browser_use_text', 'AI智能模式-文本提示词'),
                    ('browser_use_vision', 'AI智能模式-视觉提示词'),
                    ('hermes_agent', 'Hermes Agent提示词'),
                ],
                max_length=20,
                verbose_name='提示词类型',
            ),
        ),
    ]