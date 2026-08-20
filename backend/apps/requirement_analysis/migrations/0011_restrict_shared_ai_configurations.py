from django.db import migrations, models


def remove_non_requirement_configurations(apps, schema_editor):
    AIModelConfig = apps.get_model('requirement_analysis', 'AIModelConfig')
    PromptConfig = apps.get_model('requirement_analysis', 'PromptConfig')
    AIModelConfig.objects.exclude(role__in=('writer', 'reviewer')).delete()
    PromptConfig.objects.exclude(prompt_type__in=('writer', 'reviewer')).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('requirement_analysis', '0010_add_alpha_model_roles'),
        ('ai_testing', '0017_aitestmodelconfig_aitestpromptconfig'),
        ('assistant', '0008_add_alpha_agent_model_roles'),
    ]

    operations = [
        migrations.RunPython(remove_non_requirement_configurations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='aimodelconfig',
            name='role',
            field=models.CharField(choices=[('writer', '测试用例编写专家'), ('reviewer', '测试评审专家')], max_length=20, verbose_name='角色'),
        ),
        migrations.AlterField(
            model_name='promptconfig',
            name='prompt_type',
            field=models.CharField(choices=[('writer', '用例编写提示词'), ('reviewer', '用例评审提示词')], max_length=20, verbose_name='提示词类型'),
        ),
    ]