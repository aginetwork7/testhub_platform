from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0008_add_notify_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='scheduleconfig',
            name='notification_config',
        ),
        migrations.AddField(
            model_name='scheduleconfig',
            name='notification_configs',
            field=models.ManyToManyField(blank=True, help_text='选择通知配置，用于发送通知时使用', related_name='schedules', to='core.unifiednotificationconfig', verbose_name='通知配置'),
        ),
    ]
