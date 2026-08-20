from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api_automation', '0017_configuration_web_url'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='apiautomationconfiguration',
            name='unique_api_automation_configuration_name',
        ),
        migrations.RemoveConstraint(
            model_name='apiautomationconfiguration',
            name='unique_api_automation_configuration_environment',
        ),
        migrations.RemoveField(
            model_name='apiautomationconfiguration',
            name='project',
        ),
    ]