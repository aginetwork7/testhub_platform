"""邮件异步任务"""
from django_q.tasks import async_task
from .email_service import email_service


def _send_task_notification_wrapper(subject, message, recipients, html_content=None, attachments=None):
    """发送任务通知邮件的包装函数"""
    return email_service.send_task_notification(
        subject=subject,
        message=message,
        recipients=recipients,
        html_content=html_content,
        attachments=attachments
    )


def send_task_notification_task(subject, message, recipients, html_content=None, attachments=None):
    """异步发送任务通知邮件
    
    Args:
        subject: 邮件主题（从模板获取）
        message: 邮件正文纯文本（从模板获取）
        recipients: 收件人列表
        html_content: HTML内容（从模板获取，可选）
        attachments: 附件列表（可选）
    
    Returns:
        str: 任务ID
    """
    return async_task(
        _send_task_notification_wrapper,
        subject,
        message,
        recipients,
        html_content,
        attachments
    )


def _send_notification_email_wrapper(subject, message, recipients, html_content=None, attachments=None, cc=None, bcc=None):
    """发送通知邮件的包装函数"""
    return email_service.send_notification_email(
        subject=subject,
        message=message,
        recipients=recipients,
        html_content=html_content,
        attachments=attachments,
        cc=cc,
        bcc=bcc
    )


def send_notification_email_task(subject, message, recipients, html_content=None, attachments=None, cc=None, bcc=None):
    """异步发送通知邮件
    
    Args:
        subject: 邮件主题
        message: 邮件正文（纯文本）
        recipients: 收件人列表
        html_content: HTML内容（可选）
        attachments: 附件列表（可选）
        cc: 抄送列表（可选）
        bcc: 密送列表（可选）
    
    Returns:
        str: 任务ID
    """
    return async_task(
        _send_notification_email_wrapper,
        subject,
        message,
        recipients,
        html_content,
        attachments,
        cc,
        bcc
    )


def _send_bulk_emails_wrapper(emails):
    """批量发送邮件的包装函数"""
    return email_service.send_bulk_emails(emails)


def send_bulk_emails_task(emails):
    """异步批量发送邮件
    
    Args:
        emails: 邮件列表，每个邮件包含subject, message, to等字段
    
    Returns:
        str: 任务ID
    """
    return async_task(_send_bulk_emails_wrapper, emails)
