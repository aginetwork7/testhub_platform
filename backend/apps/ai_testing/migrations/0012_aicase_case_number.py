import re

from django.db import migrations, models


CASE_NUMBER_PATTERN = re.compile(r'^用例编号：\s*(.+?)\s*(?:\r?\n|$)')


def migrate_case_numbers(apps, schema_editor):
    ai_case_model = apps.get_model('ai_testing', 'AICase')

    for ai_case in ai_case_model.objects.all().iterator():
        description = ai_case.description or ''
        match = CASE_NUMBER_PATTERN.match(description)
        if match is None:
            continue

        ai_case.case_number = match.group(1).strip()
        ai_case.description = description[match.end():].strip()
        ai_case.save(update_fields=['case_number', 'description'])


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0011_aicase_priority'),
    ]

    operations = [
        migrations.AddField(
            model_name='aicase',
            name='case_number',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='用例编号'),
        ),
        migrations.RunPython(migrate_case_numbers, migrations.RunPython.noop),
    ]