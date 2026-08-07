import re

from django.db import migrations, models


PRIORITY_PATTERN = re.compile(r'\n{0,2}优先级：\s*(P[012])\s*')


def migrate_priorities(apps, schema_editor):
    ai_case_model = apps.get_model('ai_testing', 'AICase')

    for ai_case in ai_case_model.objects.all().iterator():
        description = ai_case.description or ''
        task_description = ai_case.task_description or ''
        match = PRIORITY_PATTERN.search(task_description) or PRIORITY_PATTERN.search(description)

        ai_case.priority = match.group(1) if match else 'P0'
        ai_case.description = PRIORITY_PATTERN.sub('', description).strip()
        ai_case.task_description = PRIORITY_PATTERN.sub('', task_description).strip()
        ai_case.save(update_fields=['priority', 'description', 'task_description'])


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0010_aicase_planned_steps'),
    ]

    operations = [
        migrations.AddField(
            model_name='aicase',
            name='priority',
            field=models.CharField(
                choices=[('P0', 'P0'), ('P1', 'P1'), ('P2', 'P2')],
                default='P0',
                max_length=2,
                verbose_name='优先级',
            ),
        ),
        migrations.RunPython(migrate_priorities, migrations.RunPython.noop),
    ]