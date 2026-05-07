# -*- coding: utf-8 -*-
"""
AI模型配置和服务

此文件从 models.py 重新导出模型和服务类，保持向后兼容性。
所有实际的模型定义都在 models.py 中。
"""

# 从 models.py 导入所有模型和服务类
from .models import (
    AIModelConfig,
    PromptConfig,
    TestCaseGenerationTask,
    AIModelService
)

__all__ = [
    'AIModelConfig',
    'PromptConfig',
    'TestCaseGenerationTask',
    'AIModelService'
]
