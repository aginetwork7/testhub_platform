from django.db import migrations, models
import django.db.models.deletion


def migrate_execution_environments(apps, schema_editor):
    EnvironmentConfiguration = apps.get_model('core', 'EnvironmentConfiguration')
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM ai_testing_execution_records LIKE 'api_automation_configuration_id'")
        if cursor.fetchone() is None:
            return
        cursor.execute(
            'UPDATE ai_testing_execution_records record '
            'JOIN api_automation_configurations legacy ON legacy.id = record.api_automation_configuration_id '
            'JOIN environment_configurations environment ON environment.name = legacy.name AND environment.environment = legacy.environment '
            'SET record.environment_configuration_id = environment.id'
        )


def ensure_environment_column(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM ai_testing_execution_records LIKE 'environment_configuration_id'")
        if cursor.fetchone() is None:
            cursor.execute('ALTER TABLE ai_testing_execution_records ADD COLUMN environment_configuration_id bigint NULL')


def remove_legacy_environment_column(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM ai_testing_execution_records LIKE 'api_automation_configuration_id'")
        if cursor.fetchone() is None:
            return
        cursor.execute(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_testing_execution_records' "
            "AND COLUMN_NAME = 'api_automation_configuration_id' AND REFERENCED_TABLE_NAME IS NOT NULL"
        )
        for (constraint_name,) in cursor.fetchall():
            cursor.execute(f'ALTER TABLE ai_testing_execution_records DROP FOREIGN KEY `{constraint_name}`')
        cursor.execute('ALTER TABLE ai_testing_execution_records DROP COLUMN api_automation_configuration_id')


class Migration(migrations.Migration):
    atomic = False
    dependencies = [('ai_testing', '0023_aiexecutionexperience_last_verified_attempt_and_more'), ('core', '0011_migrate_global_environment_configurations')]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(ensure_environment_column, migrations.RunPython.noop)],
            state_operations=[
                migrations.AddField(model_name='aiexecutionrecord', name='environment_configuration', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_testing_execution_records', to='core.environmentconfiguration', verbose_name='全局环境配置')),
            ],
        ),
        migrations.RunPython(migrate_execution_environments, migrations.RunPython.noop),
        migrations.RunPython(remove_legacy_environment_column, migrations.RunPython.noop),
    ]