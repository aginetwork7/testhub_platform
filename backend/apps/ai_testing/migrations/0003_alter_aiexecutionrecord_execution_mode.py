from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0002_migrate_old_ai_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aiexecutionrecord',
            name='execution_mode',
            field=models.CharField(
                choices=[('text', '文本模式'), ('hermes', 'Hermes模式')],
                default='text',
                max_length=20,
                verbose_name='执行模式',
            ),
        ),
    ]