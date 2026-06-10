from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0003_alter_aiexecutionrecord_execution_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='aicase',
            name='case_mode',
            field=models.CharField(
                choices=[('freeform', '自由描述'), ('structured', '结构化步骤')],
                default='freeform',
                max_length=20,
                verbose_name='用例模式',
            ),
        ),
        migrations.AddField(
            model_name='aicase',
            name='task_steps',
            field=models.JSONField(blank=True, default=list, verbose_name='结构化步骤'),
        ),
        migrations.AddField(
            model_name='aiexecutionrecord',
            name='artifacts',
            field=models.JSONField(blank=True, default=list, verbose_name='执行产物'),
        ),
        migrations.AddField(
            model_name='aiexecutionrecord',
            name='cache_stats',
            field=models.JSONField(blank=True, default=dict, verbose_name='缓存统计'),
        ),
        migrations.AddField(
            model_name='aiexecutionrecord',
            name='planner_trace',
            field=models.JSONField(blank=True, default=dict, verbose_name='规划追踪数据'),
        ),
        migrations.AlterField(
            model_name='aiexecutionrecord',
            name='execution_mode',
            field=models.CharField(
                choices=[('text', '文本模式'), ('hermes', 'Hermes模式'), ('planner_v2', '结构化规划模式')],
                default='text',
                max_length=20,
                verbose_name='执行模式',
            ),
        ),
    ]