from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api_automation', '0007_add_endpoint_metadata_and_coverage'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationconfiguration',
            name='runtime_settings',
            field=models.JSONField(default=dict, verbose_name='测试运行设置'),
        ),
    ]