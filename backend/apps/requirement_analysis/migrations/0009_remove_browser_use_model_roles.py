from django.db import migrations, models


def remove_browser_use_configs(apps, schema_editor):
    model = apps.get_model('requirement_analysis', 'AIModelConfig')
    model.objects.filter(role__in=['browser_use_text', 'browser_use_vision']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('requirement_analysis', '0008_alter_aimodelconfig_role'),
    ]

    operations = [
        migrations.RunPython(remove_browser_use_configs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='aimodelconfig',
            name='role',
            field=models.CharField(
                choices=[
                    ('writer', '测试用例编写专家'),
                    ('reviewer', '测试评审专家'),
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