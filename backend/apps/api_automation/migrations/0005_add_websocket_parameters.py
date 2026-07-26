from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api_automation', '0004_split_code_runtime_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationproject',
            name='websocket_params',
            field=models.JSONField(default=dict, verbose_name='WebSocket协议参数'),
        ),
    ]