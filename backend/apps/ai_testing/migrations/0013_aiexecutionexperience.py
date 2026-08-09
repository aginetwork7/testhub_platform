from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0012_aicase_case_number'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIExecutionExperience',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step_description', models.TextField(verbose_name='步骤描述')),
                ('intent_hash', models.CharField(db_index=True, max_length=64, verbose_name='步骤语义哈希')),
                ('page_url', models.CharField(blank=True, default='', max_length=1000, verbose_name='页面地址')),
                ('page_fingerprint', models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='页面指纹')),
                ('environment_key', models.CharField(blank=True, default='', max_length=200, verbose_name='环境标识')),
                ('action_sequence', models.JSONField(default=list, verbose_name='已验证动作序列')),
                ('status', models.CharField(choices=[('verified', '已验证'), ('invalid', '已失效')], db_index=True, default='verified', max_length=20, verbose_name='状态')),
                ('review_status', models.CharField(choices=[('auto_verified', '自动验证'), ('confirmed', '人工确认'), ('rejected', '人工拒绝')], default='auto_verified', max_length=20, verbose_name='审核状态')),
                ('review_note', models.TextField(blank=True, default='', verbose_name='审核备注')),
                ('success_count', models.PositiveIntegerField(default=1, verbose_name='成功次数')),
                ('failure_count', models.PositiveIntegerField(default=0, verbose_name='失败次数')),
                ('confidence', models.FloatField(default=0.7, verbose_name='置信度')),
                ('last_verified_at', models.DateTimeField(auto_now=True, verbose_name='最近验证时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('ai_case', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='execution_experiences', to='ai_testing.aicase')),
                ('execution_record', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='experiences', to='ai_testing.aiexecutionrecord')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='execution_experiences', to='ai_testing.aiproject')),
            ],
            options={
                'verbose_name': 'AI执行经验',
                'verbose_name_plural': 'AI执行经验',
                'db_table': 'ai_testing_execution_experiences',
                'ordering': ['-confidence', '-last_verified_at'],
            },
        ),
        migrations.AddIndex(
            model_name='aiexecutionexperience',
            index=models.Index(fields=['project', 'intent_hash', 'status'], name='ai_testing__project_37575f_idx'),
        ),
        migrations.AddIndex(
            model_name='aiexecutionexperience',
            index=models.Index(fields=['project', 'page_fingerprint', 'status'], name='ai_testing__project_e20de4_idx'),
        ),
    ]