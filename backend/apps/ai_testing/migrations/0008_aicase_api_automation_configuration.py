from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api_automation', '0001_initial'),
        ('ai_testing', '0007_alter_aiexecutionrecord_execution_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='aicase',
            name='api_automation_configuration',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='ai_testing_cases',
                to='api_automation.apiautomationconfiguration',
                verbose_name='设备 CLI 环境',
            ),
        ),
    ]