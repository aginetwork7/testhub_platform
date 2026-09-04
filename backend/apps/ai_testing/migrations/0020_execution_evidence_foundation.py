from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0019_aiexecutionrecord_inconclusive_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIExecutionPlanRevision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revision_number', models.PositiveSmallIntegerField()),
                ('source_goal', models.TextField()),
                ('plan', models.JSONField(default=dict)),
                ('plan_hash', models.CharField(db_index=True, max_length=64)),
                ('reason', models.CharField(default='initial', max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('execution_record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plan_revisions', to='ai_testing.aiexecutionrecord')),
            ],
            options={'db_table': 'ai_testing_execution_plan_revisions', 'ordering': ['execution_record_id', 'revision_number']},
        ),
        migrations.CreateModel(
            name='AIExecutionStep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step_key', models.CharField(max_length=100)),
                ('display_order', models.PositiveSmallIntegerField()),
                ('intent', models.TextField()),
                ('dependencies', models.JSONField(default=list)),
                ('allowed_capabilities', models.JSONField(default=list)),
                ('assertions', models.JSONField(default=list)),
                ('status', models.CharField(choices=[('pending', '等待中'), ('running', '执行中'), ('action_completed', '动作完成'), ('verified', '已验证'), ('failed', '失败'), ('inconclusive', '证据不足'), ('skipped', '已跳过')], db_index=True, default='pending', max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan_revision', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='steps', to='ai_testing.aiexecutionplanrevision')),
            ],
            options={'db_table': 'ai_testing_execution_steps', 'ordering': ['plan_revision_id', 'display_order', 'id']},
        ),
        migrations.CreateModel(
            name='AIExecutionStepAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attempt_number', models.PositiveSmallIntegerField()),
                ('action', models.JSONField(default=dict)),
                ('action_output', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('running', '执行中'), ('completed', '动作完成'), ('failed', '失败'), ('stopped', '已停止')], db_index=True, default='running', max_length=20)),
                ('error_message', models.TextField(blank=True, default='')),
                ('environment_fingerprint', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('permission_fingerprint', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('step', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='ai_testing.aiexecutionstep')),
            ],
            options={'db_table': 'ai_testing_execution_step_attempts', 'ordering': ['step_id', 'attempt_number']},
        ),
        migrations.CreateModel(
            name='AIExecutionEvidenceArtifact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('artifact_type', models.CharField(db_index=True, max_length=64)),
                ('storage_path', models.CharField(blank=True, default='', max_length=1000)),
                ('content_hash', models.CharField(db_index=True, max_length=64)),
                ('metadata', models.JSONField(default=dict)),
                ('captured_at', models.DateTimeField(auto_now_add=True)),
                ('attempt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evidence_artifacts', to='ai_testing.aiexecutionstepattempt')),
            ],
            options={'db_table': 'ai_testing_execution_evidence_artifacts', 'ordering': ['attempt_id', 'id']},
        ),
        migrations.CreateModel(
            name='AIExecutionAssertionResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assertion', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('passed', '通过'), ('failed', '失败'), ('inconclusive', '证据不足'), ('invalid_evidence', '证据无效')], db_index=True, max_length=32)),
                ('actual', models.JSONField(default=dict)),
                ('evaluated_at', models.DateTimeField(auto_now_add=True)),
                ('evidence_artifacts', models.ManyToManyField(related_name='assertion_results', to='ai_testing.aiexecutionevidenceartifact')),
                ('step', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assertion_results', to='ai_testing.aiexecutionstep')),
            ],
            options={'db_table': 'ai_testing_execution_assertion_results', 'ordering': ['step_id', 'id']},
        ),
        migrations.CreateModel(
            name='AIExecutionQualityGateResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('evaluation_number', models.PositiveSmallIntegerField(default=1)),
                ('status', models.CharField(choices=[('passed', '通过'), ('failed', '失败'), ('inconclusive', '证据不足')], db_index=True, max_length=20)),
                ('details', models.JSONField(default=dict)),
                ('evaluated_at', models.DateTimeField(auto_now_add=True)),
                ('plan_revision', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quality_gate_results', to='ai_testing.aiexecutionplanrevision')),
            ],
            options={'db_table': 'ai_testing_execution_quality_gate_results', 'ordering': ['plan_revision_id', 'evaluation_number']},
        ),
        migrations.AddConstraint(
            model_name='aiexecutionplanrevision',
            constraint=models.UniqueConstraint(fields=('execution_record', 'revision_number'), name='ai_testing_execution_plan_revision_unique'),
        ),
        migrations.AddConstraint(
            model_name='aiexecutionstep',
            constraint=models.UniqueConstraint(fields=('plan_revision', 'step_key'), name='ai_testing_execution_step_key_unique'),
        ),
        migrations.AddConstraint(
            model_name='aiexecutionstepattempt',
            constraint=models.UniqueConstraint(fields=('step', 'attempt_number'), name='ai_testing_execution_step_attempt_unique'),
        ),
        migrations.AddConstraint(
            model_name='aiexecutionqualitygateresult',
            constraint=models.UniqueConstraint(fields=('plan_revision', 'evaluation_number'), name='ai_testing_execution_quality_gate_unique'),
        ),
    ]