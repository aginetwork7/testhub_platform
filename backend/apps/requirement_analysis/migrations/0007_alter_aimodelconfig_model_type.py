from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('requirement_analysis', '0006_alter_promptconfig_prompt_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aimodelconfig',
            name='model_type',
            field=models.CharField(
                choices=[
                    ('deepseek', 'DeepSeek'),
                    ('qwen', '通义千问'),
                    ('gemini', 'Google Gemini'),
                    ('siliconflow', '硅基流动'),
                    ('zhipu', '智谱'),
                    ('other', '其他'),
                ],
                max_length=20,
                verbose_name='模型类型',
            ),
        ),
    ]