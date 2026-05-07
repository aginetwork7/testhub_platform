# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_update_notification_config_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='unifiednotificationconfig',
            name='email_recipients',
            field=models.JSONField(blank=True, default=list, help_text='邮件收件人列表，可包含用户ID或邮箱地址', verbose_name='邮件收件人'),
        ),
        migrations.AlterField(
            model_name='unifiednotificationconfig',
            name='config_type',
            field=models.CharField(choices=[('webhook_feishu', '飞书机器人'), ('webhook_wechat', '企业微信机器人'), ('webhook_dingtalk', '钉钉机器人'), ('webhook_generic', '通用Webhook'), ('email', '邮件通知')], default='webhook_feishu', max_length=20, verbose_name='配置类型'),
        ),
        migrations.AlterField(
            model_name='unifiednotificationconfig',
            name='name',
            field=models.CharField(help_text='用于标识该配置的名称', max_length=100, verbose_name='名称'),
        ),
        migrations.AlterField(
            model_name='unifiednotificationconfig',
            name='webhook_url',
            field=models.URLField(blank=True, default='', help_text='机器人Webhook地址（飞书/企微/钉钉/通用Webhook需要）', max_length=500, verbose_name='Webhook URL'),
        ),
    ]
