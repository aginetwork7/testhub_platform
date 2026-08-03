from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0008_aicase_api_automation_configuration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aiexecutionrecord',
            name='execution_mode',
            field=models.CharField(
                choices=[
                    ('text', '文本模式'),
                    ('hermes', 'Hermes模式'),
                    ('planner_v2', 'Planner'),
                ],
                default='planner_v2',
                max_length=20,
                verbose_name='执行模式',
            ),
        ),
    ]