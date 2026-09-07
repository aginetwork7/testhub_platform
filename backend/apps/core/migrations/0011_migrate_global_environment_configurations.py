from django.db import migrations


def migrate_configurations(apps, schema_editor):
    LegacyEnvironment = apps.get_model('api_automation', 'ApiAutomationConfiguration')
    EnvironmentConfiguration = apps.get_model('core', 'EnvironmentConfiguration')
    for legacy in LegacyEnvironment.objects.all():
        EnvironmentConfiguration.objects.get_or_create(
            name=legacy.name,
            environment=legacy.environment,
            defaults={
                'base_url': legacy.base_url,
                'web_url': legacy.web_url,
                'websocket_url': legacy.websocket_url,
                'variables': legacy.variables,
                'auth_profiles': legacy.auth_profiles,
                'payment_config': legacy.payment_config,
                'model_profiles': legacy.model_profiles,
                'runtime_settings': legacy.runtime_settings,
                'event_device_keys_encrypted': legacy.event_device_keys_encrypted,
                'timeout_seconds': legacy.timeout_seconds,
                'max_workers': legacy.max_workers,
                'is_default': legacy.is_default,
                'created_by_id': legacy.created_by_id,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_environmentconfiguration'),
        ('api_automation', '0018_make_configurations_global'),
    ]

    operations = [
        migrations.RunPython(migrate_configurations, migrations.RunPython.noop),
    ]