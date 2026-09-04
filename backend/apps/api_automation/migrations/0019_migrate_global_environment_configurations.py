from django.db import migrations, models
import django.db.models.deletion


def migrate_run_configurations(apps, schema_editor):
    LegacyEnvironment = apps.get_model('api_automation', 'ApiAutomationConfiguration')
    EnvironmentConfiguration = apps.get_model('core', 'EnvironmentConfiguration')
    ApiAutomationRun = apps.get_model('api_automation', 'ApiAutomationRun')

    for legacy in LegacyEnvironment.objects.all().iterator():
        configuration = EnvironmentConfiguration.objects.filter(
            name=legacy.name,
            environment=legacy.environment,
        ).order_by('id').first()
        if configuration is not None:
            ApiAutomationRun.objects.filter(configuration_id=legacy.id).update(
                environment_configuration_id=configuration.id,
            )
        else:
            ApiAutomationRun.objects.filter(configuration_id=legacy.id).update(
                environment_configuration_id=None,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('api_automation', '0018_make_configurations_global'),
        ('ai_testing', '0024_aiexecutionrecord_environment_configuration'),
        ('core', '0011_migrate_global_environment_configurations'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationrun',
            name='environment_configuration',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='core.environmentconfiguration',
                verbose_name='执行配置',
            ),
        ),
        migrations.RunPython(migrate_run_configurations, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='apiautomationrun',
            name='configuration',
        ),
        migrations.RenameField(
            model_name='apiautomationrun',
            old_name='environment_configuration',
            new_name='configuration',
        ),
        migrations.DeleteModel(name='ApiAutomationConfiguration'),
    ]