from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0029_assertion_result_attempt_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIActionCacheEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cache_key', models.CharField(max_length=191, unique=True, verbose_name='缓存键')),
                ('schema_version', models.CharField(default='', max_length=16, verbose_name='键格式版本')),
                ('project_id', models.IntegerField(blank=True, db_index=True, null=True, verbose_name='项目 id')),
                ('ai_case_id', models.IntegerField(blank=True, db_index=True, null=True, verbose_name='用例 id')),
                ('case_name', models.CharField(blank=True, default='', max_length=255, verbose_name='用例名')),
                ('step_index', models.PositiveIntegerField(default=0, verbose_name='步骤序号')),
                ('step_description', models.TextField(blank=True, default='', verbose_name='步骤描述')),
                ('page_url', models.CharField(blank=True, default='', max_length=1000, verbose_name='页面地址')),
                ('page_fingerprint', models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='页面指纹')),
                ('environment_key', models.CharField(blank=True, default='', max_length=200, verbose_name='环境标识')),
                ('permission_fingerprint', models.CharField(blank=True, default='', max_length=64, verbose_name='权限指纹')),
                ('actions', models.JSONField(default=list, verbose_name='动作序列')),
                ('hit_count', models.PositiveIntegerField(default=0, verbose_name='命中次数')),
                ('last_hit_at', models.DateTimeField(blank=True, null=True, verbose_name='最近命中时间')),
                ('expires_at', models.DateTimeField(db_index=True, verbose_name='过期时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': 'AI步骤动作缓存',
                'verbose_name_plural': 'AI步骤动作缓存',
                'db_table': 'ai_testing_action_cache_entries',
                'indexes': [models.Index(fields=['case_name', 'step_index'], name='ai_action_cache_step_idx')],
            },
        ),
    ]
