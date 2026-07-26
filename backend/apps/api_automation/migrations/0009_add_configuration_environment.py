from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api_automation', '0008_add_runtime_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationconfiguration',
            name='environment',
            field=models.CharField(default='custom', max_length=50, verbose_name='运行环境'),
        ),
        migrations.AddConstraint(
            model_name='apiautomationconfiguration',
            constraint=models.UniqueConstraint(fields=('project', 'environment'), name='unique_api_automation_configuration_environment'),
        ),
    ]