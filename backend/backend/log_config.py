"""
Loguru日志配置模块，提供统一的日志接口
"""
import sys
import os
import logging
from pathlib import Path

from loguru import logger

from .config_loader import config_loader

logging_config = config_loader.get_logging_config()

def exclude_errors(record):
    """过滤器：过滤掉 ERROR 级别的日志"""
    return record["level"].name != "ERROR"


def only_errors(record):
    """过滤器：只记录 ERROR 级别的日志"""
    return record["level"].name == "ERROR"


def only_orm_sql(record):
    """过滤器：只记录 ORM SQL 日志"""
    name = record["extra"].get("name", "")
    return name == "django.db.backends"


class LogConfig:
    """Loguru日志配置类"""
    
    def __init__(self):
        """初始化日志配置"""
        self.log_dir = self._get_log_dir()
        self.debug_enabled = self._get_debug_enabled()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._configure_loguru_logger()
        self._configure_django_logging()
    
    def _get_log_dir(self):
        """获取日志目录"""
        try:
            log_dir_config = logging_config.get('dir', 'logs')
            
            if os.path.isabs(log_dir_config):
                return Path(log_dir_config)
            else:
                project_root = str(config_loader.project_root)
                return Path(os.path.join(project_root, log_dir_config))
        except Exception as e:
            logger.warning(f"读取日志配置失败，使用默认目录: {e}")
            return Path('logs')
    
    def _get_debug_enabled(self):
        """获取是否启用DEBUG日志"""
        try:
            return logging_config.get('debug_enabled', False)
        except Exception as e:
            logger.warning(f"读取DEBUG配置失败，默认关闭DEBUG日志: {e}")
            return False
    
    def _get_log_format(self):
        """获取日志格式"""
        try:
            format_config = logging_config.get('format', None)

            if format_config:
                # 将标准 logging 格式转换为 loguru 兼容格式
                format_config = format_config.replace('{levelname}', '{level}')
                format_config = format_config.replace('{asctime}', '{time:YYYY-MM-DD HH:mm:ss}')
                return format_config
            else:
                return "{time:YYYY-MM-DD HH:mm:ss.SSS} - [{name}-->{function}:{line}] - {level} - {message}"
        except Exception as e:
            logger.warning(f"读取日志格式配置失败，使用默认格式: {e}")
            return "{time:YYYY-MM-DD HH:mm:ss.SSS} - [{name}-->{function}:{line}] - {level} - {message}"
    
    def _configure_loguru_logger(self):
        """配置loguru logger"""
        logger.remove()  # 移除默认的handler
        
        # 根据配置决定控制台日志级别
        console_level = "DEBUG" if self.debug_enabled else "INFO"
        
        # 控制台输出 - 详细格式（带颜色）
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> - <cyan>[{name}-->{function}:{line}]</cyan> - <level>{level}</level> - <level>{message}</level>",
            level=console_level,
            colorize=True,
            backtrace=True,
            diagnose=True,
            enqueue=True
        )
        
        # 主日志文件 - 保留7天（不包含 ERROR 级别的日志）
        # 使用文件大小轮转避免 Windows 文件锁定问题
        # delay=True 延迟文件打开，catch=True 捕获轮转错误
        app_log_level = "DEBUG" if self.debug_enabled else "INFO"
        logger.add(
            self.log_dir / "app.log",
            rotation="10 MB",  # 文件大小达到10MB时轮转，减少文件锁定时间
            retention="7 days",  # 保留7天
            encoding="utf-8",
            level=app_log_level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} - [{name}-->{function}:{line}] - {level.name} - {message}",
            filter=exclude_errors,  # 过滤掉 ERROR 级别的日志
            backtrace=True,
            diagnose=True,
            enqueue=True,  # 异步写入
            delay=True,  # 延迟文件打开，避免 Windows 文件锁定问题
            catch=True  # 捕获轮转错误，避免程序崩溃
        )
        
        # 错误日志文件 - 保留7天（只记录 ERROR 级别的日志）
        logger.add(
            self.log_dir / "error.log",
            rotation="10 MB",  # 文件大小达到10MB时轮转，减少文件锁定时间
            retention="7 days",
            encoding="utf-8",
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} - [{name}-->{function}:{line}] - {level.name} - {message}",
            filter=only_errors,  # 只记录 ERROR 级别的日志
            backtrace=True,
            diagnose=True,
            enqueue=True,  # 异步写入
            delay=True,  # 延迟文件打开，避免 Windows 文件锁定问题
            catch=True  # 捕获轮转错误，避免程序崩溃
        )
        
        # ORM SQL日志文件 - 保留7天（仅在debug_enabled为True时记录DEBUG日志）
        if self.debug_enabled:
            logger.add(
                self.log_dir / "orm_sql.log",
                rotation="10 MB",  # 文件大小达到10MB时轮转，减少文件锁定时间
                retention="7 days",
                encoding="utf-8",
                level="DEBUG",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} - [{name}-->{function}:{line}] - {level.name} - {message}",
                backtrace=True,
                diagnose=True,
                enqueue=True,
                filter=only_orm_sql,
                delay=True,  # 延迟文件打开，避免 Windows 文件锁定问题
                catch=True  # 捕获轮转错误，避免程序崩溃
            )
        else:
            logger.add(
                self.log_dir / "orm_sql.log",
                rotation="10 MB",  # 文件大小达到10MB时轮转，减少文件锁定时间
                retention="7 days",
                encoding="utf-8",
                level="INFO",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} - [{name}-->{function}:{line}] - {level.name} - {message}",
                backtrace=True,
                diagnose=True,
                enqueue=True,
                filter=only_orm_sql,
                delay=True,  # 延迟文件打开，避免 Windows 文件锁定问题
                catch=True  # 捕获轮转错误，避免程序崩溃
            )
    
    def _configure_django_logging(self):
        """配置Django标准logging系统"""
        # 配置ORM SQL日志
        try:
            orm_logger = logging.getLogger('django.db.backends')
            orm_logger.setLevel(logging.DEBUG)
            orm_handler = logging.FileHandler(
                self.log_dir / 'orm_sql.log',
                encoding='utf-8',
                delay=True  # 延迟文件打开，避免 Windows 文件锁定问题
            )
            orm_handler.setLevel(logging.DEBUG)
            orm_handler.setFormatter(logging.Formatter(
                '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
                style='{'
            ))
            orm_logger.addHandler(orm_handler)
            orm_logger.propagate = False
        except Exception as e:
            logger.warning(f"配置ORM SQL日志失败: {e}")
        
        # 配置Django-Q任务日志
        django_q_loggers = ['django_q', 'django_q.cluster', 'django_q.monitor', 
                           'django_q.worker', 'django_q.pusher', 'monitor', 
                           'tasks', 'scheduler', 'worker', 'pusher']
        
        for logger_name in django_q_loggers:
            try:
                q_logger = logging.getLogger(logger_name)
                q_logger.setLevel(logging.DEBUG)
                q_handler = logging.FileHandler(
                    self.log_dir / 'django_task.log',
                    encoding='utf-8',
                    delay=True  # 延迟文件打开，避免 Windows 文件锁定问题
                )
                q_handler.setLevel(logging.DEBUG)
                q_handler.setFormatter(logging.Formatter(
                    '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
                    style='{'
                ))
                q_logger.addHandler(q_handler)
                q_logger.propagate = False
            except Exception as e:
                logger.warning(f"配置Django-Q日志 {logger_name} 失败: {e}")
    
    def get_logger(self, name=None):
        """
        获取logger实例
        
        Args:
            name: logger名称（可选）
            
        Returns:
            logger实例
        """
        if name:
            return logger.bind(name=name)
        return logger


