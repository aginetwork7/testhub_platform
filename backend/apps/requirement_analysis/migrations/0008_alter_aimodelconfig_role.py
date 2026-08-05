from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('requirement_analysis', '0007_alter_aimodelconfig_model_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aimodelconfig',
            name='role',
            field=models.CharField(
                choices=[
                    ('writer', '测试用例编写专家'),
                    ('reviewer', '测试评审专家'),
                    ('browser_use_text', 'Browser Use - 文本模式'),
                    ('browser_use_vision', 'Browser Use - 视觉模式'),
                    ('planner_text', 'AI智能测试 - Planner文本模型'),
                    ('planner_vision', 'AI智能测试 - Planner视觉模型'),
                    ('executor_text', 'AI智能测试 - Executor文本模型'),
                    ('executor_vision', 'AI智能测试 - Executor视觉模型'),
                    ('hermes_agent', 'Hermes Agent'),
                ],
                max_length=20,
                verbose_name='角色',
            ),
        ),
    ]