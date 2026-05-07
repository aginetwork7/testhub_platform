"""国际化与本地化工具"""
from django.utils import timezone
from django.utils.translation import gettext as _
from django.conf import settings
from datetime import datetime, timedelta
import pytz


class TimezoneHelper:
    """时区处理辅助类"""
    
    @staticmethod
    def get_default_timezone():
        """获取默认时区"""
        return getattr(settings, 'TIME_ZONE', 'Asia/Shanghai')
    
    @staticmethod
    def get_user_timezone(user):
        """获取用户时区"""
        if hasattr(user, 'timezone') and user.timezone:
            return pytz.timezone(user.timezone)
        return pytz.timezone(TimezoneHelper.get_default_timezone())
    
    @staticmethod
    def localize_datetime(dt, timezone_str=None):
        """本地化日期时间"""
        if dt is None:
            return None
        tz_str = timezone_str or TimezoneHelper.get_default_timezone()
        tz = pytz.timezone(tz_str)
        if dt.tzinfo is None:
            return tz.localize(dt)
        return dt.astimezone(tz)
    
    @staticmethod
    def to_user_timezone(dt, user):
        """转换为用户时区"""
        user_tz = TimezoneHelper.get_user_timezone(user)
        if dt.tzinfo is None:
            dt = timezone.make_aware(dt)
        return dt.astimezone(user_tz)
    
    @staticmethod
    def format_datetime(dt, format_str='%Y-%m-%d %H:%M:%S', timezone_str=None):
        """格式化日期时间"""
        tz_str = timezone_str or TimezoneHelper.get_default_timezone()
        localized = TimezoneHelper.localize_datetime(dt, tz_str)
        return localized.strftime(format_str) if localized else ''


class TranslationHelper:
    """翻译辅助类"""
    
    @staticmethod
    def get_translated_choices(choices_dict):
        """获取翻译后的选择项"""
        return [(k, _(v)) for k, v in choices_dict.items()]
    
    @staticmethod
    def get_language_display_name(language_code):
        """获取语言显示名称"""
        languages = getattr(settings, 'LANGUAGES', [
            ('zh-hans', '简体中文'),
            ('en', 'English'),
        ])
        language_dict = dict(languages)
        return language_dict.get(language_code, language_code)
    
    @staticmethod
    def get_supported_languages():
        """获取支持的语言列表"""
        return getattr(settings, 'LANGUAGES', [('zh-hans', '简体中文')])


timezone_helper = TimezoneHelper()
translation_helper = TranslationHelper()
