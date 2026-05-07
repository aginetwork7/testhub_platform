"""
Core 应用视图
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import UnifiedNotificationConfig, NotificationTemplate
from .serializers import UnifiedNotificationConfigSerializer, NotificationTemplateSerializer

import logging
import requests
import json
import time
import hmac
import hashlib
import base64
import re
from urllib.parse import quote_plus
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    """通知模板视图集"""
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['template_type', 'is_default', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        """创建通知模板"""
        instance = serializer.save(created_by=self.request.user)
        logger.info(f"创建通知模板: {instance.name}")

    def perform_update(self, serializer):
        """更新通知模板"""
        instance = serializer.save()
        logger.info(f"更新通知模板: {instance.name}")

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """设置为默认模板"""
        template = self.get_object()
        NotificationTemplate.objects.filter(
            template_type=template.template_type,
            is_default=True
        ).update(is_default=False)
        template.is_default = True
        template.save()
        return Response({'message': '已设置为默认模板'})


class UnifiedNotificationConfigViewSet(viewsets.ModelViewSet):
    """统一通知配置视图集"""
    queryset = UnifiedNotificationConfig.objects.all()
    serializer_class = UnifiedNotificationConfigSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['config_type', 'is_default', 'is_active']
    search_fields = ['name']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        """创建通知配置"""
        instance = serializer.save(created_by=self.request.user)
        logger.info(f"创建通知配置: {instance.name} - {instance.get_config_type_display()}")

    def perform_update(self, serializer):
        """更新通知配置"""
        instance = serializer.save()
        logger.info(f"更新通知配置: {instance.name}")

    def perform_destroy(self, instance):
        """删除通知配置"""
        logger.info(f"删除通知配置: {instance.name}")
        instance.delete()

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """设置为默认配置"""
        config = self.get_object()
        UnifiedNotificationConfig.objects.filter(
            config_type=config.config_type,
            is_default=True
        ).update(is_default=False)
        config.is_default = True
        config.save()
        return Response({'message': '已设置为默认配置'})

    @action(detail=False, methods=['get'])
    def active_configs(self, request):
        """获取所有启用的配置"""
        configs = UnifiedNotificationConfig.objects.filter(is_active=True)
        serializer = self.get_serializer(configs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def test_send(self, request, pk=None):
        """测试发送通知消息"""
        config = self.get_object()
        
        if not config.is_active:
            return Response({'success': False, 'message': '该配置已禁用，请先启用'}, status=status.HTTP_400_BAD_REQUEST)
        
        test_message = {
            'title': '测试通知',
            'content': f'这是一条测试消息，来自 TestHub 平台。\n\n配置名称: {config.name}\n发送时间: {time.strftime("%Y-%m-%d %H:%M:%S")}'
        }
        
        try:
            if config.config_type == 'webhook_feishu':
                result = self._send_feishu(config.webhook_url, test_message, config)
            elif config.config_type == 'webhook_wechat':
                result = self._send_wechat(config.webhook_url, test_message, config)
            elif config.config_type == 'webhook_dingtalk':
                result = self._send_dingtalk(config.webhook_url, config.secret, test_message, config)
            elif config.config_type == 'webhook_generic':
                result = self._send_generic(config.webhook_url, test_message, config)
            elif config.config_type == 'email':
                result = self._send_email(config, test_message)
            else:
                return Response({'success': False, 'message': f'不支持的通知类型: {config.config_type}'}, status=status.HTTP_400_BAD_REQUEST)
            
            if result['success']:
                logger.info(f"测试通知发送成功: {config.name}")
                return Response({'success': True, 'message': result.get('message', '测试消息发送成功')})
            else:
                logger.error(f"测试通知发送失败: {config.name} - {result.get('message')}")
                return Response({'success': False, 'message': result.get('message', '发送失败')}, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"测试通知发送异常: {config.name} - {str(e)}")
            return Response({'success': False, 'message': f'发送异常: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _send_feishu(self, webhook_url, message, config=None):
        """发送飞书消息"""
        try:
            # 清理webhook_url
            webhook_url = webhook_url.strip().strip('`').strip()
            
            logger.info(f"[DEBUG] 飞书Webhook - URL: {webhook_url}")
            logger.info(f"[DEBUG] 飞书Webhook - Message: {message}")
            
            # 判断是否为测试通知
            is_test_notification = '这是一条测试消息' in message.get('content', '')
            
            # 判断是否使用消息模板
            use_template = config and config.notification_template and not is_test_notification
            
            if is_test_notification:
                # 测试通知：使用飞书特有的交互式卡片格式
                payload = {
                    "msg_type": "interactive",
                    "card": {
                        "header": {
                            "title": {
                                "tag": "plain_text",
                                "content": message['title']
                            },
                            "template": "blue"
                        },
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "plain_text",
                                    "content": message['content']
                                }
                            }
                        ]
                    }
                }
            elif use_template:
                # 实际通知：使用消息模板
                template = config.notification_template
                content = template.content
                
                # 替换message中的变量
                for key, value in message.items():
                    content = content.replace(f'{{{{{key}}}}}', str(value))
                
                # 替换常用变量
                send_time = time.strftime("%Y-%m-%d %H:%M:%S")
                content = content.replace('{{config_name}}', config.name)
                content = content.replace('{{send_time}}', send_time)
                
                # 替换未定义的变量为空字符串或默认值
                undefined_vars = re.findall(r'\{\{(\w+)\}\}', content)
                default_values = {
                    'executor': '系统',
                    'start_time': send_time,
                    'execution_time': 'N/A',
                    'total_cases': '0',
                    'passed_cases': '0',
                    'failed_cases': '0',
                    'error_cases': '0',
                    'skipped_cases': '0',
                    'pass_rate': '0%',
                    'task_name': '测试任务',
                    'task_type': '测试通知',
                    'status': 'N/A',
                    'details': '这是一条测试消息',
                    'result': 'N/A'
                }
                
                for var in undefined_vars:
                    if var not in message:
                        content = content.replace(f'{{{{{var}}}}}', default_values.get(var, ''))
                
                # 根据模板类型选择飞书消息格式
                if template.template_type == 'text':
                    payload = {
                        "msg_type": "text",
                        "content": {
                            "text": content
                        }
                    }
                else:
                    payload = {
                        "msg_type": "interactive",
                        "card": {
                            "header": {
                                "title": {
                                    "tag": "plain_text",
                                    "content": message['title']
                                },
                                "template": "blue"
                            },
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "plain_text",
                                        "content": content
                                    }
                                }
                            ]
                        }
                    }
            else:
                # 实际通知：使用交互式卡片格式
                payload = {
                    "msg_type": "interactive",
                    "card": {
                        "header": {
                            "title": {
                                "tag": "plain_text",
                                "content": message['title']
                            },
                            "template": "blue"
                        },
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "plain_text",
                                    "content": message['content']
                                }
                            }
                        ]
                    }
                }
            
            logger.info(f"[DEBUG] 飞书Webhook - Payload: {json.dumps(payload, ensure_ascii=False)}")
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            result = response.json()
            
            logger.info(f"[DEBUG] 飞书Webhook - Response status: {response.status_code}")
            logger.info(f"[DEBUG] 飞书Webhook - Response body: {response.text}")
            
            if result.get('StatusCode') == 0 or result.get('code') == 0:
                return {'success': True}
            else:
                return {'success': False, 'message': result.get('msg', str(result))}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def _send_wechat(self, webhook_url, message, config=None):
        """发送企业微信消息"""
        try:
            # 清理webhook_url
            webhook_url = webhook_url.strip().strip('`').strip()
            
            logger.info(f"[DEBUG] 企微Webhook - URL: {webhook_url}")
            logger.info(f"[DEBUG] 企微Webhook - Message: {message}")
            
            # 判断是否为测试通知
            is_test_notification = '这是一条测试消息' in message.get('content', '')
            
            # 判断是否使用消息模板
            use_template = config and config.notification_template and not is_test_notification
            
            if is_test_notification:
                # 测试通知：使用企业微信特有的Markdown格式
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "content": f"### {message['title']}\n\n{message['content']}"
                    }
                }
            elif use_template:
                # 实际通知：使用消息模板
                template = config.notification_template
                content = template.content
                
                # 替换message中的变量
                for key, value in message.items():
                    content = content.replace(f'{{{{{key}}}}}', str(value))
                
                # 替换常用变量
                send_time = time.strftime("%Y-%m-%d %H:%M:%S")
                content = content.replace('{{config_name}}', config.name)
                content = content.replace('{{send_time}}', send_time)
                
                # 替换未定义的变量为空字符串或默认值
                undefined_vars = re.findall(r'\{\{(\w+)\}\}', content)
                default_values = {
                    'executor': '系统',
                    'start_time': send_time,
                    'execution_time': 'N/A',
                    'total_cases': '0',
                    'passed_cases': '0',
                    'failed_cases': '0',
                    'error_cases': '0',
                    'skipped_cases': '0',
                    'pass_rate': '0%',
                    'task_name': '测试任务',
                    'task_type': '测试通知',
                    'status': 'N/A',
                    'details': '这是一条测试消息',
                    'result': 'N/A'
                }
                
                for var in undefined_vars:
                    if var not in message:
                        content = content.replace(f'{{{{{var}}}}}', default_values.get(var, ''))
                
                # 根据模板类型选择企业微信消息格式
                if template.template_type == 'text':
                    payload = {
                        "msgtype": "text",
                        "text": {
                            "content": content
                        }
                    }
                else:
                    payload = {
                        "msgtype": "markdown",
                        "markdown": {
                            "content": f"### {message['title']}\n\n{content}"
                        }
                    }
            else:
                # 实际通知：使用Markdown格式
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "content": f"### {message['title']}\n\n{message['content']}"
                    }
                }
            
            logger.info(f"[DEBUG] 企微Webhook - Payload: {json.dumps(payload, ensure_ascii=False)}")
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            result = response.json()
            
            logger.info(f"[DEBUG] 企微Webhook - Response status: {response.status_code}")
            logger.info(f"[DEBUG] 企微Webhook - Response body: {response.text}")
            
            if result.get('errcode') == 0:
                return {'success': True}
            else:
                return {'success': False, 'message': result.get('errmsg', str(result))}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def _send_dingtalk(self, webhook_url, secret, message, config=None):
        """发送钉钉消息"""
        try:
            # 清理webhook_url
            webhook_url = webhook_url.strip().strip('`').strip()
            url = webhook_url
            
            if secret:
                timestamp = str(round(time.time() * 1000))
                string_to_sign = f"{timestamp}\n{secret}"
                hmac_code = hmac.new(
                    secret.encode('utf-8'),
                    string_to_sign.encode('utf-8'),
                    digestmod=hashlib.sha256
                ).digest()
                sign = quote_plus(base64.b64encode(hmac_code))
                url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"
            
            logger.info(f"[DEBUG] 钉钉Webhook - URL: {url}")
            logger.info(f"[DEBUG] 钉钉Webhook - Message: {message}")
            
            # 判断是否为测试通知
            is_test_notification = '这是一条测试消息' in message.get('content', '')
            
            # 判断是否使用消息模板
            use_template = config and config.notification_template and not is_test_notification
            
            if is_test_notification:
                # 测试通知：使用钉钉特有的Markdown格式
                content = f"### {message['title']}\n\n"
                content += message['content'].replace('\n', '\n\n')
                
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": message['title'],
                        "text": content
                    }
                }
            elif use_template:
                # 实际通知：使用消息模板
                template = config.notification_template
                content = template.content
                
                # 替换message中的变量
                for key, value in message.items():
                    content = content.replace(f'{{{{{key}}}}}', str(value))
                
                # 替换常用变量
                send_time = time.strftime("%Y-%m-%d %H:%M:%S")
                content = content.replace('{{config_name}}', config.name)
                content = content.replace('{{send_time}}', send_time)
                
                # 替换未定义的变量为空字符串或默认值
                undefined_vars = re.findall(r'\{\{(\w+)\}\}', content)
                default_values = {
                    'executor': '系统',
                    'start_time': send_time,
                    'execution_time': 'N/A',
                    'total_cases': '0',
                    'passed_cases': '0',
                    'failed_cases': '0',
                    'error_cases': '0',
                    'skipped_cases': '0',
                    'pass_rate': '0%',
                    'task_name': '测试任务',
                    'task_type': '测试通知',
                    'status': 'N/A',
                    'details': '这是一条测试消息',
                    'result': 'N/A'
                }
                
                for var in undefined_vars:
                    if var not in message:
                        content = content.replace(f'{{{{{var}}}}}', default_values.get(var, ''))
                
                # 根据模板类型选择钉钉消息格式
                if template.template_type == 'text':
                    payload = {
                        "msgtype": "text",
                        "text": {
                            "content": content
                        }
                    }
                else:
                    markdown_content = f"### {message['title']}\n\n"
                    markdown_content += content.replace('\n', '\n\n')
                    
                    payload = {
                        "msgtype": "markdown",
                        "markdown": {
                            "title": message['title'],
                            "text": markdown_content
                        }
                    }
            else:
                # 实际通知：使用Markdown格式
                content = f"### {message['title']}\n\n"
                content += message['content'].replace('\n', '\n\n')
                
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": message['title'],
                        "text": content
                    }
                }
            
            logger.info(f"[DEBUG] 钉钉Webhook - Payload: {json.dumps(payload, ensure_ascii=False)}")
            
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            
            logger.info(f"[DEBUG] 钉钉Webhook - Response status: {response.status_code}")
            logger.info(f"[DEBUG] 钉钉Webhook - Response body: {response.text}")
            
            if result.get('errcode') == 0:
                return {'success': True}
            else:
                return {'success': False, 'message': result.get('errmsg', str(result))}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def _send_generic(self, webhook_url, message, config=None):
        """发送通用 Webhook 消息"""
        try:
            # 清理webhook_url
            webhook_url = webhook_url.strip().strip('`').strip()
            
            # 判断是否为测试通知
            is_test_notification = '这是一条测试消息' in message.get('content', '')
            
            # 判断是否使用消息模板
            use_template = config and config.notification_template and not is_test_notification
            
            if is_test_notification:
                # 测试通知：使用简单格式
                payload = {
                    "title": message['title'],
                    "content": message['content'],
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "test"
                }
            elif use_template:
                # 实际通知：使用消息模板
                template = config.notification_template
                content = template.content
                
                # 替换message中的变量
                for key, value in message.items():
                    content = content.replace(f'{{{{{key}}}}}', str(value))
                
                # 替换常用变量
                send_time = time.strftime("%Y-%m-%d %H:%M:%S")
                content = content.replace('{{config_name}}', config.name)
                content = content.replace('{{send_time}}', send_time)
                
                # 替换未定义的变量为空字符串或默认值
                undefined_vars = re.findall(r'\{\{(\w+)\}\}', content)
                default_values = {
                    'executor': '系统',
                    'start_time': send_time,
                    'execution_time': 'N/A',
                    'total_cases': '0',
                    'passed_cases': '0',
                    'failed_cases': '0',
                    'error_cases': '0',
                    'skipped_cases': '0',
                    'pass_rate': '0%',
                    'task_name': '测试任务',
                    'task_type': '测试通知',
                    'status': 'N/A',
                    'details': '这是一条测试消息',
                    'result': 'N/A'
                }
                
                for var in undefined_vars:
                    if var not in message:
                        content = content.replace(f'{{{{{var}}}}}', default_values.get(var, ''))
                
                # 实际通知：使用标准格式
                payload = {
                    "title": message['title'],
                    "content": content,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "notification",
                    "template_type": template.template_type
                }
            else:
                # 实际通知：使用标准格式
                payload = {
                    "title": message['title'],
                    "content": message['content'],
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "notification"
                }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code >= 200 and response.status_code < 300:
                return {'success': True}
            else:
                return {'success': False, 'message': f'HTTP {response.status_code}: {response.text[:200]}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def _send_email(self, config, message):
        """发送邮件通知（异步）"""
        try:
            if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
                return {'success': False, 'message': '邮件服务未配置，请在 config.yaml 中配置 SMTP 信息'}
            
            recipients = config.get_email_recipients()
            if not recipients:
                return {'success': False, 'message': '未配置有效的邮件收件人'}
            
            send_time = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 判断是否为测试通知（与其他平台保持一致）
            is_test_notification = '这是一条测试消息' in message.get('content', '')
            
            if is_test_notification or not config.notification_template:
                # 测试通知或无模板：使用简单文本格式，与其他平台保持一致
                subject = f"[TestHub] {message['title']}"
                content = message['content']
                
                # 生成简单的HTML邮件内容
                html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .title {{ font-size: 18px; font-weight: bold; margin-bottom: 15px; color: #409eff; }}
        .content {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; border: 1px solid #e9ecef; }}
        .footer {{ margin-top: 20px; padding-top: 15px; border-top: 1px solid #e9ecef; font-size: 12px; color: #6c757d; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="title">{message['title']}</div>
        <div class="content">
            {content.replace(chr(10), '<br>')}
        </div>
        <div class="footer">
            <p>此邮件由 TestHub 平台自动发送，请勿回复。</p>
        </div>
    </div>
</body>
</html>
"""
            else:
                # 实际通知：使用邮件模板
                template = config.notification_template
                subject = template.subject or f"[TestHub] {message['title']}"
                content = template.content
                
                # 替换message中的变量
                for key, value in message.items():
                    content = content.replace(f'{{{{{key}}}}}', str(value))
                
                # 替换常用变量
                content = content.replace('{{config_name}}', config.name)
                content = content.replace('{{send_time}}', send_time)
                
                # 替换未定义的变量为空字符串或默认值
                undefined_vars = re.findall(r'\{\{(\w+)\}\}', content)
                default_values = {
                    'executor': '系统',
                    'start_time': send_time,
                    'execution_time': 'N/A',
                    'total_cases': '0',
                    'passed_cases': '0',
                    'failed_cases': '0',
                    'error_cases': '0',
                    'skipped_cases': '0',
                    'pass_rate': '0%',
                    'task_name': '测试任务',
                    'task_type': '测试通知',
                    'status': 'N/A',
                    'details': '这是一条测试消息',
                    'result': 'N/A'
                }
                
                for var in undefined_vars:
                    if var not in message:
                        content = content.replace(f'{{{{{var}}}}}', default_values.get(var, ''))
                
                # 生成标准HTML邮件内容
                html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #409eff; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
        .content {{ padding: 20px; background-color: #f9f9f9; border: 1px solid #e9ecef; }}
        .footer {{ margin-top: 20px; padding-top: 15px; border-top: 1px solid #e9ecef; font-size: 12px; color: #6c757d; }}
        .info {{ background-color: #e7f3ff; padding: 10px; border-radius: 5px; margin: 10px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin: 0;">{message['title']}</h2>
        </div>
        <div class="content">
            <p>{content.replace(chr(10), '<br>')}</p>
            <div class="info">
                <p><strong>发送时间:</strong> {send_time}</p>
                <p><strong>配置名称:</strong> {config.name}</p>
            </div>
        </div>
        <div class="footer">
            <p>此邮件由 TestHub 平台自动发送，请勿回复。</p>
        </div>
    </div>
</body>
</html>
"""
            
            from django_q.tasks import async_task
            from services.email_service import email_service
            
            async_task(
                'services.email_service.email_service.send_notification_email',
                subject=subject,
                message=content,
                recipients=recipients,
                html_content=html_message,
                q_options={'group': '邮件通知'}
            )
            
            return {'success': True, 'message': f'测试邮件已加入发送队列，收件人: {", ".join(recipients)}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """按类型获取配置"""
        config_type = request.query_params.get('config_type')
        if not config_type:
            return Response({'error': '请提供config_type参数'}, status=status.HTTP_400_BAD_REQUEST)
        
        configs = UnifiedNotificationConfig.objects.filter(
            config_type=config_type,
            is_active=True
        )
        serializer = self.get_serializer(configs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def for_business(self, request):
        """获取指定业务类型的配置"""
        business_type = request.query_params.get('business_type')
        if not business_type:
            return Response({'error': '请提供business_type参数'}, status=status.HTTP_400_BAD_REQUEST)
        
        configs = UnifiedNotificationConfig.objects.filter(is_active=True)
        
        if business_type == 'ui_automation':
            configs = configs.filter(enable_ui_automation=True)
        elif business_type == 'api_testing':
            configs = configs.filter(enable_api_testing=True)
        elif business_type == 'app_automation':
            configs = configs.filter(enable_app_automation=True)
        
        serializer = self.get_serializer(configs, many=True)
        return Response(serializer.data)
