from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0018_aiexecutionexperience_pending_review'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aiexecutionrecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', '等待中'),
                    ('running', '执行中'),
                    ('passed', '成功'),
                    ('failed', '失败'),
                    ('inconclusive', '证据不足'),
                    ('stopped', '已停止'),
                ],
                default='pending',
                max_length=20,
                verbose_name='执行状态',
            ),
        ),
    ]