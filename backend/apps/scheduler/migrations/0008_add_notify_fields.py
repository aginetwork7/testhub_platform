from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0006_scheduleconfig_notification_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleconfig',
            name='notify_on_email',
            field=models.BooleanField(default=False, verbose_name='邮箱通知'),
        ),
        migrations.AddField(
            model_name='scheduleconfig',
            name='notify_on_webhook',
            field=models.BooleanField(default=False, verbose_name='Webhook机器人通知'),
        ),
    ]
