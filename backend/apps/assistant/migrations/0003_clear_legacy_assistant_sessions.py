from django.db import migrations


def clear_legacy_assistant_sessions(apps, schema_editor):
    assistant_session = apps.get_model('assistant', 'AssistantSession')
    assistant_session.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(clear_legacy_assistant_sessions, migrations.RunPython.noop),
    ]