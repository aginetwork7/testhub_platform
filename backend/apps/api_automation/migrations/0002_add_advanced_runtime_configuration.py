from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api_automation', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiautomationcase',
            name='capabilities',
            field=models.JSONField(default=list, verbose_name='运行能力依赖'),
        ),
        migrations.AddField(
            model_name='apiautomationconfiguration',
            name='auth_profiles',
            field=models.JSONField(default=dict, verbose_name='认证角色配置'),
        ),
        migrations.AddField(
            model_name='apiautomationconfiguration',
            name='payment_config',
            field=models.JSONField(default=dict, verbose_name='支付服务配置'),
        ),
        migrations.AddField(
            model_name='apiautomationconfiguration',
            name='model_profiles',
            field=models.JSONField(default=dict, verbose_name='模型服务配置'),
        ),
        migrations.AlterField(
            model_name='apiautomationstep',
            name='step_type',
            field=models.CharField(
                choices=[
                    ('AUTHENTICATE', '认证'),
                    ('HTTP_REQUEST', 'HTTP请求'),
                    ('WEBSOCKET_REQUEST', 'WebSocket请求'),
                    ('PAYMENT_ACTION', '支付操作'),
                    ('MODEL_REQUEST', '模型请求'),
                    ('PYTHON', 'Python代码'),
                ],
                max_length=30,
                verbose_name='步骤类型',
            ),
        ),
    ]