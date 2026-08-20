from django.db import migrations, models


def migrate_auto_verified_experiences(apps, schema_editor):
    AIExecutionExperience = apps.get_model('ai_testing', 'AIExecutionExperience')
    AIExecutionExperience.objects.filter(
        status='verified',
        review_status='auto_verified',
    ).update(status='pending', review_status='pending')


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0017_aitestmodelconfig_aitestpromptconfig'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aiexecutionexperience',
            name='review_status',
            field=models.CharField(
                choices=[
                    ('pending', '待确认'),
                    ('auto_verified', '自动验证'),
                    ('confirmed', '人工确认'),
                    ('rejected', '人工拒绝'),
                ],
                default='pending',
                max_length=20,
                verbose_name='审核状态',
            ),
        ),
        migrations.AlterField(
            model_name='aiexecutionexperience',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', '待定'),
                    ('verified', '已验证'),
                    ('invalid', '已失效'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
                verbose_name='状态',
            ),
        ),
        migrations.RunPython(migrate_auto_verified_experiences, migrations.RunPython.noop),
    ]