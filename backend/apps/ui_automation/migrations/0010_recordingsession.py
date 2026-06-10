from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ui_automation', '0009_remove_aiexecutionrecord_ai_case_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RecordingSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='录制名称')),
                ('base_url', models.URLField(verbose_name='录制入口URL')),
                ('status', models.CharField(choices=[('created', '已创建'), ('uploaded', '已上传'), ('parsed', '已解析'), ('imported', '已导入'), ('cancelled', '已取消'), ('failed', '失败')], default='created', max_length=20, verbose_name='录制状态')),
                ('browser', models.CharField(default='chromium', max_length=20, verbose_name='浏览器类型')),
                ('target_language', models.CharField(default='python', max_length=20, verbose_name='目标语言')),
                ('framework', models.CharField(default='playwright', max_length=20, verbose_name='执行框架')),
                ('import_target', models.CharField(choices=[('script', '仅脚本'), ('test_case', '仅测试用例'), ('both', '脚本和测试用例')], default='both', max_length=20, verbose_name='导入目标')),
                ('raw_script', models.TextField(blank=True, verbose_name='原始录制脚本')),
                ('parsed_steps', models.JSONField(blank=True, default=list, verbose_name='解析后的步骤')),
                ('error_message', models.TextField(blank=True, verbose_name='错误信息')),
                ('started_at', models.DateTimeField(auto_now_add=True, verbose_name='发起时间')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='结束时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recording_sessions', to='ui_automation.uiproject', verbose_name='所属项目')),
                ('started_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ui_recording_sessions', to=settings.AUTH_USER_MODEL, verbose_name='发起人')),
            ],
            options={
                'verbose_name': 'UI录制会话',
                'verbose_name_plural': 'UI录制会话',
                'db_table': 'ui_recording_sessions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='recordingsession',
            index=models.Index(fields=['project', '-created_at'], name='ui_automat_project_367689_idx'),
        ),
        migrations.AddIndex(
            model_name='recordingsession',
            index=models.Index(fields=['started_by', '-created_at'], name='ui_automat_started_6f4031_idx'),
        ),
        migrations.AddIndex(
            model_name='recordingsession',
            index=models.Index(fields=['status'], name='ui_automat_status_8d84ca_idx'),
        ),
    ]