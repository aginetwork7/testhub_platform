from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ui_automation', '0002_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='uinotificationlog',
            name='task',
        ),
        migrations.RemoveField(
            model_name='uitasknotificationsetting',
            name='task',
        ),
        migrations.RemoveField(
            model_name='uitasknotificationsetting',
            name='custom_recipients',
        ),
        migrations.RemoveField(
            model_name='uitasknotificationsetting',
            name='notification_config',
        ),
        migrations.DeleteModel(
            name='UiTaskNotificationSetting',
        ),
        migrations.DeleteModel(
            name='UiScheduledTask',
        ),
    ]
