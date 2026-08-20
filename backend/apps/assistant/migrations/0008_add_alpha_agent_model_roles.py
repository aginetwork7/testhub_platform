from django.db import migrations, models


ALPHA_AGENT_MODEL_ROLES = ('alpha_planner', 'alpha_reflection')


def migrate_legacy_alpha_configurations(apps, schema_editor):
    LegacyModelConfig = apps.get_model('requirement_analysis', 'AIModelConfig')
    AgentModelConfig = apps.get_model('assistant', 'AgentModelConfig')

    for config in LegacyModelConfig.objects.filter(role__in=ALPHA_AGENT_MODEL_ROLES).iterator():
        copied_config = AgentModelConfig.objects.create(
            name=config.name,
            role=config.role,
            model_type=config.model_type,
            api_key=config.api_key or '',
            base_url=config.base_url,
            model_name=config.model_name,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            is_active=config.is_active,
            created_by_id=config.created_by_id,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
        AgentModelConfig.objects.filter(pk=copied_config.pk).update(
            created_at=config.created_at,
            updated_at=config.updated_at,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('assistant', '0007_agentpromptconfig'),
        ('requirement_analysis', '0010_add_alpha_model_roles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agentmodelconfig',
            name='role',
            field=models.CharField(
                choices=[
                    ('chat', 'Chat 模型'),
                    ('agent', 'Agent 模型'),
                    ('alpha_planner', 'Alpha Planner 模型'),
                    ('alpha_reflection', 'Alpha Reflection 模型'),
                ],
                max_length=16,
                verbose_name='配置角色',
            ),
        ),
        migrations.RunPython(migrate_legacy_alpha_configurations, migrations.RunPython.noop),
    ]