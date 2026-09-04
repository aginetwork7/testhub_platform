from django.db import migrations, models
import django.db.models.deletion


def migrate_case_environments(apps, schema_editor):
    AICase = apps.get_model('ai_testing', 'AICase')
    LegacyEnvironment = apps.get_model('api_automation', 'ApiAutomationConfiguration')
    EnvironmentConfiguration = apps.get_model('core', 'EnvironmentConfiguration')
    for case in AICase.objects.exclude(api_automation_configuration_id=None).iterator():
        legacy = LegacyEnvironment.objects.filter(id=case.api_automation_configuration_id).first()
        if legacy is None:
            continue
        configuration = EnvironmentConfiguration.objects.filter(
            name=legacy.name,
            environment=legacy.environment,
        ).first()
        if configuration is not None:
            case.environment_configuration_id = configuration.id
            case.save(update_fields=['environment_configuration'])


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0021_execution_experience_verification_scope'),
        ('core', '0011_migrate_global_environment_configurations'),
    ]

    operations = [
        migrations.AddField(
            model_name='aicase',
            name='environment_configuration',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ai_testing_cases',
                to='core.environmentconfiguration',
                verbose_name='全局环境配置',
            ),
        ),
        migrations.RunPython(migrate_case_environments, migrations.RunPython.noop),
        migrations.RemoveField(model_name='aicase', name='api_automation_configuration'),
    ]