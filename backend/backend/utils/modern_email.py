"""Django 6 现代 Email API 工具"""
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.conf import settings
from email.message import EmailMessage as ModernEmailMessage
from email.utils import formataddr, make_msgid
from email.header import Header
import logging
from typing import List, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class ModernEmailSender:
    """Django 6 现代邮件发送器"""
    
    def __init__(self):
        self.default_from_email = settings.DEFAULT_FROM_EMAIL
    
    def send_simple_email(
        self,
        subject: str,
        body: str,
        to: List[str],
        from_email: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[List[str]] = None,
        headers: Optional[dict] = None,
        attachments: Optional[List[dict]] = None,
    ) -> bool:
        """发送简单邮件"""
        try:
            encoded_subject = Header(subject, 'utf-8')
            email = EmailMessage(
                subject=encoded_subject,
                body=body,
                from_email=from_email or self.default_from_email,
                to=to,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
                headers=headers,
            )
            email.encoding = 'utf-8'
            
            if attachments:
                for attachment in attachments:
                    if 'file_path' in attachment:
                        email.attach_file(attachment['file_path'])
                    elif 'content' in attachment:
                        email.attach(
                            attachment.get('filename', 'attachment'),
                            attachment['content'],
                            attachment.get('mimetype', 'text/html')
                        )
            
            email.send()
            return True
        except Exception as e:
            logger.error(f'发送邮件失败: {e}')
            return False
    
    def send_html_email(
        self,
        subject: str,
        text_body: str,
        html_body: str,
        to: List[str],
        from_email: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[List[str]] = None,
        attachments: Optional[List[dict]] = None,
    ) -> bool:
        """发送 HTML 邮件"""
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=from_email or self.default_from_email,
                to=to,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
            )
            
            email.encoding = 'utf-8'
            email.content_subtype = 'plain'
            
            email.attach_alternative(html_body, 'text/html')
            
            if attachments:
                for attachment in attachments:
                    if 'file_path' in attachment:
                        email.attach_file(attachment['file_path'])
                    elif 'content' in attachment:
                        email.attach(
                            attachment.get('filename', 'attachment'),
                            attachment['content'],
                            attachment.get('mimetype', 'text/html')
                        )
            
            email.send()
            return True
        except Exception as e:
            logger.error(f'发送HTML邮件失败: {e}', exc_info=True)
            return False
    
    def send_template_email(
        self,
        subject: str,
        template_name: str,
        context: dict,
        to: List[str],
        from_email: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> bool:
        """发送模板邮件"""
        try:
            from django.template.loader import render_to_string
            
            text_body = render_to_string(f'{template_name}.txt', context)
            html_body = render_to_string(f'{template_name}.html', context)
            
            return self.send_html_email(
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                to=to,
                from_email=from_email,
                cc=cc,
                bcc=bcc,
            )
        except Exception as e:
            logger.error(f'发送模板邮件失败: {e}')
            return False
    
    def send_with_attachments(
        self,
        subject: str,
        body: str,
        to: List[str],
        attachments: List[Union[str, Path]],
        from_email: Optional[str] = None,
    ) -> bool:
        """发送带附件的邮件"""
        try:
            encoded_subject = Header(subject, 'utf-8')
            email = EmailMessage(
                subject=encoded_subject,
                body=body,
                from_email=from_email or self.default_from_email,
                to=to,
            )
            email.encoding = 'utf-8'
            
            for attachment in attachments:
                path = Path(attachment) if isinstance(attachment, str) else attachment
                if path.exists():
                    email.attach_file(str(path))
            
            email.send()
            return True
        except Exception as e:
            logger.error(f'发送带附件邮件失败: {e}')
            return False
    
    async def send_email_async(
        self,
        subject: str,
        body: str,
        to: List[str],
        from_email: Optional[str] = None,
    ) -> bool:
        """异步发送邮件"""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(
                executor,
                self.send_simple_email,
                subject,
                body,
                to,
                from_email
            )
        return result


class TestReportEmailSender:
    """测试报告邮件发送器"""
    
    def __init__(self):
        self.email_sender = ModernEmailSender()
    
    def send_test_report(
        self,
        report_title: str,
        report_summary: dict,
        recipients: List[str],
        report_url: Optional[str] = None,
        attachment_path: Optional[str] = None,
    ) -> bool:
        """发送测试报告邮件"""
        subject = f'[TestHub] 测试报告 - {report_title}'
        
        text_body = self._generate_text_report(report_title, report_summary, report_url)
        html_body = self._generate_html_report(report_title, report_summary, report_url)
        
        attachments = []
        if attachment_path:
            attachments.append({'file_path': attachment_path})
        
        return self.email_sender.send_html_email(
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            to=recipients,
            attachments=attachments if attachments else None,
        )
    
    def _generate_text_report(self, title: str, summary: dict, url: Optional[str]) -> str:
        """生成文本格式报告"""
        lines = [
            f'测试报告: {title}',
            '=' * 50,
            f'总用例数: {summary.get("total", 0)}',
            f'通过数: {summary.get("passed", 0)}',
            f'失败数: {summary.get("failed", 0)}',
            f'跳过数: {summary.get("skipped", 0)}',
            f'通过率: {summary.get("pass_rate", 0):.2f}%',
        ]
        
        if url:
            lines.extend([
                '',
                f'详细报告: {url}',
            ])
        
        return '\n'.join(lines)
    
    def _generate_html_report(self, title: str, summary: dict, url: Optional[str]) -> str:
        """生成 HTML 格式报告"""
        pass_rate = summary.get('pass_rate', 0)
        color = 'green' if pass_rate >= 80 else 'orange' if pass_rate >= 60 else 'red'
        
        html = f'''
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">测试报告: {title}</h2>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background-color: #f5f5f5;">
                    <td style="padding: 10px; border: 1px solid #ddd;">总用例数</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{summary.get("total", 0)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;">通过数</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: green;">{summary.get("passed", 0)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;">失败数</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: red;">{summary.get("failed", 0)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;">跳过数</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: orange;">{summary.get("skipped", 0)}</td>
                </tr>
                <tr style="background-color: #f5f5f5;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">通过率</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; font-weight: bold; color: {color};">{pass_rate:.2f}%</td>
                </tr>
            </table>
        '''
        
        if url:
            html += f'''
            <p style="text-align: center;">
                <a href="{url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">查看详细报告</a>
            </p>
            '''
        
        html += '''
        </body>
        </html>
        '''
        
        return html


modern_email_sender = ModernEmailSender()
test_report_email_sender = TestReportEmailSender()
