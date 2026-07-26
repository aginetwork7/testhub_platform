from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ApiAutomationProject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True, verbose_name='项目名称')),
                ('description', models.TextField(blank=True, verbose_name='项目描述')),
                ('status', models.CharField(choices=[('active', '进行中'), ('paused', '暂停'), ('archived', '已归档')], default='active', max_length=20, verbose_name='项目状态')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('members', models.ManyToManyField(blank=True, related_name='api_automation_projects', to=settings.AUTH_USER_MODEL, verbose_name='团队成员')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='owned_api_automation_projects', to=settings.AUTH_USER_MODEL, verbose_name='负责人')),
            ],
            options={
                'verbose_name': 'API自动化项目',
                'verbose_name_plural': 'API自动化项目',
                'db_table': 'api_automation_projects',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ApiAutomationSuite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='套件名称')),
                ('source_path', models.CharField(max_length=500, verbose_name='来源相对路径')),
                ('description', models.TextField(blank=True, verbose_name='描述')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='排序')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='api_automation.apiautomationsuite', verbose_name='父级套件')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suites', to='api_automation.apiautomationproject', verbose_name='所属项目')),
            ],
            options={
                'verbose_name': 'API自动化套件',
                'verbose_name_plural': 'API自动化套件',
                'db_table': 'api_automation_suites',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='ApiAutomationConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='配置名称')),
                ('base_url', models.URLField(blank=True, verbose_name='HTTP基础地址')),
                ('websocket_url', models.URLField(blank=True, verbose_name='WebSocket地址')),
                ('variables', models.JSONField(default=dict, verbose_name='环境变量')),
                ('timeout_seconds', models.PositiveIntegerField(default=30, verbose_name='请求超时秒数')),
                ('max_workers', models.PositiveIntegerField(default=1, verbose_name='并发数')),
                ('is_default', models.BooleanField(default=False, verbose_name='是否默认配置')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='创建人')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='configurations', to='api_automation.apiautomationproject', verbose_name='所属项目')),
            ],
            options={
                'verbose_name': 'API自动化配置',
                'verbose_name_plural': 'API自动化配置',
                'db_table': 'api_automation_configurations',
                'ordering': ['-is_default', 'name'],
            },
        ),
        migrations.CreateModel(
            name='ApiAutomationEndpoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=300, verbose_name='接口别名')),
                ('path', models.CharField(max_length=1000, verbose_name='接口路径')),
                ('description', models.TextField(blank=True, verbose_name='描述')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='endpoints', to='api_automation.apiautomationproject', verbose_name='所属项目')),
            ],
            options={
                'verbose_name': 'API自动化接口目录',
                'verbose_name_plural': 'API自动化接口目录',
                'db_table': 'api_automation_endpoints',
                'ordering': ['key'],
            },
        ),
        migrations.CreateModel(
            name='ApiAutomationCase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=300, verbose_name='用例名称')),
                ('description', models.TextField(blank=True, verbose_name='用例描述')),
                ('source_path', models.CharField(max_length=500, verbose_name='来源相对路径')),
                ('source_class', models.CharField(max_length=200, verbose_name='来源测试类')),
                ('source_function', models.CharField(max_length=300, verbose_name='来源测试方法')),
                ('node_id', models.CharField(max_length=255, unique=True, verbose_name='pytest节点ID')),
                ('priority', models.CharField(choices=[('P0', 'P0'), ('P1', 'P1'), ('P2', 'P2')], default='P2', max_length=10, verbose_name='优先级')),
                ('markers', models.JSONField(default=list, verbose_name='pytest标记')),
                ('parameter_sets', models.JSONField(default=list, verbose_name='参数化数据')),
                ('source_code', models.TextField(verbose_name='原始用例代码')),
                ('setup_code', models.TextField(blank=True, verbose_name='前置代码')),
                ('teardown_code', models.TextField(blank=True, verbose_name='后置代码')),
                ('execution_mode', models.CharField(choices=[('STRUCTURED', '结构化执行'), ('CODE', '代码执行'), ('MANUAL_REVIEW', '待人工完善')], default='MANUAL_REVIEW', max_length=30, verbose_name='执行模式')),
                ('is_skipped', models.BooleanField(default=False, verbose_name='是否跳过')),
                ('skip_reason', models.CharField(blank=True, max_length=500, verbose_name='跳过原因')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('source_hash', models.CharField(max_length=64, verbose_name='来源哈希')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('suite', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cases', to='api_automation.apiautomationsuite', verbose_name='所属套件')),
            ],
            options={
                'verbose_name': 'API自动化用例',
                'verbose_name_plural': 'API自动化用例',
                'db_table': 'api_automation_cases',
                'ordering': ['source_path', 'source_class', 'source_function'],
            },
        ),
        migrations.CreateModel(
            name='ApiAutomationStep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(verbose_name='执行顺序')),
                ('name', models.CharField(max_length=300, verbose_name='步骤名称')),
                ('step_type', models.CharField(choices=[('HTTP_REQUEST', 'HTTP请求'), ('WEBSOCKET_REQUEST', 'WebSocket请求'), ('PYTHON', 'Python代码')], max_length=30, verbose_name='步骤类型')),
                ('request_data', models.JSONField(blank=True, default=dict, verbose_name='请求定义')),
                ('assertions', models.JSONField(blank=True, default=list, verbose_name='断言定义')),
                ('code', models.TextField(blank=True, verbose_name='代码片段')),
                ('is_executable', models.BooleanField(default=False, verbose_name='是否可执行')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='steps', to='api_automation.apiautomationcase', verbose_name='所属用例')),
            ],
            options={
                'verbose_name': 'API自动化步骤',
                'verbose_name_plural': 'API自动化步骤',
                'db_table': 'api_automation_steps',
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='ApiAutomationRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('selection', models.JSONField(default=dict, verbose_name='用例选择条件')),
                ('status', models.CharField(choices=[('PENDING', '待执行'), ('RUNNING', '执行中'), ('COMPLETED', '已完成'), ('FAILED', '失败'), ('CANCELLED', '已取消')], default='PENDING', max_length=20, verbose_name='执行状态')),
                ('total_cases', models.PositiveIntegerField(default=0, verbose_name='用例总数')),
                ('passed_cases', models.PositiveIntegerField(default=0, verbose_name='通过数')),
                ('failed_cases', models.PositiveIntegerField(default=0, verbose_name='失败数')),
                ('skipped_cases', models.PositiveIntegerField(default=0, verbose_name='跳过数')),
                ('started_at', models.DateTimeField(blank=True, null=True, verbose_name='开始时间')),
                ('ended_at', models.DateTimeField(blank=True, null=True, verbose_name='结束时间')),
                ('log_content', models.TextField(blank=True, verbose_name='执行日志')),
                ('report_path', models.CharField(blank=True, max_length=1000, verbose_name='报告路径')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('configuration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='runs', to='api_automation.apiautomationconfiguration', verbose_name='执行配置')),
                ('executed_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='执行人')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='runs', to='api_automation.apiautomationproject', verbose_name='所属项目')),
            ],
            options={
                'verbose_name': 'API自动化执行记录',
                'verbose_name_plural': 'API自动化执行记录',
                'db_table': 'api_automation_runs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ApiAutomationCaseResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('PASSED', '通过'), ('FAILED', '失败'), ('SKIPPED', '跳过'), ('ERROR', '错误')], max_length=20, verbose_name='执行状态')),
                ('duration_ms', models.FloatField(blank=True, null=True, verbose_name='耗时毫秒')),
                ('error_message', models.TextField(blank=True, verbose_name='错误信息')),
                ('trace', models.TextField(blank=True, verbose_name='错误堆栈')),
                ('details', models.JSONField(default=dict, verbose_name='执行详情')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='results', to='api_automation.apiautomationcase', verbose_name='测试用例')),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='case_results', to='api_automation.apiautomationrun', verbose_name='所属执行')),
            ],
            options={
                'verbose_name': 'API自动化用例结果',
                'verbose_name_plural': 'API自动化用例结果',
                'db_table': 'api_automation_case_results',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='apiautomationsuite',
            constraint=models.UniqueConstraint(fields=('project', 'source_path'), name='unique_api_automation_suite_path'),
        ),
        migrations.AddConstraint(
            model_name='apiautomationconfiguration',
            constraint=models.UniqueConstraint(fields=('project', 'name'), name='unique_api_automation_configuration_name'),
        ),
        migrations.AddConstraint(
            model_name='apiautomationendpoint',
            constraint=models.UniqueConstraint(fields=('project', 'key'), name='unique_api_automation_endpoint_key'),
        ),
        migrations.AddConstraint(
            model_name='apiautomationstep',
            constraint=models.UniqueConstraint(fields=('case', 'order'), name='unique_api_automation_step_order'),
        ),
        migrations.AddConstraint(
            model_name='apiautomationcaseresult',
            constraint=models.UniqueConstraint(fields=('run', 'case'), name='unique_api_automation_run_case'),
        ),
        migrations.AddIndex(
            model_name='apiautomationcase',
            index=models.Index(fields=['suite', 'priority'], name='api_automa_suite_i_b419a1_idx'),
        ),
        migrations.AddIndex(
            model_name='apiautomationcase',
            index=models.Index(fields=['source_path'], name='api_automa_source__458c36_idx'),
        ),
        migrations.AddIndex(
            model_name='apiautomationcase',
            index=models.Index(fields=['execution_mode'], name='api_automa_execut_07b919_idx'),
        ),
    ]