# 全局日志配置实例
log_config = LogConfig()


def get_logger(name=None):
    """
    获取logger实例的便捷函数
    
    Args:
        name: logger名称（可选）
        
    Returns:
        logger实例
    """
    return log_config.get_logger(name)


def log_exception(logger, message, *args, **kwargs):
    """
    记录异常日志
    
    Args:
        logger: logger实例
        message: 日志消息
        *args: 格式化参数
        **kwargs: 额外字段
    """
    logger.exception(message, *args, **kwargs)


def log_error(logger, message, *args, **kwargs):
    """
    记录错误日志
    
    Args:
        logger: logger实例
        message: 日志消息
        *args: 格式化参数
        **kwargs: 额外字段
    """
    logger.error(message, *args, **kwargs)


def log_warning(logger, message, *args, **kwargs):
    """
    记录警告日志
    
    Args:
        logger: logger实例
        message: 日志消息
        *args: 格式化参数
        **kwargs: 额外字段
    """
    logger.warning(message, *args, **kwargs)


def log_info(logger, message, *args, **kwargs):
    """
    记录信息日志
    
    Args:
        logger: logger实例
        message: 日志消息
        *args: 格式化参数
        **kwargs: 额外字段
    """
    logger.info(message, *args, **kwargs)


def log_debug(logger, message, *args, **kwargs):
    """
    记录调试日志
    
    Args:
        logger: logger实例
        message: 日志消息
        *args: 格式化参数
        **kwargs: 额外字段
    """
    logger.debug(message, *args, **kwargs)


def log_success(logger, message, *args, **kwargs):
    """
    记录成功日志

    Args:
        logger: logger实例
        message: 日志消息
        *args: 格式化参数
        **kwargs: 额外字段
    """
    logger.success(message, *args, **kwargs)
