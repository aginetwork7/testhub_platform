from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api_automation', '0005_add_websocket_parameters'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationproject',
            name='websocket_schemas',
            field=models.JSONField(default=dict, verbose_name='WebSocket响应Schema'),
        ),
    ]