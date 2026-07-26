from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('api_automation', '0006_add_websocket_schemas'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationendpoint',
            name='deprecated',
            field=models.BooleanField(default=False, verbose_name='是否废弃'),
        ),
        migrations.AddField(
            model_name='apiautomationendpoint',
            name='methods',
            field=models.JSONField(default=list, verbose_name='HTTP方法'),
        ),
        migrations.AddField(
            model_name='apiautomationendpoint',
            name='summary',
            field=models.CharField(blank=True, max_length=500, verbose_name='接口摘要'),
        ),
        migrations.AddField(
            model_name='apiautomationendpoint',
            name='tags',
            field=models.JSONField(default=list, verbose_name='Swagger标签'),
        ),
        migrations.CreateModel(
            name='ApiAutomationCoverageSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period', models.CharField(choices=[('WEEKLY', '每周'), ('MONTHLY', '每月')], max_length=10, verbose_name='统计周期')),
                ('snapshot_date', models.DateField(verbose_name='快照日期')),
                ('total_endpoints', models.PositiveIntegerField(default=0, verbose_name='接口总数')),
                ('covered_endpoints', models.PositiveIntegerField(default=0, verbose_name='已覆盖接口数')),
                ('coverage_rate', models.FloatField(default=0, verbose_name='覆盖率')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coverage_snapshots', to='api_automation.apiautomationproject', verbose_name='所属项目')),
            ],
            options={
                'verbose_name': 'API自动化覆盖率快照',
                'verbose_name_plural': 'API自动化覆盖率快照',
                'db_table': 'api_automation_coverage_snapshots',
                'ordering': ['period', 'snapshot_date'],
            },
        ),
        migrations.AddConstraint(
            model_name='apiautomationcoveragesnapshot',
            constraint=models.UniqueConstraint(fields=('project', 'period', 'snapshot_date'), name='unique_api_automation_coverage_snapshot'),
        ),
    ]