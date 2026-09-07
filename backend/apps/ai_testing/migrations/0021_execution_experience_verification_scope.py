from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0020_execution_evidence_foundation'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiexecutionexperience',
            name='permission_fingerprint',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='权限指纹'),
        ),
        migrations.AddField(
            model_name='aiexecutionexperience',
            name='assertion_contract_hash',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='断言契约哈希'),
        ),
    ]