from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0009_alter_aiexecutionrecord_execution_mode_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='aicase',
            name='planned_steps',
            field=models.JSONField(blank=True, default=list, verbose_name='Planner执行步骤'),
        ),
    ]