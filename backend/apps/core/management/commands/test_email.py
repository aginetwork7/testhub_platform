"""
邮件发送测试管理命令
使用方法: python manage.py test_email
"""
from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
from backend.config_loader import config_loader


class Command(BaseCommand):
    help = '测试邮件配置是否正确'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write('TestHub 邮件配置测试工具')
        self.stdout.write('='*60)
        
        # 打印当前配置
        self.print_email_config()
        
        # 获取测试邮箱地址
        test_email_address = self.get_test_email_address()
        
        # 运行测试
        results = []
        
        # 测试1: 简单邮件
        results.append(("简单邮件", self.test_simple_email(test_email_address)))
        
        # 测试2: HTML邮件
        results.append(("HTML邮件", self.test_html_email(test_email_address)))
        
        # 总结
        self.stdout.write('\n' + '='*60)
        self.stdout.write('测试总结')
        self.stdout.write('='*60)
        
        for test_name, success in results:
            status = "✅ 成功" if success else "❌ 失败"
            self.stdout.write(f"{test_name}: {status}")
        
        all_success = all(success for _, success in results)
        
        if all_success:
            self.stdout.write(self.style.SUCCESS('\n🎉 所有测试通过！邮件配置正确。'))
        else:
            self.stdout.write(self.style.WARNING('\n⚠️ 部分测试失败，请检查邮件配置。'))
        
        self.stdout.write('='*60 + '\n')

    def get_test_email_address(self):
        """获取测试邮箱地址"""
        email_config = config_loader.get_email_config()
        test_email = email_config.get('test_email')
        
        if test_email:
            self.stdout.write(f"使用配置文件中的测试邮箱: {test_email}")
            return test_email
        else:
            self.stdout.write(self.style.WARNING("配置文件中未设置 test_email，使用默认测试邮箱"))
            return None

    def print_email_config(self):
        """打印当前邮件配置"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('当前邮件配置')
        self.stdout.write('='*60)
        self.stdout.write(f"邮件后端: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"SMTP服务器: {settings.EMAIL_HOST}")
        self.stdout.write(f"SMTP端口: {settings.EMAIL_PORT}")
        self.stdout.write(f"使用TLS: {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"使用SSL: {settings.EMAIL_USE_SSL}")
        self.stdout.write(f"发件人邮箱: {settings.EMAIL_HOST_USER}")
        password_display = '*' * len(settings.EMAIL_HOST_PASSWORD) if settings.EMAIL_HOST_PASSWORD else '未设置'
        self.stdout.write(f"发件人密码: {password_display}")
        self.stdout.write(f"默认发件人: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"超时时间: {settings.EMAIL_TIMEOUT}秒")
        self.stdout.write('='*60)

    def test_simple_email(self, test_email_address):
        """测试简单邮件发送"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('测试1: 发送简单文本邮件')
        self.stdout.write('='*60)
        
        try:
            email = EmailMessage(
                subject='[TestHub] 邮件配置测试',
                body='这是一封测试邮件，用于验证邮件配置是否正确。\n\n如果您收到这封邮件，说明邮件配置成功！',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[test_email_address],
            )
            email.encoding = 'utf-8'
            
            result = email.send()
            self.stdout.write(self.style.SUCCESS(f"✅ 简单邮件发送成功！返回值: {result}"))
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ 简单邮件发送失败: {e}"))
            import traceback
            traceback.print_exc()
            return False

    def test_html_email(self, test_email_address):
        """测试HTML邮件发送"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('测试2: 发送HTML格式邮件')
        self.stdout.write('='*60)
        
        try:
            current_time = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            
            html_content = '''
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height:1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #007bff; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background: #f8f9fa; margin-top: 20px; }}
                    .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>🎉 邮件配置测试成功！</h2>
                    </div>
                    <div class="content">
                        <p>尊敬的用户，</p>
                        <p>这是一封HTML格式的测试邮件，用于验证邮件配置是否正确。</p>
                        <p><strong>测试信息：</strong></p>
                        <ul>
                            <li>发件人: {from_email}</li>
                            <li>收件人: {to_email}</li>
                            <li>发送时间: {time}</li>
                        </ul>
                        <p>如果您看到这封邮件的格式正确，说明HTML邮件发送功能正常！</p>
                    </div>
                    <div class="footer">
                        <p>此邮件由 TestHub 自动发送，请勿回复。</p>
                    </div>
                </div>
            </body>
            </html>
            '''.format(
                from_email=settings.DEFAULT_FROM_EMAIL,
                to_email=test_email_address,
                time=current_time
            )
            
            email = EmailMultiAlternatives(
                subject='[TestHub] HTML邮件配置测试',
                body='这是一封HTML格式邮件的纯文本版本。',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[test_email_address],
            )
            
            email.encoding = 'utf-8'
            email.content_subtype = 'html'
            
            from email.mime.text import MIMEText
            html_part = MIMEText(html_content, 'html', 'utf-8')
            email.attach(html_part)
            
            result = email.send()
            self.stdout.write(self.style.SUCCESS(f"✅ HTML邮件发送成功！返回值: {result}"))
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ HTML邮件发送失败: {e}"))
            import traceback
            traceback.print_exc()
            return False
