from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api_automation', '0003_add_code_runtime_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationcase',
            name='module_support_code',
            field=models.TextField(blank=True, verbose_name='模块辅助代码'),
        ),
        migrations.AddField(
            model_name='apiautomationcase',
            name='class_support_code',
            field=models.TextField(blank=True, verbose_name='测试类辅助代码'),
        ),
    ]