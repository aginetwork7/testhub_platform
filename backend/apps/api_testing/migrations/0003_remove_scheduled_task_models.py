from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api_testing', '0002_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='notificationlog',
            name='task',
        ),
        migrations.RemoveField(
            model_name='taskexecutionlog',
            name='task',
        ),
        migrations.RemoveField(
            model_name='tasknotificationsetting',
            name='task',
        ),
        migrations.RemoveField(
            model_name='tasknotificationsetting',
            name='custom_recipients',
        ),
        migrations.RemoveField(
            model_name='tasknotificationsetting',
            name='notification_config',
        ),
        migrations.DeleteModel(
            name='TaskExecutionLog',
        ),
        migrations.DeleteModel(
            name='TaskNotificationSetting',
        ),
        migrations.DeleteModel(
            name='ScheduledTask',
        ),
    ]
