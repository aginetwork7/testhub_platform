from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('scheduler', '0009_change_notification_config_to_many'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scheduleconfig',
            name='module',
            field=models.CharField(
                choices=[
                    ('API', 'API测试'),
                    ('API_AUTOMATION', 'API自动化测试'),
                    ('UI', 'UI自动化'),
                    ('APP', 'APP自动化'),
                ],
                max_length=20,
                verbose_name='所属模块',
            ),
        ),
        migrations.AlterField(
            model_name='scheduleconfig',
            name='task_type',
            field=models.CharField(
                choices=[
                    ('API_TEST_SUITE', 'API测试套件'),
                    ('API_REQUEST', 'API请求'),
                    ('API_AUTOMATION_SUITE', 'API自动化测试套件'),
                    ('UI_TEST_SUITE', 'UI测试套件'),
                    ('UI_TEST_CASE', 'UI测试用例'),
                    ('APP_TEST_SUITE', 'APP测试套件'),
                    ('APP_TEST_CASE', 'APP测试用例'),
                ],
                max_length=30,
                verbose_name='任务类型',
            ),
        ),
    ]