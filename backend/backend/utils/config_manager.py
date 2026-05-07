"""配置与部署工具"""
import os
from pathlib import Path
from django.conf import settings


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.base_dir = Path(settings.BASE_DIR)
    
    def get_env_config(self, key, default=None, cast=None):
        """获取环境变量配置"""
        value = os.environ.get(key, default)
        if value is not None and cast:
            try:
                return cast(value)
            except (ValueError, TypeError):
                return default
        return value
    
    def get_path_config(self, relative_path):
        """获取路径配置"""
        return self.base_dir / relative_path
    
    def ensure_dir(self, path):
        """确保目录存在"""
        Path(path).mkdir(parents=True, exist_ok=True)
        return path


class StaticFilesManager:
    """静态文件管理器"""
    
    def __init__(self):
        self.static_url = settings.STATIC_URL
        self.static_root = Path(settings.STATIC_ROOT)
        self.media_url = settings.MEDIA_URL
        self.media_root = Path(settings.MEDIA_ROOT)
    
    def get_static_path(self, relative_path):
        """获取静态文件路径"""
        return self.static_root / relative_path
    
    def get_media_path(self, relative_path):
        """获取媒体文件路径"""
        return self.media_root / relative_path
    
    def get_static_url(self, relative_path):
        """获取静态文件 URL"""
        return f"{self.static_url}{relative_path}"
    
    def get_media_url(self, relative_path):
        """获取媒体文件 URL"""
        return f"{self.media_url}{relative_path}"


config_manager = ConfigManager()
static_files_manager = StaticFilesManager()
