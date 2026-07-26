"""
配置加载器模块
用于从 YAML 配置文件加载配置
"""
import os
import yaml
from pathlib import Path


class ConfigLoader:
    """配置加载器类"""

    def __init__(self, config_file=None):
        """
        初始化配置加载器
        :param config_file: 配置文件路径，默认为项目根目录下的 config.yaml
        """
        if config_file is None:
            # 获取项目根目录（向上查找包含config.yaml的目录）
            current_path = Path(__file__).resolve().parent
            while current_path != current_path.parent:
                config_path = current_path / 'config.yaml'
                if config_path.is_file() and config_path.stat().st_size > 0:
                    self.project_root = current_path
                    config_file = config_path
                    break
                current_path = current_path.parent
            else:
                # 如果没找到，使用默认位置
                self.project_root = Path(__file__).resolve().parent.parent
                config_file = self.project_root / 'config.yaml'
        else:
            # 如果指定了配置文件，设置项目根目录为配置文件的父目录
            self.project_root = Path(config_file).parent

        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self):
        """加载 YAML 配置文件"""
        if not os.path.exists(self.config_file):
            # 如果配置文件不存在，返回空字典
            return {}

        with open(self.config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def get(self, key_path, default=None, cast=None):
        """
        获取配置项
        :param key_path: 配置键路径，如 'server.backend_port'
        :param default: 默认值
        :param cast: 类型转换函数
        :return: 配置值
        """
        keys = key_path.split('.')
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        # 类型转换
        if cast is not None and value is not None:
            try:
                return cast(value)
            except (ValueError, TypeError):
                return default

        return value

    def get_server_config(self):
        """获取服务器配置"""
        return self.config.get('server', {})

    def get_database_config(self):
        """获取数据库配置"""
        return self.config.get('database', {})

    def get_redis_config(self):
        """获取 Redis 配置"""
        return self.config.get('redis', {})

    def get_cache_config(self):
        """获取缓存配置"""
        return self.config.get('cache', {})

    def get_logging_config(self):
        """获取日志配置"""
        return self.config.get('logging', {})

    def get_jwt_config(self):
        """获取 JWT 配置"""
        return self.config.get('jwt', {})

    def get_throttling_config(self):
        """获取速率限制配置"""
        return self.config.get('throttling', {})

    def get_cors_config(self):
        """获取 CORS 配置"""
        return self.config.get('cors', {})

    def get_email_config(self):
        """获取邮件配置"""
        return self.config.get('email', {})

    def get_allure_config(self):
        """获取 Allure 配置"""
        return self.config.get('allure', {})

    def get_paths_config(self):
        """获取路径配置"""
        return self.config.get('paths', {})

    def get_timeouts_config(self):
        """获取超时配置"""
        return self.config.get('timeouts', {})


# 创建全局配置加载器实例
config_loader = ConfigLoader()
