"""统一邮件发送服务"""
from backend.utils.modern_email import ModernEmailSender
from backend.log_config import get_logger
from django.conf import settings
from typing import List, Optional, Dict, Any

logger = get_logger('email')


class EmailService:
    """统一邮件发送服务"""
    
    def __init__(self):
        self.email_sender = ModernEmailSender()
        self.default_from_email = settings.DEFAULT_FROM_EMAIL
    
    def send_notification_email(
        self,
        subject: str,
        message: str,
        recipients: List[str],
        html_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """发送通知邮件
        
        Args:
            subject: 邮件主题
            message: 邮件正文（纯文本）
            recipients: 收件人列表
            html_content: HTML内容（可选）
            attachments: 附件列表（可选）
            cc: 抄送列表（可选）
            bcc: 密送列表（可选）
        
        Returns:
            bool: 是否发送成功
        """
        try:
            logger.info(f"准备发送邮件: 主题='{subject}', 收件人={recipients}")
            
            if not recipients:
                logger.warning("收件人列表为空，跳过邮件发送")
                return False
            
            if html_content:
                # 发送HTML邮件
                result = self.email_sender.send_html_email(
                    subject=subject,
                    text_body=message,
                    html_body=html_content,
                    to=recipients,
                    cc=cc,
                    bcc=bcc,
                    attachments=attachments
                )
            else:
                # 发送纯文本邮件
                result = self.email_sender.send_simple_email(
                    subject=subject,
                    body=message,
                    to=recipients,
                    cc=cc,
                    bcc=bcc,
                    attachments=attachments
                )
            
            if result:
                logger.info(f"邮件发送成功: 主题='{subject}'")
            else:
                logger.error(f"邮件发送失败: 主题='{subject}'")
            
            return result
            
        except Exception as e:
            logger.error(f"邮件发送异常: 主题='{subject}', 错误={str(e)}", exc_info=True)
            return False
    
    def send_task_notification(
        self,
        subject: str,
        message: str,
        recipients: List[str],
        html_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """发送任务通知邮件
        
        Args:
            subject: 邮件主题（从模板获取）
            message: 邮件正文纯文本（从模板获取）
            recipients: 收件人列表
            html_content: HTML内容（从模板获取，可选）
            attachments: 附件列表（可选）
        
        Returns:
            bool: 是否发送成功
        """
        return self.send_notification_email(
            subject=subject,
            message=message,
            html_content=html_content,
            recipients=recipients,
            attachments=attachments
        )
    
    def send_bulk_emails(self, emails: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量发送邮件
        
        Args:
            emails: 邮件列表，每个邮件包含subject, message, to等字段
        
        Returns:
            Dict: 发送结果统计
        """
        total = len(emails)
        success_count = 0
        failed_count = 0
        failed_emails = []
        
        for email_data in emails:
            try:
                subject = email_data.get('subject', '')
                message = email_data.get('message', '')
                to = email_data.get('to', [])
                html_content = email_data.get('html_content')
                
                if self.send_notification_email(
                    subject=subject,
                    message=message,
                    recipients=to,
                    html_content=html_content
                ):
                    success_count += 1
                else:
                    failed_count += 1
                    failed_emails.append({
                        'subject': subject,
                        'to': to
                    })
            except Exception as e:
                logger.error(f"批量发送邮件异常: {str(e)}", exc_info=True)
                failed_count += 1
                failed_emails.append({
                    'subject': email_data.get('subject', ''),
                    'to': email_data.get('to', [])
                })
        
        result = {
            'total': total,
            'success': success_count,
            'failed': failed_count,
            'failed_emails': failed_emails
        }
        
        logger.info(f"批量邮件发送完成: {result}")
        return result


# 全局邮件服务实例
email_service = EmailService()
