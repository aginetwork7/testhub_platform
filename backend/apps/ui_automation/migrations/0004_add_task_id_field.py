from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ui_automation', '0003_remove_scheduled_task_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='uinotificationlog',
            name='task_id',
            field=models.IntegerField(blank=True, null=True, verbose_name='关联任务ID'),
        ),
    ]
