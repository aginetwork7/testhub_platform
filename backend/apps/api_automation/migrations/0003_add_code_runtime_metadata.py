from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api_automation', '0002_add_advanced_runtime_configuration'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationcase',
            name='module_imports',
            field=models.TextField(blank=True, verbose_name='模块导入代码'),
        ),
        migrations.AddField(
            model_name='apiautomationcase',
            name='support_code',
            field=models.TextField(blank=True, verbose_name='辅助代码'),
        ),
    ]