from django.core.mail.backends.smtp import EmailBackend
from django.conf import settings
import ssl
import smtplib
import base64


class CustomEmailBackend(EmailBackend):
    def open(self):
        """打开SMTP连接，使用自定义SSL上下文"""
        if self.connection:
            return False
        
        ssl_context = ssl._create_unverified_context()
        
        try:
            if self.use_ssl:
                self.connection = smtplib.SMTP_SSL(
                    self.host, 
                    self.port, 
                    context=ssl_context,
                    timeout=self.timeout
                )
            else:
                self.connection = smtplib.SMTP(
                    self.host, 
                    self.port, 
                    timeout=self.timeout
                )
                if self.use_tls:
                    self.connection.starttls(context=ssl_context)
            
            if self.username and self.password:
                self._login_utf8()
            return True
        except Exception:
            if not self.fail_silently:
                raise
    
    def _login_utf8(self):
        """支持UTF-8编码的用户名和密码登录"""
        try:
            self.connection.ehlo_or_helo_if_needed()
            
            auth_methods = self.connection.esmtp_features.get('AUTH', '').split()
            
            if 'LOGIN' in auth_methods:
                self.connection.docmd('AUTH LOGIN')
                self.connection.docmd(base64.b64encode(self.username.encode('utf-8')).decode('ascii'))
                self.connection.docmd(base64.b64encode(self.password.encode('utf-8')).decode('ascii'))
            else:
                auth_string = f'\x00{self.username}\x00{self.password}'
                self.connection.docmd('AUTH PLAIN', base64.b64encode(auth_string.encode('utf-8')).decode('ascii'))
        except smtplib.SMTPAuthenticationError as e:
            raise smtplib.SMTPAuthenticationError(e.smtp_code, e.smtp_error)
