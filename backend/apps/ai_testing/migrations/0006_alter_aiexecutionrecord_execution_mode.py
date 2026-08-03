from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0005_alter_aicase_case_mode'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aiexecutionrecord',
            name='execution_mode',
            field=models.CharField(
                choices=[
                    ('text', '文本模式'),
                    ('hermes', 'Hermes模式'),
                    ('planner_v2', 'planner'),
                ],
                default='text',
                max_length=20,
                verbose_name='执行模式',
            ),
        ),
    ]