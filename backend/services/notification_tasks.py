"""异步通知任务服务"""
from django_q.tasks import async_task
from django.utils import timezone
import requests
import json
import re
from apps.core.models import NotificationTemplate


class NotificationService:
    """通知服务类"""
    
    def render_template(self, template_content, context):
        """渲染模板
        
        Args:
            template_content: 模板内容
            context: 上下文变量
            
        Returns:
            str: 渲染后的内容
        """
        # 简单的变量替换
        content = template_content
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value) if value is not None else '')
        return content
    
    def get_template(self, template_type, template_id=None):
        """获取模板
        
        Args:
            template_type: 模板类型
            template_id: 模板ID，不指定则使用默认模板
            
        Returns:
            NotificationTemplate: 模板实例
        """
        if template_id:
            try:
                return NotificationTemplate.objects.get(id=template_id, template_type=template_type)
            except NotificationTemplate.DoesNotExist:
                pass
        
        # 使用默认模板
        return NotificationTemplate.get_default_template(template_type)
    
    def send_webhook_notification(self, webhook_url, message, bot_type):
        """发送Webhook通知
        
        Args:
            webhook_url: Webhook URL
            message: 消息内容
            bot_type: 机器人类型
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 钉钉签名已在task_executor.py中处理，这里直接发送
            print(f"[DEBUG] 发送Webhook通知 - bot_type: {bot_type}")
            print(f"[DEBUG] Webhook URL: {webhook_url}")
            print(f"[DEBUG] Message: {message}")
            print(f"[DEBUG] Message JSON: {json.dumps(message, ensure_ascii=False)}")
            
            response = requests.post(
                webhook_url,
                json=message,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            print(f"[DEBUG] Response status: {response.status_code}")
            print(f"[DEBUG] Response body: {response.text}")
            
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"发送Webhook通知失败: {e}")
            return False


# 创建通知服务实例
notification_service = NotificationService()


def _send_webhook_notification_wrapper(webhook_url, message, bot_type):
    """发送Webhook通知的包装函数"""
    return notification_service.send_webhook_notification(webhook_url, message, bot_type)


def send_webhook_notification_task(webhook_url, message, bot_type, group='通知任务'):
    """异步发送Webhook通知
    
    Args:
        webhook_url: Webhook URL
        message: 消息内容
        bot_type: 机器人类型
        group: 任务分组（默认为'通知任务'）
    """
    return async_task(
        _send_webhook_notification_wrapper,
        webhook_url=webhook_url,
        message=message,
        bot_type=bot_type,
        group=group
    )


def _send_task_notification_wrapper(task_name, task_type, status, recipients, details="", execution_time=None, result=None, template_id=None):
    """发送任务通知的包装函数"""
    from services.email_service import email_service
    return email_service.send_task_notification(
        task_name=task_name,
        task_type=task_type,
        status=status,
        recipients=recipients,
        details=details,
        execution_time=execution_time,
        result=result
    )


def send_task_notification_task(task_name, task_type, status, recipients, details="", execution_time=None, result=None, template_id=None):
    """异步发送任务通知
    
    Args:
        task_name: 任务名称
        task_type: 任务类型
        status: 任务状态
        recipients: 收件人
        details: 详细信息
        execution_time: 执行时间
        result: 执行结果
        template_id: 模板ID
        
    Returns:
        str: 任务ID
    """
    # 从task_type中提取模块名称作为分组
    group = '通知任务'
    if task_type:
        if 'API' in task_type:
            group = 'API测试'
        elif 'UI' in task_type:
            group = 'UI测试'
        elif 'APP' in task_type:
            group = 'APP测试'
    
    return async_task(
        _send_task_notification_wrapper,
        task_name,
        task_type,
        status,
        recipients,
        details,
        execution_time,
        result,
        group=group
    )


def send_notification_with_template_task(template_type, template_id, context, recipients=None, webhook_urls=None):
    """使用模板发送通知
    
    Args:
        template_type: 模板类型
        template_id: 模板ID
        context: 上下文变量
        recipients: 收件人列表（邮件通知用）
        webhook_urls: Webhook URL列表（Webhook通知用）
        
    Returns:
        str: 任务ID
    """
    return async_task(
        _send_notification_with_template,
        template_type,
        template_id,
        context,
        recipients,
        webhook_urls
    )


def _send_notification_with_template(template_type, template_id, context, recipients=None, webhook_urls=None):
    """使用模板发送通知（内部函数）
    
    Args:
        template_type: 模板类型
        template_id: 模板ID
        context: 上下文变量
        recipients: 收件人列表（邮件通知用）
        webhook_urls: Webhook URL列表（Webhook通知用）
        
    Returns:
        dict: 发送结果
    """
    try:
        # 获取模板
        template = notification_service.get_template(template_type, template_id)
        if not template:
            return {'success': False, 'message': '模板不存在'}
        
        # 渲染模板
        rendered_content = notification_service.render_template(template.content, context)
        
        # 根据模板类型发送通知
        if template_type == 'email' and recipients:
            from services.email_service import email_service
            success = email_service.send_notification_email(
                subject=context.get('title', '系统通知'),
                message=rendered_content,
                recipients=recipients,
                html_content=None
            )
            return {'success': success, 'message': '邮件通知发送成功' if success else '邮件通知发送失败'}
        
        elif template_type in ['feishu', 'dingtalk', 'wecom'] and webhook_urls:
            results = []
            for webhook_url in webhook_urls:
                # 构建消息格式
                if template_type == 'feishu':
                    message = {
                        'msg_type': 'markdown',
                        'content': {
                            'text': rendered_content
                        }
                    }
                elif template_type == 'dingtalk':
                    message = {
                        'msgtype': 'markdown',
                        'markdown': {
                            'title': context.get('title', '系统通知'),
                            'text': rendered_content
                        }
                    }
                elif template_type == 'wecom':
                    message = {
                        'msgtype': 'markdown',
                        'markdown': {
                            'content': rendered_content
                        }
                    }
                
                # 发送Webhook
                success = notification_service.send_webhook_notification(
                    webhook_url, message, f'webhook_{template_type}'
                )
                results.append({'url': webhook_url, 'success': success})
            
            return {'success': any(r['success'] for r in results), 'results': results}
        
        return {'success': False, 'message': '无效的通知类型或参数'}
        
    except Exception as e:
        return {'success': False, 'message': f'发送通知失败: {str(e)}'}
