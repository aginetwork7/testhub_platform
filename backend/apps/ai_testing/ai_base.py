import logging

logger = logging.getLogger('django')

import os

# 禁用 browser-use 遥测
os.environ['ANONYMIZED_TELEMETRY'] = 'false'

import asyncio
import functools
import json
import re
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 加载环境变量
load_dotenv()


# ============================================================================
# 任务动作类型定义 - 统一管理所有动作类型
# ============================================================================

class ActionType:
    """动作类型常量定义，统一管理所有浏览器动作和任务状态动作"""
    # 浏览器动作
    CLICK = 'click'
    FILL = 'fill'
    INPUT_TEXT = 'input_text'
    INPUT = 'input'
    GET_TEXT = 'getText'
    WAIT_FOR = 'waitFor'
    HOVER = 'hover'
    SCROLL = 'scroll'
    SCREENSHOT = 'screenshot'
    WAIT = 'wait'
    SWITCH_TAB = 'switch_tab'
    NAVIGATE_TO = 'navigateTo'
    GO_TO_URL = 'go_to_url'
    OPEN_NEW_TAB = 'open_new_tab'
    CLOSE_TAB = 'close_tab'
    ASSERT = 'assert'

    # 任务状态动作
    MARK_TASK_COMPLETE = 'mark_task_complete'
    MARK_TASK_FAILED = 'mark_task_failed'
    MARK_TASK_SKIPPED = 'mark_task_skipped'
    UPDATE_TASK_STATUS = 'update_task_status'
    DONE = 'done'

    # 常量集合
    TASK_STATUS_ACTIONS = {MARK_TASK_COMPLETE, MARK_TASK_FAILED, MARK_TASK_SKIPPED}
    TERMINAL_ACTIONS = TASK_STATUS_ACTIONS | {DONE}
    BROWSER_ACTIONS = {
        CLICK, FILL, INPUT_TEXT, INPUT, GET_TEXT, WAIT_FOR, HOVER,
        SCROLL, SCREENSHOT, WAIT, SWITCH_TAB, NAVIGATE_TO, GO_TO_URL,
        OPEN_NEW_TAB, CLOSE_TAB, ASSERT
    }
    ALL_ACTIONS = TERMINAL_ACTIONS | BROWSER_ACTIONS

    @classmethod
    def is_task_status_action(cls, action_name: str) -> bool:
        """判断是否是任务状态动作"""
        return action_name in cls.TASK_STATUS_ACTIONS

    @classmethod
    def is_terminal_action(cls, action_name: str) -> bool:
        """判断是否是终端动作（会终止后续操作）"""
        return action_name in cls.TERMINAL_ACTIONS

    @classmethod
    def is_browser_action(cls, action_name: str) -> bool:
        """判断是否是浏览器业务动作"""
        return action_name in cls.BROWSER_ACTIONS

    @classmethod
    def get_status_from_update(cls, action_params) -> str | None:
        """从 update_task_status 参数中提取状态值"""
        if not isinstance(action_params, dict):
            return None
        status = str(action_params.get('status', '')).strip().lower()
        return status if status in {'completed', 'failed', 'skipped'} else None


# 保持向后兼容的常量
TASK_STATUS_ACTIONS = ActionType.TASK_STATUS_ACTIONS


# ============================================================================
# 动作信息提取和验证辅助函数
# ============================================================================

def _extract_action_dict(action):
    """
    从不同类型的 action 对象中提取动作字典

    Args:
        action: 可能是 dict、有 model_dump 方法的对象、或有 _action_dict 属性的对象

    Returns:
        dict: 提取出的动作字典，失败返回空字典
    """
    if isinstance(action, dict):
        return action
    if hasattr(action, 'model_dump'):
        try:
            dumped = action.model_dump()
            if isinstance(dumped, list):
                if dumped and isinstance(dumped[0], dict):
                    return dumped[0]
                return {}
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    if hasattr(action, '_action_dict'):
        extracted = getattr(action, '_action_dict', {})
        if isinstance(extracted, list):
            if extracted and isinstance(extracted[0], dict):
                return extracted[0]
            return {}
        return extracted if isinstance(extracted, dict) else {}
    return {}


def _extract_action_info(action):
    """
    统一提取动作信息

    Args:
        action: 动作对象（可能是 dict、有 model_dump 方法的对象等）

    Returns:
        dict: 包含以下键的字典:
            - action_name: 动作名称
            - action_params: 动作参数
            - is_terminal: 是否是终端动作
            - task_id: 关联的任务ID（仅任务状态动作有）
            - status: 任务状态（仅 update_task_status 有）
            - raw_action: 原始动作字典
    """
    action_dict = _extract_action_dict(action)

    if not action_dict or not isinstance(action_dict, dict):
        return {
            'action_name': None,
            'action_params': None,
            'is_terminal': False,
            'task_id': None,
            'status': None,
            'raw_action': action_dict
        }

    # 提取动作名称和参数
    action_name = next(iter(action_dict.keys()), None)
    action_params = action_dict.get(action_name, {})

    # 判断是否是终端动作
    is_terminal = False
    task_id = None
    status = None

    if ActionType.is_task_status_action(action_name):
        is_terminal = True
        if isinstance(action_params, dict):
            task_id = action_params.get('task_id')
    elif action_name == ActionType.UPDATE_TASK_STATUS:
        status = ActionType.get_status_from_update(action_params)
        if status:
            is_terminal = True
            if isinstance(action_params, dict):
                task_id = action_params.get('task_id')
    elif action_name == ActionType.DONE:
        is_terminal = True

    return {
        'action_name': action_name,
        'action_params': action_params,
        'is_terminal': is_terminal,
        'task_id': task_id,
        'status': status,
        'raw_action': action_dict
    }


def _validate_task_id(task_id, planned_tasks):
    """
    验证 task_id 是否有效

    Args:
        task_id: 要验证的任务ID
        planned_tasks: 计划任务列表

    Returns:
        tuple: (is_valid, task, error_message)
            - is_valid: 是否有效
            - task: 找到的任务对象（如果有效）
            - error_message: 错误信息（如果无效）
    """
    if task_id is None:
        return False, None, "task_id 为空"

    if not planned_tasks:
        return False, None, "planned_tasks 为空，无法验证 task_id"

    # 查找任务
    task = None
    for t in planned_tasks:
        # 防御性编程：如果 t 不是字典，尝试兼容或跳过
        if not isinstance(t, dict):
            if hasattr(t, 'model_dump'):
                t = t.model_dump()
            elif hasattr(t, '__dict__'):
                t = t.__dict__
            else:
                continue

        if t.get('id') == task_id or str(t.get('id')) == str(task_id):
            task = t
            break

    if task is None:
        valid_ids = []
        for t in planned_tasks:
            if isinstance(t, dict):
                valid_ids.append(t.get('id'))
            elif hasattr(t, 'id'):
                valid_ids.append(getattr(t, 'id'))
        return False, None, f"task_id {task_id} 不在有效列表中，有效ID: {valid_ids}"

    return True, task, None


def _sanitize_planned_tasks(planned_tasks):
    if not planned_tasks:
        return []

    if not isinstance(planned_tasks, list):
        planned_tasks = [planned_tasks]

    flattened = []
    for item in planned_tasks:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)

    normalized = []
    for task in flattened:
        if isinstance(task, dict):
            normalized.append(task)
            continue
        if hasattr(task, 'model_dump'):
            try:
                dumped = task.model_dump()
                if isinstance(dumped, dict):
                    normalized.append(dumped)
                continue
            except Exception:
                continue
        if hasattr(task, '__dict__'):
            try:
                task_dict = dict(task.__dict__)
                if isinstance(task_dict, dict):
                    normalized.append(task_dict)
            except Exception:
                continue
    return normalized


def _validate_task_status_value(status_value, action_name='update_task_status'):
    """
    验证任务状态值是否有效

    Args:
        status_value: 要验证的状态值
        action_name: 动作名称（用于错误信息）

    Returns:
        tuple: (is_valid, normalized_status, error_message)
            - is_valid: 是否有效
            - normalized_status: 标准化后的状态值
            - error_message: 错误信息（如果无效）
    """
    valid_statuses = {'completed', 'failed', 'skipped'}
    normalized = str(status_value).strip().lower() if status_value else ''

    if not normalized:
        return False, None, f"{action_name}: status 值为空"

    if normalized not in valid_statuses:
        return False, None, f"{action_name}: status '{status_value}' 无效，有效值: {valid_statuses}"

    return True, normalized, None


def _all_tasks_in_terminal_status(planned_tasks):
    """
    检查是否所有计划任务都已达到终端状态

    Args:
        planned_tasks: 计划任务列表

    Returns:
        tuple: (all_terminal, completed_count, total_count, terminal_tasks)
            - all_terminal: 是否全部达到终端状态
            - completed_count: 已完成的任务数
            - total_count: 总任务数
            - terminal_tasks: 达到终端状态的任务列表
    """
    if not planned_tasks:
        return True, 0, 0, []

    terminal_statuses = {'completed', 'failed', 'skipped'}
    terminal_tasks = []
    completed_count = 0

    for task in planned_tasks:
        if not isinstance(task, dict):
            if hasattr(task, 'model_dump'):
                task = task.model_dump()
            elif hasattr(task, '__dict__'):
                task = task.__dict__
            else:
                continue

        status = str(task.get('status', 'pending')).lower()
        if status in terminal_statuses:
            terminal_tasks.append(task)
            completed_count += 1

    all_terminal = completed_count == len(planned_tasks)
    return all_terminal, completed_count, len(planned_tasks), terminal_tasks


def _get_pending_task_id(planned_tasks):
    """
    获取下一个待处理的任务ID

    Args:
        planned_tasks: 计划任务列表

    Returns:
        int or None: 下一个待处理任务的ID，如果没有则返回 None
    """
    if not planned_tasks:
        return None

    for task in planned_tasks:
        if not isinstance(task, dict):
            if hasattr(task, 'model_dump'):
                task = task.model_dump()
            elif hasattr(task, '__dict__'):
                task = task.__dict__
            else:
                continue

        status = str(task.get('status', 'pending')).lower()
        if status in {'pending', 'in_progress'}:
            return task.get('id')

    return None


# ============================================================================
# 向后兼容的函数（使用新的 ActionType 类）
# ============================================================================


def _normalize_action_params(action_name, action_params):
    """Normalize common LLM-generated action parameter variants to browser-use schema."""
    if isinstance(action_params, int):
        if action_name in TASK_STATUS_ACTIONS:
            return {'task_id': action_params}
        return {'index': action_params}

    if action_name == 'switch_tab' and isinstance(action_params, str) and not isinstance(action_params, dict):
        return {'tab_id': action_params}

    if not isinstance(action_params, dict):
        return action_params

    normalized_params = {}
    for key, value in action_params.items():
        normalized_key = key
        if key in {'element_index', 'element_id', 'node_id', 'id'} and action_name not in TASK_STATUS_ACTIONS:
            normalized_key = 'index'
        elif key in {'tab', 'target', 'target_id'} and action_name in {'switch_tab', 'switch'}:
            normalized_key = 'tab_id'
        elif key in {'content', 'value'} and action_name in {'input', 'input_text'}:
            normalized_key = 'text'
        normalized_params[normalized_key] = value
    return normalized_params


def _is_terminal_status_action(action_name, action_params):
    """判断是否是终端状态动作（使用新的 ActionType 类）"""
    if ActionType.is_task_status_action(action_name):
        return True
    if action_name == ActionType.UPDATE_TASK_STATUS:
        return ActionType.get_status_from_update(action_params) is not None
    return False


def _enforce_single_task_step(actions):
    """
    强制单任务步骤边界：
    - 当同一步中同时存在页面变更动作（click/navigate/scroll等）和任务标记动作时，
      移除任务标记动作，强制模型在下一步验证结果后再标记。
    - 防止模型在点击后未验证结果就标记任务完成。

    Args:
        actions: 动作列表

    Returns:
        tuple: (trimmed_actions, dropped_actions)
    """
    if not isinstance(actions, list) or len(actions) <= 1:
        return actions, []

    # 页面变更动作：执行后需要等待截图验证结果
    PAGE_CHANGING_ACTIONS = {
        'click', 'click_at_coordinates', 'go_to_url', 'scroll_down', 'scroll_up',
        'switch_tab', 'go_back', 'select_option',
    }

    has_page_change = False
    task_mark_indices = []

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        for action_name in action:
            if action_name in PAGE_CHANGING_ACTIONS:
                has_page_change = True
            if action_name in TASK_STATUS_ACTIONS:
                task_mark_indices.append(i)

    # 如果同时存在页面变更动作和任务标记，移除任务标记
    if has_page_change and task_mark_indices:
        dropped = [actions[i] for i in task_mark_indices]
        trimmed = [a for i, a in enumerate(actions) if i not in task_mark_indices]
        for d in dropped:
            logger.warning(f"⚠️ 延迟任务标记: {d} — 需等待下一步截图验证结果后再标记")
        return trimmed, dropped

    return actions, []


# ============================================================================
# 动作顺序验证配置
# ============================================================================

# 配置选项：是否严格检查动作顺序
# True - 拒绝顺序错误的动作（终端动作必须在最后）
# False - 仅记录警告，不拒绝执行
STRICT_ACTION_ORDER = False


def _validate_action_order(actions):
    """
    验证动作顺序是否正确

    规则：
    - 终端状态动作（mark_task_*、done）应该是步骤中最后一个动作
    - 如果不是，根据 STRICT_ACTION_ORDER 配置决定行为

    Args:
        actions: 动作列表

    Returns:
        tuple: (is_valid, issues, reordered_actions)
            - is_valid: 动作顺序是否有效
            - issues: 发现的问题列表
            - reordered_actions: 如果顺序错误且启用自动重排，返回重排后的动作；否则返回原动作
    """
    if not isinstance(actions, list) or len(actions) <= 1:
        return True, [], actions

    issues = []
    terminal_action_indices = []
    has_business_action_after_terminal = False

    # 找出所有终端动作的位置
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            continue

        for action_name, action_params in action.items():
            is_terminal = False

            if ActionType.is_task_status_action(action_name):
                is_terminal = True
            elif action_name == ActionType.UPDATE_TASK_STATUS:
                status = ActionType.get_status_from_update(action_params)
                is_terminal = (status is not None)
            elif action_name == ActionType.DONE:
                is_terminal = True

            if is_terminal:
                terminal_action_indices.append(i)
                break  # 每个动作只需要检查一个键名

    # 检查是否有业务动作在终端动作之后
    if terminal_action_indices:
        last_terminal_index = max(terminal_action_indices)
        for i in range(last_terminal_index + 1, len(actions)):
            action = actions[i]
            if isinstance(action, dict):
                action_info = _extract_action_info(action)
                if action_info['action_name'] and action_info['action_name'] not in ActionType.TERMINAL_ACTIONS:
                    has_business_action_after_terminal = True
                    terminal_action = actions[last_terminal_index]
                    terminal_name = next(iter(terminal_action.keys()))
                    issues.append({
                        'type': 'business_after_terminal',
                        'terminal_action': terminal_name,
                        'terminal_index': last_terminal_index,
                        'business_action': action_info['action_name'],
                        'business_index': i
                    })

    is_valid = not has_business_action_after_terminal

    # 如果没有问题，直接返回
    if is_valid:
        return True, [], actions

    # 记录警告
    for issue in issues:
        logger.warning(
            f"⚠️ 动作顺序问题: 终端动作 '{issue['terminal_action']}' "
            f"(位置 {issue['terminal_index']}) 后有业务动作 '{issue['business_action']}' "
            f"(位置 {issue['business_index']})"
        )

    # 根据配置决定是否重新排序
    if not STRICT_ACTION_ORDER:
        # 自动重新排序：将所有业务动作移到终端动作之前
        business_actions = []
        terminal_actions = []
        terminal_seen = False

        for action in actions:
            action_info = _extract_action_info(action)
            action_name = action_info['action_name']

            if not terminal_seen and action_name in ActionType.TERMINAL_ACTIONS:
                terminal_seen = True

            if terminal_seen:
                terminal_actions.append(action)
            else:
                business_actions.append(action)

        reordered = business_actions + terminal_actions
        if len(reordered) != len(actions):
            # 重排序失败，返回原始动作
            return False, issues, actions

        logger.info("🔄 自动重排动作：将业务动作移到终端动作之前")
        return False, issues, reordered
    else:
        # 严格模式：拒绝执行
        logger.error("❌ 动作顺序错误（严格模式已启用），拒绝执行")
        return False, issues, actions


# ============================================================================
# 任务状态管理器 - 跟踪任务状态变更历史
# ============================================================================

class TaskStateManager:
    """
    任务状态管理器

    跟踪计划任务的状态变更历史，提供状态查询和调试功能。
    """

    def __init__(self, planned_tasks):
        """
        初始化任务状态管理器

        Args:
            planned_tasks: 计划任务列表
        """
        self.planned_tasks = {t['id']: t for t in planned_tasks} if planned_tasks else {}
        # 初始化状态历史
        self.status_history = {}
        for task_id, task in self.planned_tasks.items():
            self.status_history[task_id] = [{
                'from_status': None,
                'to_status': task.get('status', 'pending'),
                'step_number': 0,
                'timestamp': None,
                'trigger_action': None
            }]

    def update_status(self, task_id, new_status, step_number, trigger_action=None):
        """
        更新任务状态并记录历史

        Args:
            task_id: 任务ID
            new_status: 新状态 ('completed', 'failed', 'skipped', 'in_progress')
            step_number: 步骤编号
            trigger_action: 触发状态变更的动作类型
        """
        if task_id not in self.status_history:
            self.status_history[task_id] = [{
                'from_status': None,
                'to_status': 'pending',
                'step_number': 0,
                'timestamp': None,
                'trigger_action': None
            }]

        # 获取当前状态
        current_status = self.status_history[task_id][-1]['to_status']

        # 只有状态真正改变时才记录
        if current_status != new_status:
            from datetime import datetime
            status_change = {
                'from_status': current_status,
                'to_status': new_status,
                'step_number': step_number,
                'timestamp': datetime.now().isoformat(),
                'trigger_action': trigger_action
            }
            self.status_history[task_id].append(status_change)

            # 更新任务对象中的状态
            if task_id in self.planned_tasks:
                self.planned_tasks[task_id]['status'] = new_status

            # 记录日志
            logger.info(
                f"📋 任务状态变更: task_id={task_id}, {current_status} -> {new_status}, "
                f"step={step_number}, action={trigger_action}"
            )

    def get_status(self, task_id):
        """获取任务当前状态"""
        if task_id not in self.status_history:
            return 'unknown'
        return self.status_history[task_id][-1]['to_status']

    def get_history(self, task_id=None):
        """
        获取状态变更历史

        Args:
            task_id: 任务ID，如果为 None 则返回所有任务的历史

        Returns:
            dict: 状态变更历史
        """
        if task_id is not None:
            return self.status_history.get(task_id, [])
        return self.status_history

    def is_all_terminal(self):
        """检查是否所有任务都处于终端状态"""
        terminal_statuses = {'completed', 'failed', 'skipped'}
        for task_id, history in self.status_history.items():
            current_status = history[-1]['to_status']
            if current_status not in terminal_statuses:
                return False
        return True

    def get_summary(self):
        """
        获取任务执行摘要

        Returns:
            dict: 包含各状态任务数量的摘要
        """
        summary = {
            'total': len(self.planned_tasks),
            'pending': 0,
            'in_progress': 0,
            'completed': 0,
            'failed': 0,
            'skipped': 0,
            'terminal': 0
        }

        for history in self.status_history.values():
            current_status = history[-1]['to_status']
            if current_status in summary:
                summary[current_status] += 1
            if current_status in {'completed', 'failed', 'skipped'}:
                summary['terminal'] += 1

        return summary


def _get_task_status_action_task_id(action):
    if not isinstance(action, dict):
        return None

    for action_name, action_params in action.items():
        if action_name in TASK_STATUS_ACTIONS and isinstance(action_params, dict):
            return action_params.get('task_id')
        if action_name == 'update_task_status' and isinstance(action_params, dict):
            status = str(action_params.get('status', '')).strip().lower()
            if status in {'completed', 'failed', 'skipped'}:
                return action_params.get('task_id')
    return None


def _has_real_business_action(action):
    """判断动作是否包含真实的业务操作（使用新的 ActionType 类）"""
    action_dict = _extract_action_dict(action)
    if not action_dict:
        return False
    return any(
        action_name not in ActionType.TERMINAL_ACTIONS
        for action_name in action_dict.keys()
    )


def _extract_task_literals(task_description):
    if not task_description:
        return []

    text = str(task_description)
    literals = []
    literals.extend(re.findall(r'「([^」]+)」', text))
    literals.extend(re.findall(r'"([^"\n]+)"', text))
    literals.extend(re.findall(r"'([^'\n]+)'", text))
    literals.extend(re.findall(r'https?://[^\s]+', text))
    literals.extend(re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text))
    # 提取冒号或顿号后面的内容（例如：版本名称输入：V8.020260316001456）
    literals.extend(re.findall(r'[：:]([^，,。！\n]+)', text))

    deduped = []
    for item in literals:
        cleaned = str(item).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _action_matches_pending_task(action, pending_task_description):
    if not isinstance(action, dict):
        return False

    literals = _extract_task_literals(pending_task_description)
    if not literals:
        return False

    action_payload = json.dumps(action, ensure_ascii=False)
    return any(literal in action_payload for literal in literals)


def _enforce_pending_status_settlement(actions, pending_task_id, pending_task_description=None):
    """
    If the previous step executed a task but forgot to mark it, the next step must settle
    that pending task status first and must not start the following business task in the same step.
    """
    if not pending_task_id or not isinstance(actions, list):
        return actions

    marked_pending_task = any(
        str(_get_task_status_action_task_id(action)) == str(pending_task_id)
        for action in actions
    )
    has_real_action = any(_has_real_business_action(action) for action in actions)

    if not (marked_pending_task and has_real_action):
        return actions

    real_actions = [action for action in actions if _has_real_business_action(action)]
    if pending_task_description and any(
            _action_matches_pending_task(action, pending_task_description)
            for action in real_actions
    ):
        return actions

    settled_actions = [
        action for action in actions
        if str(_get_task_status_action_task_id(action)) == str(pending_task_id)
    ]

    if settled_actions:
        # Relaxed logic: Allow mixed actions (settle pending task + new business actions)
        # Previously we dropped business actions, but this caused issues where tasks were marked completed
        # but the next task's action (like clicking save) was dropped.
        logger.info(
            f"ℹ️ Settling pending task {pending_task_id} while executing new business actions in the same step"
        )
        return actions

    return actions


def _contains_auth_failure_signal(text):
    if not text:
        return False

    normalized = str(text).lower()
    keywords = [
        '登录失败', 'login failed', 'invalid credentials', 'incorrect password',
        '用户名或密码', '账号或密码', 'authentication failed', 'auth failed',
        'bad credentials', 'unauthorized', '401', '403'
    ]
    return any(keyword in normalized for keyword in keywords)


# ============================================================================
# PART 1: Common Patches (Pydantic, ActionModel, TokenCost, Basic Connection)
# ============================================================================

# Patch ChatOpenAI to allow setting attributes (required for browser-use token counting)
try:
    from pydantic import ConfigDict

    if hasattr(ChatOpenAI, 'model_config'):
        if isinstance(ChatOpenAI.model_config, dict):
            ChatOpenAI.model_config['extra'] = 'allow'
        else:
            ChatOpenAI.model_config = ConfigDict(extra='allow', arbitrary_types_allowed=True)
    else:
        ChatOpenAI.model_config = ConfigDict(extra='allow', arbitrary_types_allowed=True)
except ImportError:
    if hasattr(ChatOpenAI, 'model_config'):
        ChatOpenAI.model_config['extra'] = 'allow'

# 修改 ActionModel 配置以允许额外字段
try:
    from browser_use.tools.registry.views import ActionModel
    from pydantic import ConfigDict

    ActionModel.model_config = ConfigDict(arbitrary_types_allowed=True, extra='allow')
    # logger.info("✅ Modified ActionModel.model_config to allow extra fields")
except Exception as e:
    logger.warning(f"⚠️ Failed to modify ActionModel config: {e}")

# Patch Agent.get_model_output 方法
try:
    from browser_use.agent.service import Agent
    from browser_use.agent.message_manager.service import AgentOutput
    import json as json_module

    _original_get_model_output = Agent.get_model_output


    async def _patched_get_model_output(self, input_messages):
        """修补后的 get_model_output，直接从 response.content 解析 JSON"""
        # logger.info("🔧 _patched_get_model_output called")

        if hasattr(self, '_task_was_done') and self._task_was_done:
            logger.info("🔧 Task was marked as done, stopping LLM interaction")
            raise KeyboardInterrupt("Task finished")

        kwargs = {'output_format': self.AgentOutput}

        def _build_agent_output(thinking=None, evaluation_previous_goal=None, memory=None, next_goal=None, actions_data=None):
            parsed = AgentOutput.model_construct(
                thinking=thinking,
                evaluation_previous_goal=evaluation_previous_goal,
                memory=memory,
                next_goal=next_goal,
                action=[]
            )

            class _ActionWrapper:
                def __init__(self, action_dict):
                    self._action_dict = action_dict

                def model_dump(self, **kwargs):
                    return self._action_dict

                def get_index(self):
                    for action_params in self._action_dict.values():
                        if isinstance(action_params, dict) and 'index' in action_params:
                            return action_params['index']
                    return None

            action_list = []
            for action_dict in actions_data or []:
                action_list.append(_ActionWrapper(action_dict))

            object.__setattr__(parsed, 'action', action_list)
            return parsed

        # Add retry logic for LLM invocation with timeout
        max_retries = 2  # 重试次数为2次
        last_exception = None
        response = None
        for attempt in range(max_retries):
            try:
                # 添加超时控制，设置为60秒（支持硅基流动等大模型API的响应时间）
                # 注意：ainvoke 不接受 session_id 参数，确保 kwargs 中不包含它
                # 某些版本的 LangChain 或 LLM 包装器可能会传递额外参数
                clean_kwargs = {k: v for k, v in kwargs.items() if k != 'session_id'}

                response = await asyncio.wait_for(
                    self.llm.ainvoke(input_messages, **clean_kwargs),
                    timeout=60.0  # 超时时间60秒
                )
                break
            except asyncio.TimeoutError as te:
                last_exception = te
                logger.warning(f"⚠️ LLM invocation timed out (attempt {attempt + 1}/{max_retries}): {te}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)  # 重试间隔0.5秒
            except Exception as e:
                last_exception = e
                # 特殊处理 session_id 参数错误
                if "unexpected keyword argument 'session_id'" in str(e):
                    logger.warning(f"⚠️ Removing session_id and retrying...")
                    if 'session_id' in kwargs:
                        del kwargs['session_id']
                    # 立即重试，不计入重试次数
                    try:
                        clean_kwargs = {k: v for k, v in kwargs.items() if k != 'session_id'}
                        response = await asyncio.wait_for(
                            self.llm.ainvoke(input_messages, **clean_kwargs),
                            timeout=60.0
                        )
                        break
                    except Exception as retry_e:
                        last_exception = retry_e
                        logger.warning(f"⚠️ Retry failed: {retry_e}")

                logger.warning(f"⚠️ LLM invocation failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)  # 重试间隔0.5秒
        else:
            logger.error(f"❌ LLM invocation failed after {max_retries} attempts.")
            raise last_exception

        # 检查响应是否为空或无效
        if not response or not hasattr(response, 'content'):
            error_msg = "LLM returned invalid response (no content attribute)"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

        # 检查content是否为空字符串
        content = response.content
        # 视觉模型可能返回 list 格式(多模态内容)，提取文本部分
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict) and item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
            content = '\n'.join(text_parts)
        if not content or not isinstance(content, str) or not content.strip():
            error_msg = "LLM returned empty content - possible API error or timeout"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

        try:
            if hasattr(response, 'content') and isinstance(response.content, str):
                # 处理带有 <thinking> 标签的响应
                content_text = response.content.strip()
                # 移除开头的 <thinking>...</thinking> 标签块
                import re
                thinking_pattern = r'^<thinking>.*?</thinking>\s*'
                if re.match(thinking_pattern, content_text, re.DOTALL):
                    content_text = re.sub(thinking_pattern, '', content_text, count=1, flags=re.DOTALL)
                    logger.info("🔧 Fixed: removed leading <thinking> block from response")

                content_dict = json_module.loads(content_text)

                # 规范化 action 字典
                if 'action' in content_dict:
                    import re
                    normalized_actions = []
                    for action_dict in content_dict['action']:
                        # 处理字符串格式的 action（如 "mark_task_complete(task_id=8)"）
                        if isinstance(action_dict, str):
                            match = re.match(r'(\w+)\(([^)]*)\)', action_dict.strip())
                            if match:
                                action_name = match.group(1)
                                params_str = match.group(2)
                                # 解析参数
                                if action_name in TASK_STATUS_ACTIONS:
                                    task_id_match = re.search(r'task_id=(\d+)', params_str)
                                    if task_id_match:
                                        normalized_actions.append(
                                            {action_name: {'task_id': int(task_id_match.group(1))}})
                                        logger.info(f"🔧 Fixed: parsed string action '{action_dict}'")
                                elif action_name == 'update_task_status':
                                    task_id_match = re.search(r'task_id=(\d+)', params_str)
                                    status_match = re.search(r"status=['\"]?(\w+)['\"]?", params_str)
                                    if task_id_match and status_match:
                                        normalized_actions.append({
                                            action_name: {
                                                'task_id': int(task_id_match.group(1)),
                                                'status': status_match.group(1)
                                            }
                                        })
                                        logger.info(f"🔧 Fixed: parsed string action '{action_dict}'")
                                elif action_name == 'done':
                                    normalized_actions.append({'done': {}})
                            continue

                        normalized_action = {}
                        for action_name, action_params in action_dict.items():
                            normalized_value = _normalize_action_params(action_name, action_params)
                            # 忽略无效的字符串参数（如 {"click": "保存"}）
                            if isinstance(normalized_value, str) and action_name not in ['done', 'switch_tab']:
                                logger.warning(f"⚠️ Invalid action format: {action_name}: {normalized_value}, skipping")
                                continue
                            normalized_action[action_name] = normalized_value
                        if normalized_action:  # 只添加非空的 action
                            normalized_actions.append(normalized_action)
                    normalized_actions, _dropped = _enforce_single_task_step(normalized_actions)

                    # 验证动作顺序
                    is_valid, issues, reordered_actions = _validate_action_order(normalized_actions)
                    if not is_valid and issues:
                        # 如果动作顺序有误，使用重排后的动作
                        normalized_actions = reordered_actions

                    pending_task_id = getattr(self, '_pending_status_task_id', None)
                    pending_task_description = getattr(self, '_pending_status_task_description', None)
                    content_dict['action'] = _enforce_pending_status_settlement(
                        normalized_actions,
                        pending_task_id,
                        pending_task_description
                    )

                # 检查 action 数组外部的 mark_task_complete（错误格式）
                # 如果存在，将其添加到 action 数组中
                for action_name in [*TASK_STATUS_ACTIONS, 'update_task_status']:
                    if action_name not in content_dict:
                        continue
                    if 'action' not in content_dict:
                        content_dict['action'] = []
                    if isinstance(content_dict[action_name], dict):
                        content_dict['action'].append({action_name: content_dict[action_name]})
                        logger.info(f"🔧 Fixed: moved {action_name} into action array")
                    elif isinstance(content_dict[action_name], int) and action_name in TASK_STATUS_ACTIONS:
                        task_id = content_dict[action_name]
                        content_dict['action'].append({action_name: {'task_id': task_id}})
                        logger.info(
                            f"🔧 Fixed: converted {action_name}({task_id}) to proper format and added to action array")

                parsed = _build_agent_output(
                    thinking=content_dict.get('thinking'),
                    evaluation_previous_goal=content_dict.get('evaluation_previous_goal'),
                    memory=content_dict.get('memory'),
                    next_goal=content_dict.get('next_goal'),
                    actions_data=content_dict.get('action', [])
                )

                if len(parsed.action) > self.settings.max_actions_per_step:
                    parsed.action = parsed.action[:self.settings.max_actions_per_step]

                return parsed
        except json_module.JSONDecodeError as je:
            # JSON 解析失败，尝试从原始文本中提取任务状态动作
            logger.warning(f"⚠️ JSON decode failed: {je}")

            # 尝试从原始文本中提取字段和动作
            if hasattr(response, 'content') and response.content:
                content_text = response.content
                # 移除 <thinking> 标签
                import re
                thinking_pattern = r'^<thinking>.*?</thinking>\s*'
                if re.match(thinking_pattern, content_text, re.DOTALL):
                    content_text = re.sub(thinking_pattern, '', content_text, count=1, flags=re.DOTALL)

                # 尝试提取各个字段（即使 JSON 格式有问题）
                extracted_fields = {}
                field_patterns = {
                    'thinking': r'"thinking"\s*:\s*"([^"]*(?:\\"[^"]*)*)"',
                    'evaluation_previous_goal': r'"evaluation_previous_goal"\s*:\s*"([^"]*(?:\\"[^"]*)*)"',
                    'memory': r'"memory"\s*:\s*"([^"]*(?:\\"[^"]*)*)"',
                    'next_goal': r'"next_goal"\s*:\s*"([^"]*(?:\\"[^"]*)*)"',
                }

                for field_name, pattern in field_patterns.items():
                    match = re.search(pattern, content_text)
                    if match:
                        extracted_fields[field_name] = match.group(1)

                # 尝试修复截断的 JSON（处理 [Omitted long context line] 问题）
                # 尝试提取 action 数组中的任务状态动作
                # 注意：使用 [^\\]] 可能导致解析错误，使用更安全的方式
                action_match = re.search(r'"action"\s*:\s*\[(?:(?!\]).)*?\]', content_text, re.DOTALL)
                if action_match:
                    try:
                        # 尝试提取并修复 action 数组
                        action_str = action_match.group(0)
                        # 移除可能被截断的 plan_update 字段
                        cleaned_action_str = re.sub(r'"plan_update"\s*:\s*\[[^\]]*\]\s*,?', '', action_str)
                        # 尝试解析清理后的 action
                        partial_match = re.search(r'"action"\s*:\s*\[(.*?)\]', cleaned_action_str, re.DOTALL)
                        if partial_match:
                            actions_content = '[' + partial_match.group(1) + ']'
                            actions_data = json_module.loads(actions_content)

                            # 构造一个简化的 AgentOutput，使用提取的字段
                            parsed = _build_agent_output(
                                thinking=extracted_fields.get('thinking'),
                                evaluation_previous_goal=extracted_fields.get('evaluation_previous_goal'),
                                memory=extracted_fields.get('memory'),
                                next_goal=extracted_fields.get('next_goal'),
                                actions_data=actions_data
                            )

                            logger.info(
                                f"🔧 Successfully recovered {len(parsed.action)} actions and {len(extracted_fields)} fields from malformed JSON")
                            return parsed
                    except Exception as recovery_error:
                        logger.warning(f"⚠️ Failed to recover actions from malformed JSON: {recovery_error}")

                inferred_actions = []
                mark_complete_match = re.search(r'mark(?:ing)?\s+task\s+(\d+)\s+complete', content_text, re.IGNORECASE)
                if mark_complete_match:
                    inferred_actions.append({'mark_task_complete': {'task_id': int(mark_complete_match.group(1))}})
                elif re.search(r'\bcall(?:ing)?\s+done\b|\ball\s+\d+\s+tasks?\s+completed\b|\ball\s+tasks?\s+completed\b', content_text, re.IGNORECASE):
                    inferred_actions.append({
                        'done': {
                            'success': True,
                            'text': (extracted_fields.get('memory') or content_text.strip())[:1000]
                        }
                    })

                if inferred_actions:
                    logger.info(f"🔧 Inferred {len(inferred_actions)} actions from malformed response text")
                    return _build_agent_output(
                        thinking=extracted_fields.get('thinking'),
                        evaluation_previous_goal=extracted_fields.get('evaluation_previous_goal'),
                        memory=extracted_fields.get('memory'),
                        next_goal=extracted_fields.get('next_goal'),
                        actions_data=inferred_actions
                    )

            # 最后的回退：调用原始方法
            fallback_output = await _original_get_model_output(self, input_messages)
            if fallback_output is None:
                logger.warning("⚠️ Original get_model_output returned None, using safe wait action")
                return _build_agent_output(next_goal='Return a valid action.', actions_data=[{'wait': {'seconds': 2}}])
            return fallback_output
        except Exception as e:
            # 其他异常，直接回退到原始方法
            logger.warning(f"⚠️ Custom output normalization failed, falling back: {e}")
            fallback_output = await _original_get_model_output(self, input_messages)
            if fallback_output is None:
                logger.warning("⚠️ Original get_model_output returned None after fallback, using safe wait action")
                return _build_agent_output(next_goal='Return a valid action.', actions_data=[{'wait': {'seconds': 2}}])
            return fallback_output


    Agent.get_model_output = _patched_get_model_output
    # logger.info("✅ Successfully patched Agent.get_model_output")
except Exception as e:
    logger.error(f"❌ Failed to patch Agent.get_model_output: {e}")

try:
    from browser_use.agent.service import Agent
    from browser_use.llm.messages import UserMessage as BrowserUseUserMessage

    _original_get_model_output_with_retry = Agent._get_model_output_with_retry

    async def _patched_get_model_output_with_retry(self, input_messages):
        try:
            return await _original_get_model_output_with_retry(self, input_messages)
        except (AttributeError, ValueError, Exception) as e:
            err_str = str(e)
            # 捕获 NoneType action、PydanticUndefined、ValidationError 等异常
            recoverable_patterns = [
                "'NoneType' object has no attribute 'action'",
                'PydanticUndefined',
                'validation error',
                'Inserting safe noop action',
            ]
            if not any(p in err_str for p in recoverable_patterns):
                raise

            self.logger.warning('Model returned no structured output. Retrying...')
            clarification_message = BrowserUseUserMessage(
                content='You forgot to return an action. Please respond with a valid JSON action according to the expected schema with your assessment and next actions.'
            )
            retry_messages = input_messages + [clarification_message]
            model_output = await self.get_model_output(retry_messages)

            if model_output is None:
                model_output = self.AgentOutput.model_construct(
                    thinking=None,
                    evaluation_previous_goal=None,
                    memory=None,
                    next_goal='Return a valid action.',
                    action=[]
                )

            if not getattr(model_output, 'action', None):
                action_instance = self.ActionModel()
                setattr(
                    action_instance,
                    'done',
                    {
                        'success': False,
                        'text': 'No next action returned by LLM!',
                    },
                )
                model_output.action = [action_instance]

            return model_output

    Agent._get_model_output_with_retry = _patched_get_model_output_with_retry
except Exception as e:
    logger.error(f"❌ Failed to patch Agent._get_model_output_with_retry: {e}")

# Patch TokenCost
try:
    from browser_use.tokens.service import TokenCost
    from langchain_core.messages import HumanMessage, SystemMessage as LangChainSystemMessage, AIMessage


    def _patched_register_llm(self, llm):
        """修补后的 register_llm，修复 langchain 兼容性"""
        instance_id = str(id(llm))
        if instance_id in self.registered_llms:
            return llm

        self.registered_llms[instance_id] = llm
        _original_ainvoke = llm.ainvoke
        _token_service = self

        async def _fixed_tracked_ainvoke(messages, output_format=None, **kwargs):
            # Sanitize message contents
            def _content_to_str(content):
                if isinstance(content, str): return content
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, str):
                            parts.append(item)
                        elif isinstance(item, dict):
                            if 'text' in item:
                                parts.append(str(item['text']))
                            elif 'image' in item or 'image_url' in item:
                                parts.append("[image]")
                        else:
                            parts.append(str(item))
                    return "\n".join(parts)
                if isinstance(content, dict):
                    if 'text' in content: return str(content['text'])
                    if 'content' in content: return str(content['content'])
                    if 'image' in content or 'image_url' in content: return "[image]"
                return str(content)

            def _sanitize_message(msg):
                msg_type_name = type(msg).__name__
                content = getattr(msg, 'content', msg)
                # 视觉模式下保留列表格式的多模态内容（图片+文字）
                # browser-use 使用 Pydantic 模型（非 dict）作为内容项，需要转为标准 dict
                if _screenshot_use_vision and isinstance(content, list):
                    converted = []
                    for item in content:
                        if isinstance(item, str):
                            converted.append({'type': 'text', 'text': item})
                        elif isinstance(item, dict):
                            converted.append(item)
                        elif hasattr(item, 'model_dump'):
                            converted.append(item.model_dump())
                        elif hasattr(item, 'dict'):
                            converted.append(item.dict())
                        else:
                            converted.append({'type': 'text', 'text': str(item)})
                    return HumanMessage(content=converted)
                content_str = _content_to_str(content)
                if msg_type_name == 'SystemMessage': return LangChainSystemMessage(content=content_str)
                if msg_type_name in ('HumanMessage', 'UserMessage'): return HumanMessage(content=content_str)
                if msg_type_name == 'AIMessage': return AIMessage(content=content_str)
                if isinstance(msg, (HumanMessage, LangChainSystemMessage, AIMessage)): return type(msg)(
                    content=content_str)
                return HumanMessage(content=str(content_str))

            sanitized_messages = [_sanitize_message(m) for m in messages]

            output_format = kwargs.pop('output_format', None)
            kwargs.pop('session_id', None)
            if output_format:
                kwargs['response_format'] = {"type": "json_object"}

            # Add retry logic for LLM invocation
            max_retries = 2  # 重试次数为2次
            last_exception = None
            for attempt in range(max_retries):
                try:
                    result = await _original_ainvoke(sanitized_messages, **kwargs)
                    break
                except Exception as e:
                    last_exception = e
                    if "response_format" in str(e):
                        kwargs.pop('response_format', None)
                        # retry immediately without response_format
                        continue
                    if "unexpected keyword argument 'session_id'" in str(e):
                        kwargs.pop('session_id', None)
                        continue

                    logger.warning(f"⚠️ LLM ainvoke failed (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)  # 等待0.5秒
            else:
                logger.error(f"❌ LLM ainvoke failed after {max_retries} attempts.")
                raise last_exception

            # Enhance response parsing
            import json as json_module
            clean_content = result.content.strip() if hasattr(result, 'content') else str(result).strip()

            # 处理带有 <thinking> 标签的响应
            thinking_pattern = r'^<thinking>.*?</thinking>\s*'
            if re.match(thinking_pattern, clean_content, re.DOTALL):
                clean_content = re.sub(thinking_pattern, '', clean_content, count=1, flags=re.DOTALL)
                logger.info("🔧 Fixed in TokenCost: removed leading <thinking> block from response")

            # Remove Markdown
            if '```' in clean_content:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean_content, re.DOTALL)
                if match:
                    clean_content = match.group(1).strip()
                else:
                    clean_content = re.sub(r'```[a-z]*', '', clean_content).replace('```', '').strip()

            parsed_data = None
            try:
                parsed_data = json_module.loads(clean_content)
            except:
                try:
                    match = re.search(r'(\{.*\})', clean_content, re.DOTALL)
                    if match: parsed_data = json_module.loads(match.group(1))
                except:
                    pass

            # Wrapper classes
            class _ActionWrapper:
                def __init__(self, action_dict):
                    self._dict = {}
                    for k, v in action_dict.items():
                        if isinstance(v, dict):
                            self._dict[k] = _normalize_action_params(k, v)
                        else:
                            self._dict[k] = v
                    for k, v in self._dict.items(): setattr(self, k, v)

                def model_dump(self, **kwargs):
                    return self._dict

                def get_index(self):
                    for v in self._dict.values():
                        if isinstance(v, dict) and 'index' in v: return v['index']
                    return None

            # Construct AgentOutput manually
            agent_output = None
            if parsed_data and 'action' in parsed_data:
                # Normalize actions
                normalized_actions = []
                for action_dict in parsed_data['action']:
                    # 处理字符串格式的 action（如 "mark_task_complete(task_id=8)"）
                    if isinstance(action_dict, str):
                        match = re.match(r'(\w+)\(([^)]*)\)', action_dict.strip())
                        if match:
                            action_name = match.group(1)
                            params_str = match.group(2)
                            # 解析参数
                            if action_name in TASK_STATUS_ACTIONS:
                                task_id_match = re.search(r'task_id=(\d+)', params_str)
                                if task_id_match:
                                    normalized_actions.append({action_name: {'task_id': int(task_id_match.group(1))}})
                                    logger.info(f"🔧 Fixed in TokenCost: parsed string action '{action_dict}'")
                            elif action_name == 'update_task_status':
                                task_id_match = re.search(r'task_id=(\d+)', params_str)
                                status_match = re.search(r"status=['\"]?(\w+)['\"]?", params_str)
                                if task_id_match and status_match:
                                    normalized_actions.append({
                                        action_name: {
                                            'task_id': int(task_id_match.group(1)),
                                            'status': status_match.group(1)
                                        }
                                    })
                                    logger.info(f"🔧 Fixed in TokenCost: parsed string action '{action_dict}'")
                            elif action_name == 'done':
                                normalized_actions.append({'done': {}})
                        continue

                    normalized_action = {}
                    for action_name, action_params in action_dict.items():
                        normalized_value = _normalize_action_params(action_name, action_params)
                        # 忽略无效的字符串参数（如 {"click": "保存"}）
                        if isinstance(normalized_value, str) and action_name not in ['done', 'switch_tab']:
                            logger.warning(
                                f"⚠️ Invalid action format in TokenCost: {action_name}: {normalized_value}, skipping")
                            continue
                        normalized_action[action_name] = normalized_value
                    if normalized_action:  # 只添加非空的 action
                        normalized_actions.append(normalized_action)
                normalized_actions, _dropped = _enforce_single_task_step(normalized_actions)

                # 验证动作顺序
                is_valid, issues, reordered_actions = _validate_action_order(normalized_actions)
                if not is_valid and issues:
                    normalized_actions = reordered_actions

                pending_task_id = getattr(llm, '_pending_status_task_id', None)
                pending_task_description = getattr(llm, '_pending_status_task_description', None)
                parsed_data['action'] = _enforce_pending_status_settlement(
                    normalized_actions,
                    pending_task_id,
                    pending_task_description
                )

                # 检查 action 数组外部的 mark_task_complete（错误格式）
                for action_name in [*TASK_STATUS_ACTIONS, 'update_task_status']:
                    if action_name not in parsed_data:
                        continue
                    if isinstance(parsed_data[action_name], dict):
                        parsed_data['action'].append({action_name: parsed_data[action_name]})
                        logger.info(f"🔧 Fixed in TokenCost: moved {action_name} into action array")
                    elif isinstance(parsed_data[action_name], int) and action_name in TASK_STATUS_ACTIONS:
                        task_id = parsed_data[action_name]
                        parsed_data['action'].append({action_name: {'task_id': task_id}})
                        logger.info(f"🔧 Fixed in TokenCost: moved {action_name}(task_id={task_id}) into action array")

                try:
                    from browser_use.agent.message_manager.service import AgentOutput
                    agent_output = AgentOutput.model_construct(
                        thinking=parsed_data.get('thinking'),
                        evaluation_previous_goal=parsed_data.get('evaluation_previous_goal'),
                        memory=parsed_data.get('memory'),
                        next_goal=parsed_data.get('next_goal'),
                        action=[]
                    )
                    action_list = []
                    for action_dict in parsed_data.get('action', []):
                        action_list.append(_ActionWrapper(action_dict))
                    object.__setattr__(agent_output, 'action', action_list)
                except Exception as e:
                    logger.error(f"🔧 Failed to create AgentOutput: {e}")

            class _ResponseWrapper:
                def __init__(self, orig, completion_obj):
                    self._orig = orig
                    self.content = getattr(orig, 'content', '')
                    self.response_metadata = getattr(orig, 'response_metadata', {})
                    self.completion = completion_obj
                    usage = getattr(orig, 'usage', None) or (
                        orig.response_metadata.get('token_usage') if hasattr(orig, 'response_metadata') else None)
                    if not usage: usage = {}
                    # Fix usage
                    usage = dict(usage) if hasattr(usage, '__dict__') else usage
                    usage.setdefault('prompt_tokens', 0)
                    usage.setdefault('completion_tokens', 0)
                    usage.setdefault('total_tokens', 0)
                    self.usage = usage

                def __getattr__(self, name): return getattr(self._orig, name)

            wrapped = _ResponseWrapper(result, agent_output)
            if hasattr(wrapped, 'usage') and wrapped.usage:
                try:
                    _token_service.add_usage(llm.model, wrapped.usage)
                except:
                    pass

            return wrapped

        setattr(llm, 'ainvoke', _fixed_tracked_ainvoke)
        return llm


    TokenCost.register_llm = _patched_register_llm
    # logger.info("✅ Successfully patched TokenCost.register_llm")
except Exception as e:
    logger.error(f"❌ Failed to patch TokenCost: {e}")

try:
    from browser_use.agent.views import AgentHistory, DOMInteractedElement

    @staticmethod
    def _patched_get_interacted_element(model_output, selector_map):
        elements = []
        for action in getattr(model_output, 'action', []) or []:
            index = None
            get_index = getattr(action, 'get_index', None)
            if callable(get_index):
                try:
                    index = get_index()
                except Exception:
                    index = None
            if index is None:
                try:
                    action_dict = action.model_dump() if hasattr(action, 'model_dump') else getattr(action, '_action_dict', {})
                    if isinstance(action_dict, dict):
                        for action_params in action_dict.values():
                            if isinstance(action_params, dict) and 'index' in action_params:
                                index = action_params['index']
                                break
                except Exception:
                    index = None
            if index is not None and index in selector_map:
                try:
                    elements.append(DOMInteractedElement.load_from_enhanced_dom_tree(selector_map[index]))
                except Exception:
                    elements.append(None)
            else:
                elements.append(None)
        return elements

    AgentHistory.get_interacted_element = _patched_get_interacted_element
except Exception as e:
    logger.error(f"❌ Failed to patch AgentHistory.get_interacted_element: {e}")

# Patch BrowserSession.connect (Windows CDP fix)
try:
    from browser_use.browser.session import BrowserSession
    import httpx

    _original_connect = BrowserSession.connect


    async def _patched_connect(self, cdp_url=None):
        if cdp_url: return await _original_connect(self, cdp_url=cdp_url)

        browser_profile = getattr(self, 'browser_profile', None)
        if hasattr(browser_profile, 'cdp_url') and browser_profile.cdp_url:
            return await _original_connect(self, cdp_url=browser_profile.cdp_url)

        port = 9222
        if hasattr(browser_profile, 'extra_chromium_args'):
            for arg in browser_profile.extra_chromium_args:
                if '--remote-debugging-port=' in str(arg):
                    try:
                        port = int(arg.split('=')[1]);
                        break
                    except:
                        pass
        if hasattr(browser_profile, 'remote_debugging_port'):
            port = browser_profile.remote_debugging_port

        cdp_endpoint = f"http://localhost:{port}/json/version"

        for attempt in range(10):  # 增加重试次数
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(cdp_endpoint)
                    if response.status_code == 200 and response.text:
                        version_info = response.json()
                        browser_profile.cdp_url = version_info['webSocketDebuggerUrl']
                        return await _original_connect(self, cdp_url=browser_profile.cdp_url)
            except Exception:
                if attempt < 4: await asyncio.sleep(1.0)

        return await _original_connect(self, cdp_url=cdp_url)


    BrowserSession.connect = _patched_connect
    # logger.info("✅ Successfully patched BrowserSession.connect")
except Exception as e:
    logger.error(f"❌ Failed to patch BrowserSession.connect: {e}")

# Patch ClickElementAction parameters
try:
    from browser_use.tools.views import ClickElementAction

    _original_click_init = ClickElementAction.__init__


    def _patched_click_init(self, **kwargs):
        fixed_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, int) and key not in ['index']:
                fixed_kwargs['index'] = value
            else:
                fixed_kwargs[key] = value
        if len(kwargs) == 1:
            key, value = list(kwargs.items())[0]
            if isinstance(value, int) and key != 'index':
                fixed_kwargs = {'index': value}
        try:
            return _original_click_init(self, **fixed_kwargs)
        except TypeError:
            if fixed_kwargs and isinstance(list(fixed_kwargs.values())[0], int):
                return _original_click_init(self, **{'index': list(fixed_kwargs.values())[0]})
            raise


    ClickElementAction.__init__ = _patched_click_init
except Exception:
    pass

# Patch ToolRegistry
try:
    from browser_use.tools.registry.service import Registry as ToolRegistry

    # Force patch Registry class
    _original_execute_action = ToolRegistry.execute_action


    async def _patched_execute_action(self, action_name: str, params: dict, **kwargs):
        # 自动映射 switch_tab -> switch (强制映射)
        if action_name == 'switch_tab':
            logger.info(f"🔧 Force aliasing: switch_tab -> switch")
            action_name = 'switch'

        if isinstance(params, int):
            params = {'index': params}
        elif not isinstance(params, dict) and params is not None:
            # 针对 switch_tab 可能是纯字符串的情况
            if action_name in ['switch_tab', 'switch']:
                params = {'tab_id': params}
            else:
                params = {'value': params} if params else {}

        if isinstance(params, dict):
            normalized_params = _normalize_action_params(action_name, params)
            if normalized_params != params:
                logger.info(f"🔧 Normalized action params for {action_name}: {params} -> {normalized_params}")
            params = normalized_params

        # 针对点击增加延迟，确保 UI 更新 (如弹窗弹出、下拉框展开)
        if action_name in ['click_element', 'click']:
            result = await _original_execute_action(self, action_name, params, **kwargs)
            # 增加延迟到 1.5s，并强制在点击后等待浏览器渲染
            # 尤其是对于 element-plus 等 UI 框架，下拉列表渲染需要时间
            await asyncio.sleep(1.5)
            return result

        return await _original_execute_action(self, action_name, params, **kwargs)


    ToolRegistry.execute_action = _patched_execute_action
    # logger.info("✅ Successfully patched ToolRegistry.execute_action with alias support")
except Exception as e:
    logger.error(f"❌ Failed to patch ToolRegistry: {e}")

# Patch ScreenshotWatchdog GLOBALLY to fix timeouts
# 模块级变量：运行时由 BrowserUseAgent 设置，控制截图质量和超时
_screenshot_use_vision = False

try:
    from browser_use.browser.watchdogs.screenshot_watchdog import ScreenshotWatchdog

    _original_on_screenshot_event = ScreenshotWatchdog.on_ScreenshotEvent

    # Check if already patched to avoid double patching
    if not getattr(_original_on_screenshot_event, '_is_patched_global', False):
        async def on_ScreenshotEvent(self, event):
            """
            Patched screenshot event handler with increased timeout and optimized parameters.
            Vision mode uses higher quality and longer timeouts.
            """
            _vision = _screenshot_use_vision
            _timeout = 8.0 if _vision else 3.0
            _quality = 80 if _vision else 50
            try:
                # Try original method first with strict timeout
                result = await asyncio.wait_for(
                    _original_on_screenshot_event(self, event),
                    timeout=_timeout
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(f"DEBUG: Watchdog timeout ({_timeout}s), trying optimized approach...")
                try:
                    # Get CDP session
                    cdp_session = await self.browser_session.get_or_create_cdp_session(target_id=None)
                    if not cdp_session: raise Exception("Failed to get CDP session")

                    params = {'format': 'png', 'quality': _quality, 'from_surface': True, 'capture_beyond_viewport': False}

                    # One quick retry
                    result = await asyncio.wait_for(
                        cdp_session.cdp_client.send.Page.captureScreenshot(params=params,
                                                                           session_id=cdp_session.session_id),
                        timeout=_timeout
                    )
                    return result

                except Exception as ex:
                    # In Text Mode especially, we don't want to die on screenshot
                    logger.warning(f"DEBUG: Screenshot failed optimized, returning placeholder: {ex}")
                    import base64
                    # 1x1 transparent pixel
                    placeholder = base64.b64decode(
                        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
                    return {'data': placeholder}
            except Exception as e:
                logger.error(f"DEBUG: Screenshot unexpected error: {e}")
                import base64
                placeholder = base64.b64decode(
                    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
                return {'data': placeholder}


        on_ScreenshotEvent._is_patched_global = True
        ScreenshotWatchdog.on_ScreenshotEvent = on_ScreenshotEvent
        # logger.info("✅ Applied Global ScreenshotWatchdog Patch")

    # Patch DOMWatchdog
    from browser_use.browser.watchdogs.dom_watchdog import DOMWatchdog

    _original_capture_clean_screenshot = DOMWatchdog._capture_clean_screenshot

    if not getattr(_original_capture_clean_screenshot, '_is_patched_global', False):
        async def _capture_clean_screenshot(self):
            _timeout = 8.0 if _screenshot_use_vision else 3.0
            try:
                # Very short timeout for DOM clean screenshot checks
                return await asyncio.wait_for(_original_capture_clean_screenshot(self), timeout=_timeout)
            except Exception as e:
                logger.warning(f"DEBUG: Clean screenshot failed/timed out: {e}, continuing...")
                return None


        _capture_clean_screenshot._is_patched_global = True
        DOMWatchdog._capture_clean_screenshot = _capture_clean_screenshot
        # logger.info("✅ Applied Global DOMWatchdog Patch")

except Exception as e:
    logger.error(f"❌ Failed to apply Global Watchdog patches: {e}")

# Patch Agent verdict
try:
    from browser_use.agent.service import Agent
    from browser_use.agent.message_manager.service import AgentOutput

    _original_judge_and_log = Agent._judge_and_log


    def _agent_output_getattr(self, name):
        if name == 'verdict':
            if hasattr(self, 'next_goal') and self.next_goal:
                if any(
                        w in str(self.next_goal).lower() for w in
                        ['complete', 'done', 'finished', 'success']): return True
            if hasattr(self, 'evaluation_previous_goal') and self.evaluation_previous_goal:
                if any(w in str(self.evaluation_previous_goal).lower() for w in ['success', 'complete']): return True
            return False
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


    if not hasattr(AgentOutput, '__getattr__'):
        AgentOutput.__getattr__ = _agent_output_getattr


    async def _patched_judge_and_log(self):
        try:
            return await _original_judge_and_log(self)
        except AttributeError as e:
            if 'verdict' in str(e):
                return None
            raise


    Agent._judge_and_log = _patched_judge_and_log
except Exception:
    pass

# Patch LocalBrowserWatchdog._find_free_port to force port 9222 on Linux
try:
    from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog
    import platform

    _original_find_free_port = LocalBrowserWatchdog._find_free_port


    # 创建补丁函数 - 始终作为实例方法（接受 self）
    def _patched_find_free_port(self):
        if platform.system() == 'Linux':
            logger.info("🔧 Force using port 9222 for Linux environment")
            return 9222
        # 尝试调用原始方法，兼容不同签名
        try:
            return _original_find_free_port(self)
        except TypeError:
            # 如果原始方法不接受 self，尝试不带参数调用
            return _original_find_free_port()


    LocalBrowserWatchdog._find_free_port = _patched_find_free_port
    # logger.info("✅ Successfully patched LocalBrowserWatchdog._find_free_port")
except Exception as e:
    logger.error(f"❌ Failed to patch LocalBrowserWatchdog._find_free_port: {e}")

# ============================================================================
# PART 2: Helper Classes
# ============================================================================

from langchain_core.callbacks import BaseCallbackHandler
from typing import Any


class RawResponseLogger(BaseCallbackHandler):
    def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        pass

    def on_llm_end(self, response: Any, **kwargs: Any) -> Any:
        try:
            generation = response.generations[0][0]
            logger.info(f"DEBUG: Raw LLM Response: {generation.text}")
        except:
            pass


# ============================================================================
# PART 3: Base Browser Agent
# ============================================================================

def _get_browser_use_imports():
    """延迟导入 browser_use 模块，避免 Windows 权限问题
    
    browser_use 库在模块导入时会创建 DEFAULT_BROWSER_PROFILE = BrowserProfile()，
    而 BrowserProfile 的默认 downloads_path 是硬编码的 '/tmp/browser-use-downloads-xxx'。
    在 Windows 上，这会导致 PermissionError: [WinError 5] 拒绝访问。
    
    通过延迟导入，只在需要使用时才导入，避免模块加载时触发错误。
    """
    from browser_use import Agent, Controller
    from browser_use.browser.events import CloseTabEvent, SwitchTabEvent
    from browser_use.browser.profile import BrowserProfile
    return Agent, Controller, CloseTabEvent, SwitchTabEvent, BrowserProfile


class BaseBrowserAgent:
    def __init__(self, execution_mode='text', enable_gif=True, case_name=None):
        self.execution_mode = 'text'
        self.enable_gif = enable_gif  # GIF录制开关
        self.case_name = case_name or "Adhoc Task"  # 用例名称

        # Load Config from DB
        from apps.ai_testing.models import AITestModelConfig

        # Select Config: prefer Executor vision mode, fallback to Executor text mode
        config_obj = AITestModelConfig.objects.filter(role='executor_vision', is_active=True).first()
        if config_obj:
            self.use_vision = True
        else:
            config_obj = AITestModelConfig.objects.filter(role='executor_text', is_active=True).first()
            self.use_vision = False

        model_config = {}
        if config_obj:
            model_config = {
                'api_key': config_obj.api_key,
                'base_url': config_obj.base_url,
                'model_name': config_obj.model_name,
                'provider': config_obj.model_type,
                'max_tokens': config_obj.max_tokens,
                'temperature': config_obj.temperature,
                'top_p': config_obj.top_p,
            }

        self.api_key = model_config.get('api_key')
        self.base_url = model_config.get('base_url')
        self.model_name = model_config.get('model_name')
        self.provider = model_config.get('provider', 'openai')

        if not self.api_key:
            logger.error(f"❌ 未找到API Key配置")
            raise ValueError(f'No active AI Testing executor model is configured for mode: {execution_mode}')

        # 确保 base_url 格式正确（去除末尾斜杠，添加 /v1 后缀如果缺失）
        if self.base_url:
            self.base_url = self.base_url.rstrip('/')
            # 对于 OpenAI 兼容 API，如果 base_url 不包含 /v1，则添加
            if not any(self.base_url.endswith(suffix) for suffix in ['/v1', '/chat/completions']):
                if self.provider == 'openai' or self.base_url.startswith('https://api.openai.com'):
                    if not self.base_url.endswith('/v1'):
                        self.base_url += '/v1'
                elif self.provider == 'siliconflow':
                    if not self.base_url.endswith('/v1'):
                        self.base_url += '/v1'
                elif self.provider == 'deepseek':
                    # DeepSeek 兼容 OpenAI API
                    if not self.base_url.endswith('/v1'):
                        self.base_url += '/v1'
                elif self.provider == 'qwen':
                    # 通义千问兼容 OpenAI API
                    if not self.base_url.endswith('/v1'):
                        self.base_url += '/v1'

        if not self.api_key:
            logger.error(f"❌ 未找到API Key配置")
            raise ValueError(f"No API Key found for mode: {execution_mode}")

        # 智能temperature处理：特殊模型强制使用特定temperature值
        # 格式: {'模型名称关键字': temperature值}
        special_model_temperature_map = {
            'kimi-2.5': 1.0,  # Moonshot AI Kimi 2.5 只支持 temperature=1
            'kimi-k2.5': 1.0,  # Moonshot AI Kimi K2.5 只支持 temperature=1
            'kimi': 1.0,  # 通用Kimi模型匹配（兜底）
            # 未来可以在这里添加其他特殊模型，例如：
            # 'claude-3.5-sonnet': 0.7,
            # 'gpt-4-turbo': 0.0,
        }

        # 确定最终使用的temperature值
        final_temperature = 0.0  # 默认值
        model_name_lower = self.model_name.lower()

        # 1. 优先检查是否是特殊模型
        for model_keyword, temp in special_model_temperature_map.items():
            if model_keyword in model_name_lower:
                final_temperature = temp
                logger.info(f"✅ 检测到特殊模型 '{self.model_name}'，使用强制 temperature={temp}")
                break
        else:
            # 2. 如果不是特殊模型，使用配置中的值
            if 'temperature' in model_config:
                final_temperature = model_config['temperature']
                logger.info(f"📋 使用配置的 temperature={final_temperature}")
            else:
                # 3. 如果配置中没有，使用默认值
                final_temperature = 0.0
                logger.info(f"⚙️ 使用默认 temperature={final_temperature}")

        is_reasoning_model = model_name_lower.startswith(('gpt-5', 'o1', 'o3', 'o4'))
        if is_reasoning_model:
            llm_parameters = {'max_completion_tokens': model_config['max_tokens']}
        else:
            llm_parameters = {
                'temperature': final_temperature,
                'top_p': model_config['top_p'],
                'extra_body': {'max_tokens': model_config['max_tokens']},
            }

        logger.info(
            f"🎛️ 最终配置: max_tokens={model_config['max_tokens']}, "
            f"temperature={final_temperature}, top_p={model_config['top_p']}"
        )
        self.llm = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            **llm_parameters,
            callbacks=[RawResponseLogger()]
        )

        # browser-use requirement
        try:
            object.__setattr__(self.llm, 'provider', self.provider)
            object.__setattr__(self.llm, 'model', self.model_name)
        except:
            if not hasattr(self.llm, '__pydantic_extra__') or self.llm.__pydantic_extra__ is None:
                self.llm.__pydantic_extra__ = {}
            self.llm.__pydantic_extra__['provider'] = self.provider
            self.llm.__pydantic_extra__['model'] = self.model_name

        # 记录LLM初始化完成
        logger.info(f"🤖 AI执行模型初始化完成:")
        logger.info(f"  Model: {self.model_name}")
        logger.info(f"  Provider: {self.provider}")
        logger.info(f"  Base URL: {self.base_url}")
        logger.info(f"  API Key: {'*' * 20 if self.api_key else 'None'}")
        logger.info(f"  Temperature: {final_temperature}")

    def _format_action(self, action):
        try:
            action_dict = {}
            if hasattr(action, 'model_dump'):
                action_dict = action.model_dump()
            elif hasattr(action, '_action_dict'):
                action_dict = action._action_dict
            elif hasattr(action, '_dict'):
                action_dict = action._dict
            elif isinstance(action, dict):
                action_dict = action
            else:
                return str(action)

            if isinstance(action_dict, list):
                action_dict = action_dict[0] if action_dict and isinstance(action_dict[0], dict) else {}

            if not action_dict: return "待机"

            descriptions = []
            for name, params in action_dict.items():
                if not params and name not in ['scroll_down', 'scroll_up', 'done']: continue

                if name in ['go_to_url', 'navigate']:
                    url = params.get('url') if isinstance(params, dict) else params
                    descriptions.append(f"访问: {url}")
                elif name in ['click_element', 'click']:
                    index = params.get('index') if isinstance(params, dict) else params
                    descriptions.append(f"点击[{index}]")
                elif name in ['input_text', 'input']:
                    text = params.get('text') if isinstance(params, dict) else None
                    descriptions.append(f"输入: '{text}'")
                elif name == 'switch_tab':
                    index = params.get('index', params)
                    descriptions.append(f"切换标签 {index}")
                elif name == 'open_new_tab':
                    url = params.get('url', params)
                    descriptions.append(f"新标签打开: {url}")
                elif name == 'close_tab':
                    descriptions.append("关闭当前标签页")
                elif name == 'done':
                    descriptions.append("任务完成")
                else:
                    descriptions.append(f"{name}")
            return " | ".join(descriptions)
        except:
            return "执行操作"

    async def _verify_execution_llm(self):
        """在真正启动执行前做一次轻量连通性检查，避免浏览器启动后反复空转失败。"""
        try:
            logger.info(f"🔍 验证LLM连接:")
            logger.info(f"  Model: {self.model_name}")
            logger.info(f"  Provider: {self.provider}")
            logger.info(f"  Base URL: {self.base_url}")
            logger.info(f"  API Key: {'*' * 20 if self.api_key else 'None'}")

            response = await asyncio.wait_for(
                self.llm.ainvoke("Reply with OK."),
                timeout=30.0  # 增加超时时间到30秒
            )
            logger.info(f"✅ LLM连接验证成功，响应: {response.content[:50] if hasattr(response, 'content') else 'OK'}...")
            return response
        except asyncio.TimeoutError as e:
            logger.error(f"❌ LLM连接超时(30秒): model={self.model_name}, base_url={self.base_url}")
            logger.error(f"   提示: 1) 检查网络连接 2) 检查API地址是否正确 3) 检查API Key是否有效")
            raise RuntimeError(f"Execution LLM unavailable: 连接超时，请检查网络或API配置") from e
        except Exception as e:
            logger.error(
                f"❌ LLM连接失败: {type(e).__name__}: {str(e)}, model={self.model_name}, base_url={self.base_url}")
            logger.error(f"   错误详情: {repr(e)[:200]}")
            # 检查是否是认证错误
            if '401' in str(e) or 'authentication' in str(e).lower():
                logger.error(f"   提示: API Key 认证失败，请检查配置")
            elif 'timeout' in str(e).lower():
                logger.error(f"   提示: 连接超时，可能是网络问题或API服务不可达")
            elif 'connection' in str(e).lower():
                logger.error(f"   提示: 连接被拒绝，可能是base_url配置错误")
            raise RuntimeError(f"Execution LLM unavailable: {str(e)}") from e

    def _extract_structured_steps(self, text: str):
        """从原始任务文本中稳定提取步骤，作为 LLM 拆分失败时的兜底。"""
        if not text:
            return []

        normalized_text = str(text).replace('\r\n', '\n').replace('\r', '\n').strip()
        if not normalized_text:
            return []

        # 优先按行解析显式编号步骤
        numbered_line_pattern = re.compile(r'^\s*(\d+(?:\.\d+)*)[\.\s、:：-]+(.*)$')
        extracted_steps = []
        plain_lines = []

        for raw_line in normalized_text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            match = numbered_line_pattern.match(line)
            if match:
                desc = match.group(2).strip()
                if desc:
                    extracted_steps.append(desc)
            else:
                plain_lines.append(line)

        if extracted_steps:
            if len(extracted_steps) == 1 and '\n' not in normalized_text:
                split_inline_text = re.sub(
                    r'\s+(?=\d+(?:\.\d+)*[\.\s、:：-]+)',
                    '\n',
                    normalized_text
                )
                if split_inline_text != normalized_text:
                    inline_steps = self._extract_structured_steps(split_inline_text)
                    if len(inline_steps) > 1:
                        return inline_steps
            return extracted_steps

        # 其次解析单行内多个编号步骤，例如：
        # "1.访问xx 2.搜索xx 3.点击xx"
        split_inline_text = re.sub(
            r'\s+(?=\d+(?:\.\d+)*[\.\s、:：-]+)',
            '\n',
            normalized_text
        )
        if split_inline_text != normalized_text:
            inline_steps = self._extract_structured_steps(split_inline_text)
            if inline_steps:
                return inline_steps

        # 最后退化为逐行文本
        return plain_lines or [normalized_text]

    def _normalize_steps(self, raw_steps, fallback_text: str):
        """清洗并展开步骤列表，避免多步被合并成一条。"""
        steps = raw_steps if isinstance(raw_steps, list) else []
        normalized_steps = []

        for step in steps:
            if step is None:
                continue
            desc = str(step).strip()
            if not desc:
                continue

            # 如果单个 step 里仍然包含多行/多编号步骤，继续拆开
            nested_steps = self._extract_structured_steps(desc)
            if nested_steps and not (len(nested_steps) == 1 and nested_steps[0] == desc):
                normalized_steps.extend(nested_steps)
            else:
                normalized_steps.append(desc)

        if not normalized_steps:
            normalized_steps = self._extract_structured_steps(fallback_text)

        cleaned_steps = []
        for desc in normalized_steps:
            current = str(desc).strip()
            while True:
                match = re.match(r'^\s*\d+(?:\.\d+)*[\.\s、:：-]+(.*)', current, re.S)
                if not match:
                    break
                current = match.group(1).strip()
            if current:
                cleaned_steps.append(current)

        return cleaned_steps or [fallback_text.strip()]

    def _compact_steps(self, steps):
        """合并过细的动作级步骤，收敛为核心业务子任务。"""
        if not steps:
            return []

        compacted = []
        i = 0
        total = len(steps)

        while i < total:
            current = str(steps[i]).strip()
            current_lower = current.lower()

            # 合并“打开浏览器 / 输入URL / 回车访问”这一类导航碎步
            if (
                    ('浏览器' in current or 'browser' in current_lower or '地址栏' in current)
                    and i + 1 < total
            ):
                window = " ".join(str(s).strip() for s in steps[i:i + 3])
                url_match = re.search(r'https?://[^\s]+', window)
                if url_match:
                    compacted.append(f"访问{url_match.group(0)}")
                    i += min(3, total - i)
                    continue

            # 合并“点击搜索框 / 输入关键词 / 点击搜索 / 等待结果”
            search_window = " ".join(str(s).strip() for s in steps[i:i + 4])
            if any(keyword in search_window for keyword in ['搜索框', '关键词', '百度一下', '搜索结果', 'search']):
                query_match = re.search(r"(?:输入搜索关键词[:：]?\s*|搜索)\s*['\"]?([^'\"\n]+?)['\"]?(?:\s|$)",
                                        search_window)
                if query_match:
                    query = query_match.group(1).strip()
                    query = re.sub(r'(并执行搜索|按钮或按下回车键|结果列表加载完成)$', '', query).strip()
                    compacted.append(f"搜索{query}")
                    i += min(4, total - i)
                    continue

            # 合并“点击第N条结果 + 新标签查看详情”
            if any(keyword in current for keyword in ['搜索结果', '结果', '标题链接', '查看详情']):
                if any(keyword in current for keyword in ['第二条', '第2条', '详情', '链接']):
                    compacted.append("点击第2条搜索结果查看详情")
                    i += 1
                    continue

            # 合并关闭标签页相关步骤
            if any(keyword in current for keyword in ['关闭', '标签页', '新标签页', 'close tab']):
                compacted.append("关闭该标签页")
                i += 1
                continue

            compacted.append(current)
            i += 1

        # 去重并保持顺序
        deduped = []
        for step in compacted:
            if not deduped or deduped[-1] != step:
                deduped.append(step)
        return deduped

    def _step_complexity_score(self, step: str) -> int:
        """粗略评估单个步骤是否包含多个动作。"""
        text = str(step).strip()
        if not text:
            return 0

        score = 0
        if len(text) >= 24:
            score += 1
        if len(text) >= 48:
            score += 1
        if any(token in text for token in ['并', '然后', '之后', '再', '并且', '同时', '且']):
            score += 1
        if any(token in text for token in
               ['点击', '输入', '搜索', '选择', '打开', '关闭', '提交', '保存', '查看', '切换']):
            action_hits = sum(text.count(token) for token in
                              ['点击', '输入', '搜索', '选择', '打开', '关闭', '提交', '保存', '查看', '切换'])
            if action_hits >= 2:
                score += 1
        return score

    def _step_has_specific_requirements(self, step: str) -> bool:
        """判断步骤是否包含必须保留的字面值、断言或字段约束。"""
        text = str(step).strip()
        if not text:
            return False

        signals = 0
        if re.search(r'https?://', text):
            signals += 1
        if any(token in text for token in ['「', '」', '"', "'"]):
            signals += 1
        if re.search(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text):
            signals += 1
        if re.search(r'\([^)]{2,}\)', text):
            signals += 1
        if any(token in text for token in ['标题为', '返回', '确认页面', '确认', '验证', '校验']):
            signals += 1
        if any(token in text for token in
               ['输入框', '按钮', '下拉', '单选', '日期', 'Password', 'Text input', 'Dropdown']):
            signals += 1
        return signals >= 2

    def _should_redecompose_explicit_steps(self, steps):
        """判断已编号任务是否复杂到需要模型二次整合。"""
        if not steps:
            return False

        detail_rich_count = sum(1 for step in steps if self._step_has_specific_requirements(step))
        if detail_rich_count >= max(2, len(steps) // 2):
            return False

        if len(steps) >= 10:
            return True

        complex_count = sum(1 for step in steps if self._step_complexity_score(step) >= 2)
        if complex_count >= max(2, len(steps) // 2):
            return True

        very_long_count = sum(1 for step in steps if len(str(step).strip()) >= 40)
        if very_long_count >= max(2, len(steps) // 2):
            return True

        return False

    async def _model_break_down_task(self, task_description: str, mode: str = 'break_down'):
        """调用模型拆分或重整任务步骤。"""
        if mode == 'recompose':
            prompt = (
                "You are given a task that already has numbered steps, but some steps may be too granular or redundant. "
                "Rewrite them into core business steps only. "
                "Rules: keep the original intent and order, merge mechanical browser operations into the surrounding business step, "
                "do not invent new goals, do not split into micro-actions like clicking an input box or waiting for page load. "
                "Preserve every concrete literal requirement from the original steps, including URLs, field labels, option values, dates, expected titles, "
                "expected result text, and quoted content. Do not replace them with vague phrases like '输入文本信息' or '验证成功'. "
                "Return JSON list of concise Chinese strings only.\n\n"
                f"Task:\n{task_description}"
            )
        else:
            prompt = (
                "Break down this task into core business steps only. "
                "Avoid micro-actions like opening the browser, clicking into an input box, or waiting for results unless they are the user's explicit goal. "
                "Preserve every concrete literal requirement from the original task, including URLs, field labels, option values, dates, expected titles, "
                "expected result text, and quoted content. Do not replace them with vague summaries like '输入文本信息' or '验证成功'. "
                "Keep the order and return JSON list of concise Chinese strings only.\n\n"
                f"Task:\n{task_description}"
            )

        response = await self.llm.ainvoke(prompt)
        content = response.content.strip() if hasattr(response, 'content') else str(response)

        steps = []
        try:
            import json
            match = re.search(r'(\[.*\])', content, re.DOTALL)
            if match:
                steps = json.loads(match.group(1))
        except Exception:
            pass

        return steps

    def _finalize_steps(self, steps, fallback_text: str):
        """统一收口步骤列表，保证输出可执行且尽量精简。"""
        return self._compact_steps(self._normalize_steps(steps, fallback_text))

    async def analyze_task(self, task_description: str):
        try:
            explicit_steps = self._extract_structured_steps(task_description)
            if len(explicit_steps) >= 2:
                if self._should_redecompose_explicit_steps(explicit_steps):
                    steps = await self._model_break_down_task(task_description, mode='recompose')
                    cleaned_steps = self._finalize_steps(steps, task_description)
                else:
                    cleaned_steps = self._normalize_steps(explicit_steps, task_description)
                return [{'id': i + 1, 'description': s, 'status': 'pending'} for i, s in enumerate(cleaned_steps)]

            steps = await self._model_break_down_task(task_description, mode='break_down')
            cleaned_steps = self._finalize_steps(steps, task_description)

            return [{'id': i + 1, 'description': s, 'status': 'pending'} for i, s in enumerate(cleaned_steps)]
        except Exception as e:
            logger.warning(f"⚠️ analyze_task fallback triggered: {e}")
            cleaned_steps = self._finalize_steps([], task_description)
            return [{'id': i + 1, 'description': s, 'status': 'pending'} for i, s in enumerate(cleaned_steps)]

    def _cleanup_zombie_chrome(self):
        """Clean up any existing Chrome processes on port 9222 (Linux only)"""
        import platform
        import psutil

        if platform.system() != 'Linux':
            return

        logger.info("🧹 Cleaning up zombie Chrome processes...")
        cleaned_count = 0
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Check for chrome/chromium
                    if proc.info['name'] and ('chrome' in proc.info['name'] or 'chromium' in proc.info['name']):
                        # Check command line for port 9222
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and any('9222' in str(arg) for arg in cmdline):
                            logger.info(f"Killing zombie chrome pid={proc.pid}")
                            proc.kill()
                            cleaned_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception as e:
            logger.warning(f"⚠️ Failed to cleanup zombie chrome: {e}")

        if cleaned_count > 0:
            logger.info(f"✅ Cleaned up {cleaned_count} zombie Chrome processes")

    def _create_browser_profile(self):
        # Default implementation, can be overridden
        chrome_path = None
        import platform

        system = platform.system()
        if system == 'Windows':
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
            ]
            for p in paths:
                if os.path.exists(p):
                    chrome_path = p
                    break
        elif system == 'Linux':
            # Linux 系统常见的 Chrome 路径 - 优先使用我们预装的浏览器
            paths = [
                # 优先使用Docker容器中预装的Chromium
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium',
                '/usr/bin/google-chrome',
                # 检查Playwright安装的浏览器
                '/ms-playwright/chromium-*/chromium-linux/chromium',
                '/root/.cache/ms-playwright/chromium-*/chromium-linux/chromium',
                # 备用路径
                '/usr/bin/google-chrome-stable',
                '/opt/google/chrome/chrome',
                '/snap/bin/chromium',
            ]
            for p in paths:
                # 支持通配符路径
                if '*' in p:
                    import glob
                    matches = glob.glob(p)
                    if matches:
                        for match in matches:
                            if os.path.exists(match) and os.access(match, os.X_OK):
                                chrome_path = match
                                logger.info(f"找到浏览器: {chrome_path}")
                                break
                        if chrome_path:
                            break
                elif os.path.exists(p) and os.access(p, os.X_OK):
                    chrome_path = p
                    logger.info(f"找到浏览器: {chrome_path}")
                    break

            # 如果还是没找到，尝试查找Playwright的默认路径或让browser-use自行安装
            if not chrome_path:
                import glob
                playwright_paths = glob.glob('/ms-playwright/**/chromium', recursive=True)
                playwright_paths.extend(glob.glob('/root/.cache/ms-playwright/**/chromium', recursive=True))
                playwright_paths.extend(glob.glob('/ms-playwright/**/chromium-linux/chromium', recursive=True))
                playwright_paths.extend(
                    glob.glob('/root/.cache/ms-playwright/**/chromium-linux/chromium', recursive=True))
                for p in playwright_paths:
                    if os.path.exists(p) and os.access(p, os.X_OK):
                        chrome_path = p
                        logger.info(f"通过Playwright找到浏览器: {chrome_path}")
                        break

                # 最后的备用方案：让browser-use自行处理浏览器安装
                if not chrome_path:
                    logger.info("未找到预装浏览器，将让browser-use自动安装")
                    chrome_path = None  # 让browser-use处理

        # 基础性能优化参数
        extra_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars', '--disable-notifications',
            '--disable-background-networking',
            '--disable-background-timer-throttling',
            '--disable-renderer-backgrounding',
            '--disable-backgrounding-occluded-windows',
            '--disable-extensions',
            '--disable-web-security',  # 允许跨域请求
        ]

        # 根据操作系统添加特定参数
        if system == 'Linux':
            # Linux 服务器环境（特别是无头环境）必需的参数
            extra_args.extend([
                '--no-sandbox',  # Linux 必需：禁用沙箱
                '--disable-setuid-sandbox',  # Linux 必需：禁用 setuid 沙箱
                '--disable-dev-shm-usage',  # Linux 必需：使用 /tmp 而不是 /dev/shm
                '--disable-gpu',  # 禁用 GPU 加速（服务器通常无 GPU）
                '--headless=new',  # Linux 服务器使用无头模式
                '--disable-software-rasterizer',  # 禁用软件光栅化器
                '--remote-debugging-port=9222',  # 使用固定端口，避免随机端口导致连接失败
                '--remote-debugging-address=0.0.0.0',  # 允许远程连接，而不仅仅是 127.0.0.1
                '--no-zygote',  # 减少进程数
                '--single-process',  # 单进程模式，虽然不稳定但能解决某些 Docker 环境下的 PID 问题
            ])
        else:
            # macOS 和 Windows 使用显示模式
            extra_args.extend([
                '--no-sandbox',  # 兼容性
                '--disable-gpu',
                '--remote-debugging-port=9222',
            ])

        _, _, _, _, BrowserProfile = _get_browser_use_imports()

        # 视觉模式使用更大的视口和更长的等待时间
        if self.use_vision:
            wait_between = 0.5
            viewport_width = 1280
            viewport_height = 720
        else:
            wait_between = 0.1
            viewport_width = 1280
            viewport_height = 720

        return BrowserProfile(
            headless=(system == 'Linux'),  # Linux 使用无头模式，其他系统使用显示模式
            disable_security=True,
            executable_path=chrome_path,
            args=extra_args,
            wait_for_network_idle_page_load_time=0.2,
            minimum_wait_page_load_time=0.05,
            wait_between_actions=wait_between,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            enable_default_extensions=False
        )

    async def run_task(self, task_description: str, planned_tasks=None, callback=None, should_stop=None):
        await self._verify_execution_llm()

        # 设置截图模式（视觉模式使用更高质量）
        global _screenshot_use_vision
        _screenshot_use_vision = self.use_vision

        # Cleanup potential zombie processes before starting
        self._cleanup_zombie_chrome()

        planned_tasks = _sanitize_planned_tasks(planned_tasks)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        _, Controller, _, _, _ = _get_browser_use_imports()
        controller = Controller()
        _task_was_done = False
        active_task_statuses = {'pending', 'in_progress'}

        # 创建任务状态管理器
        task_manager = TaskStateManager(planned_tasks) if planned_tasks else None

        async def emit_callback(payload):
            if not callback:
                return

            if asyncio.iscoroutinefunction(callback):
                await callback(payload)
            else:
                callback(payload)

        def is_placeholder_url(url: str) -> bool:
            normalized = (url or '').strip().lower()
            return (
                    not normalized
                    or normalized == 'about:blank'
                    or normalized.startswith('chrome://newtab')
                    or normalized.startswith('edge://newtab')
            )

        def is_close_step(description: str) -> bool:
            text = str(description or '').strip()
            return any(keyword in text for keyword in ['关闭', '关闭该标签页', '关闭标签页'])

        def get_next_active_task():
            if not planned_tasks:
                return None

            for task in planned_tasks:
                if task.get('status', 'pending') in active_task_statuses:
                    return task
            return None

        async def find_preferred_fallback_tab(browser_session, exclude_target_id=None):
            tabs = await browser_session.get_tabs()
            candidate_tabs = [tab for tab in tabs if tab.target_id != exclude_target_id]
            if not candidate_tabs:
                return None

            non_placeholder_tabs = [tab for tab in candidate_tabs if not is_placeholder_url(getattr(tab, 'url', ''))]
            return (non_placeholder_tabs or candidate_tabs)[-1]

        @controller.action('Done')
        async def done(success: bool = True, text: str = ""):
            nonlocal _task_was_done
            _task_was_done = True
            return f"Finished: {text}"

        @controller.action('close_tab')
        async def close_tab(browser_session=None):
            _, _, CloseTabEvent, SwitchTabEvent, _ = _get_browser_use_imports()
            if browser_session is None or browser_session.agent_focus_target_id is None:
                raise ValueError("No active tab to close")
            target_id = browser_session.agent_focus_target_id
            fallback_tab = None
            try:
                fallback_tab = await find_preferred_fallback_tab(browser_session, exclude_target_id=target_id)
            except Exception as e:
                logger.warning(f"Failed to determine fallback tab before closing {target_id[-4:]}: {e}")

            event = browser_session.event_bus.dispatch(CloseTabEvent(target_id=target_id))
            await event

            if fallback_tab is not None:
                try:
                    await asyncio.sleep(0.15)
                    if browser_session.agent_focus_target_id != fallback_tab.target_id:
                        await browser_session.event_bus.dispatch(
                            SwitchTabEvent(target_id=fallback_tab.target_id)
                        )
                        logger.info(
                            f"↩️ Switched back to existing tab {fallback_tab.target_id[-4:]} "
                            f"({fallback_tab.url}) after closing {target_id[-4:]}"
                        )
                        await emit_callback({
                            'type': 'log',
                            'content': (
                                f"\n[System]\n关闭标签页后，已切回来源页 {fallback_tab.target_id[-4:]}\n"
                            )
                        })
                except Exception as e:
                    logger.warning(f"Failed to switch back to preferred tab after closing {target_id[-4:]}: {e}")

            next_active_task = get_next_active_task()
            if next_active_task and is_close_step(next_active_task.get('description')):
                logger.info(f"✅ Auto-marking close step task {next_active_task['id']} as completed after close_tab")
                await emit_callback({'task_id': int(next_active_task['id']), 'status': 'completed'})

            return f"Closed tab {target_id[-4:]}"

        @controller.action('mark_task_complete')
        async def mark_task_complete(task_id: int):
            logger.info(f"✅ Explicitly marking task {task_id} as completed")
            try:
                await emit_callback({'task_id': int(task_id), 'status': 'completed'})
            except Exception as e:
                logger.warning(f"Failed to execute mark_task_complete callback: {e}")
            return f"Task {task_id} marked completed"

        @controller.action('mark_task_failed')
        async def mark_task_failed(task_id: int):
            logger.info(f"❌ Explicitly marking task {task_id} as failed")
            try:
                await emit_callback({'task_id': int(task_id), 'status': 'failed'})
            except Exception as e:
                logger.warning(f"Failed to execute mark_task_failed callback: {e}")
            return f"Task {task_id} marked failed"

        @controller.action('mark_task_skipped')
        async def mark_task_skipped(task_id: int):
            logger.info(f"⏭️ Explicitly marking task {task_id} as skipped")
            try:
                await emit_callback({'task_id': int(task_id), 'status': 'skipped'})
            except Exception as e:
                logger.warning(f"Failed to execute mark_task_skipped callback: {e}")
            return f"Task {task_id} marked skipped"

        @controller.action('click_at_coordinates', param_model=None)
        async def click_at_coordinates(x: int, y: int, browser_session=None):
            """Click at specific pixel coordinates (x, y) on the page. Use when element has no index overlay."""
            if browser_session is None:
                raise ValueError('No active browser session')
            page = await browser_session.get_current_page()
            logger.info(f'🖱️ Clicking at coordinates ({x}, {y})')
            await page.mouse.click(x, y)
            await asyncio.sleep(1.0)
            return f'Clicked at coordinates ({x}, {y})'

        @controller.action('update_task_status')
        async def update_task_status(task_id: int, status: str):
            normalized_status = str(status).strip().lower()
            if normalized_status not in {'completed', 'failed', 'skipped', 'in_progress'}:
                raise ValueError(f"Unsupported task status: {status}")
            logger.info(f"🔄 Explicitly updating task {task_id} to {normalized_status}")
            try:
                await emit_callback({'task_id': int(task_id), 'status': normalized_status})
            except Exception as e:
                logger.warning(f"Failed to execute update_task_status callback: {e}")
            return f"Task {task_id} marked {normalized_status}"

        # 构建强化版 Prompt
        final_task = task_description
        if planned_tasks:
            final_task += "\n\nIMPORTANT INSTRUCTION:\n"
            final_task += "You have a list of sub-tasks. Execute strictly in order.\n"
            final_task += "CRITICAL: MUST call one of 'mark_task_complete', 'mark_task_failed', 'mark_task_skipped', or 'update_task_status(task_id=..., status=...)' IMMEDIATELY after determining each sub-task result. NEVER skip this step.\n"
            final_task += "IMPORTANT: If a sub-task (like opening a URL) is already fulfilled by the initial state, YOU MUST mark it complete in your VERY FIRST STEP.\n"
            final_task += "Sub-tasks (Execute in order):\n"
            cleaned_tasks = []
            for t in planned_tasks:
                desc = t['description']
                # 递归去除所有层级的重复序号，例如 "1. 1. xxx" -> "xxx"
                while True:
                    match = re.match(r'^\s*\d+[\.\s、:]+(.*)', desc)
                    if not match: break
                    desc = match.group(1).strip()
                cleaned_tasks.append(f"{t['id']}. {desc}")
            final_task += "\n".join(cleaned_tasks)

        # 极限效率版标记指令 - 从数据库/文件加载提示词
        from datetime import datetime
        final_task += f"\n\nCURRENT TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        # 根据模式选择提示词类型
        prompt_type = 'executor_vision' if self.use_vision else 'executor_text'
        prompt_content = None

        from apps.ai_testing.models import AITestPromptConfig
        db_config = AITestPromptConfig.get_active_config(prompt_type)
        if not db_config or not db_config.content.strip():
            raise ValueError(f'No active AI Testing {prompt_type} prompt is configured')
        prompt_content = db_config.content
        logger.info(f"📝 Loaded {prompt_type} prompt from dedicated AI Testing configuration: {db_config.name}")

        final_task += "\n" + prompt_content

        if 'qwen' in self.model_name.lower() or 'deepseek' in self.model_name.lower():
            final_task += "\nEXTREMELY MINIMIZE output tokens for speed. Keep responses as short as possible while maintaining accuracy.\n"

        # 核心修复: 清理 task 长文本中的 URL，防止中文标点紧贴 URL 导致 browser-use 解析错误
        # 例如 "http://localhost:3000，" -> "http://localhost:3000 "
        try:
            # 在中文标点前加空格，避免它们成为 URL 的一部分
            final_task = re.sub(r'(https?://[^\s\u4e00-\u9fa5]+?)(?=[，；。、！])', r'\1 ', final_task)
            logger.info(f"🔧 Optimized task description for URL extraction")
        except:
            pass

        browser_profile = self._create_browser_profile()

        Agent, _, _, _, _ = _get_browser_use_imports()
        agent = Agent(
            task=final_task,
            llm=self.llm,
            controller=controller,
            browser_profile=browser_profile,
            use_vision=self.use_vision,
            max_actions_per_step=10,  # 增加步进密度，减少总步骤数，降低超时风险
            max_retries=1,  # 减少重试次数以提高速度 (从2改为1)
            max_failures=2,  # 减少最大失败次数，避免过长等待 (从默认3改为2)
            llm_timeout=60,  # 设置LLM调用超时为60秒（支持硅基流动等大模型API）
            step_timeout=90,  # 设置每步超时为90秒
            generate_gif=self.enable_gif,  # 根据开关决定是否生成GIF
        )
        agent._task_was_done = False
        agent._pending_status_task_id = None
        agent._pending_status_task_description = None
        agent._auth_failure_task_id = None
        agent._auth_failure_count = 0

        # Callback helper - 添加任务标记跟踪
        last_processed_step = 0
        last_marked_task_id = 0  # 跟踪上一次标记的任务ID
        known_tab_ids = set()

        async def on_step_end(agent_instance):
            nonlocal last_processed_step, last_marked_task_id, known_tab_ids, _task_was_done

            if should_stop:
                do_stop = await should_stop() if asyncio.iscoroutinefunction(should_stop) else should_stop()
                if do_stop: raise KeyboardInterrupt("User requested stop")

            if _task_was_done:
                raise KeyboardInterrupt("Done")

            history = getattr(agent_instance, 'history', [])
            if hasattr(history, 'history'): history = history.history

            if len(history) > last_processed_step:
                for i in range(last_processed_step, len(history)):
                    step = history[i]
                    # Log logic here
                    try:
                        actions = []
                        if hasattr(step, 'model_output') and hasattr(step.model_output, 'action'):
                            raw = step.model_output.action
                            actions = raw if isinstance(raw, list) else [raw]

                        # 后备机制：如果 action 列表为空，尝试从原始响应文本中提取任务状态动作
                        if not actions:
                            model_output = getattr(step, 'model_output', None)
                            if model_output:
                                # 从 model_output 的各个字段中提取任务状态动作
                                import re
                                text_content = ''
                                for field_name in ['thinking', 'evaluation_previous_goal', 'memory', 'next_goal']:
                                    value = getattr(model_output, field_name, None)
                                    if value:
                                        text_content += str(value) + ' '

                                # 搜索模式: mark_task_complete(task_id=N), mark_task_failed(task_id=N), 等
                                patterns = [
                                    r'mark_task_complete\s*\(\s*task_id\s*=\s*(\d+)',
                                    r'mark_task_complete\s*\(\s*"task_id"\s*:\s*(\d+)',
                                    r'mark_task_complete\s*\(\s*{\s*"task_id"\s*:\s*(\d+)',
                                    r'"mark_task_complete"\s*:\s*{\s*"task_id"\s*:\s*(\d+)',
                                    r'mark_task_failed\s*\(\s*task_id\s*=\s*(\d+)',
                                    r'mark_task_failed\s*\(\s*"task_id"\s*:\s*(\d+)',
                                    r'"mark_task_failed"\s*:\s*{\s*"task_id"\s*:\s*(\d+)',
                                    r'mark_task_skipped\s*\(\s*task_id\s*=\s*(\d+)',
                                    r'mark_task_skipped\s*\(\s*"task_id"\s*:\s*(\d+)',
                                    r'"mark_task_skipped"\s*:\s*{\s*"task_id"\s*:\s*(\d+)',
                                ]

                                for pattern in patterns:
                                    match = re.search(pattern, text_content)
                                    if match:
                                        task_id = int(match.group(1))
                                        # 确定动作类型
                                        if 'complete' in pattern:
                                            action_dict = {'mark_task_complete': {'task_id': task_id}}
                                        elif 'failed' in pattern:
                                            action_dict = {'mark_task_failed': {'task_id': task_id}}
                                        elif 'skipped' in pattern:
                                            action_dict = {'mark_task_skipped': {'task_id': task_id}}
                                        else:
                                            action_dict = {'mark_task_complete': {'task_id': task_id}}

                                        # 创建一个简单的 action wrapper
                                        class _FallbackAction:
                                            def __init__(self, action_dict):
                                                self._action_dict = action_dict

                                            def model_dump(self, **kwargs):
                                                return self._action_dict

                                            def get_index(self):
                                                for action_params in self._action_dict.values():
                                                    if isinstance(action_params, dict) and 'index' in action_params:
                                                        return action_params['index']
                                                return None

                                        actions = [_FallbackAction(action_dict)]
                                        logger.info(
                                            f"🔧 后备机制从文本中提取到任务状态动作: {action_dict} "
                                            f"(step {i + 1})"
                                        )
                                        break

                        # 第二级后备机制：即使 action 列表不为空，也检查 LLM 是否在 thinking/memory 中声明了任务完成
                        # 但没有在 action 中包含 mark_task_complete
                        # ⚠️ 安全守卫：如果当前步骤包含页面变更动作，跳过 memory 推断
                        # 避免模型在点击后还没验证结果就通过 memory 声明任务完成
                        _PAGE_CHANGING_ACTIONS_SET = {
                            'click', 'click_at_coordinates', 'go_to_url', 'scroll_down', 'scroll_up',
                            'switch_tab', 'go_back', 'select_option',
                        }
                        _step_has_page_change = False
                        for _act in actions:
                            _act_dump = _act.model_dump() if hasattr(_act, 'model_dump') else (_act if isinstance(_act, dict) else {})
                            if any(k in _PAGE_CHANGING_ACTIONS_SET for k in _act_dump):
                                _step_has_page_change = True
                                break

                        model_output = getattr(step, 'model_output', None)
                        # 调试日志：记录是否进入第二级后备机制
                        if (i + 1) <= 5 or (i + 1) % 5 == 0:  # 记录前5步和每5步
                            logger.info(
                                f"🔍 第二级后备机制条件 (step {i + 1}): model_output={bool(model_output)}, planned_tasks={bool(planned_tasks)}, planned_count={len(planned_tasks) if planned_tasks else 0}, page_change={_step_has_page_change}")
                        if model_output and planned_tasks and not _step_has_page_change:
                            import re
                            # 检查是否有任务在 thinking/memory 中被声明为完成，但 action 中没有标记
                            # 匹配模式: "Task X completed", "任务X已完成", "Task X is done", 等
                            memory_text = ''
                            for field_name in ['thinking', 'memory', 'evaluation_previous_goal']:
                                value = getattr(model_output, field_name, None)
                                if value:
                                    memory_text += str(value) + ' '

                            # 调试日志：记录 memory_text（当包含 complete/completed/done/finished/完成 时）
                            if any(keyword in memory_text.lower() for keyword in
                                   ['completed', 'done', 'finished', 'complete', '完成']):
                                logger.info(
                                    f"🔍 第二级后备机制检查 (step {i + 1}): memory_text包含完成声明, 片段={memory_text[:150]}...")

                            # 检查 action 中已经包含的任务状态动作
                            action_task_ids = set()
                            for action in actions:
                                action_info = _extract_action_info(action)
                                if action_info['action_name'] in ActionType.TASK_STATUS_ACTIONS:
                                    if action_info['task_id']:
                                        action_task_ids.add(action_info['task_id'])

                            # 在 memory 中查找声明为完成但未在 action 中标记的任务
                            # 匹配 "Task X completed", "任务X已完成", "task X done", "X and Y completed", "Tasks 1-2 completed"
                            # 还要匹配 "Tasks 1 and 2 are complete", "Task 1 is complete" 等格式
                            # 修复：只匹配明确的完成状态，避免 "Now starting task X" 被误判
                            # 使用更严格的正则，确保 "task X" 后面紧跟着完成词，或者完成词紧跟着 "task X"
                            completed_patterns = [
                                r'task\s+(\d+)\s+(?:is\s+)?(?:completed|done|finished|complete)(?!\s*successfully\s*started)',
                                r'tasks?\s+(\d+)\s+and\s+(\d+)\s+(?:are\s+)?(?:completed|done|finished|complete)',
                                r'tasks?\s+(\d+)\s*(?:-|to|–|至)\s*(\d+)\s+(?:are\s+)?(?:completed|done|finished|complete)',
                                r'(\d+)\s+and\s+(\d+)\s+(?:are\s+)?(?:completed|done|finished|complete)',
                                r'任务\s*(\d+)\s*(已完成|完成|done)',
                                r'task\s+(\d+)\s*,\s*task\s+(\d+)\s+completed',
                            ]

                            for pattern in completed_patterns:
                                match = re.search(pattern, memory_text, re.IGNORECASE)
                                if match:
                                    groups = match.groups()
                                    # 提取所有任务ID
                                    task_ids_from_match = []
                                    for g in groups:
                                        if g and g.isdigit():
                                            task_id = int(g)
                                            # 只添加有效的任务ID（在 planned_tasks 范围内）
                                            if 1 <= task_id <= len(planned_tasks):
                                                task_ids_from_match.append(task_id)

                                    # 特殊处理：如果有两个数字且它们形成范围（如 1-2），则生成范围内的所有任务ID
                                    if len(task_ids_from_match) == 2:
                                        start, end = task_ids_from_match
                                        if start < end:  # 确保是有效范围
                                            # 用范围内的所有任务替换原来的两个任务
                                            task_ids_from_match = list(range(start, end + 1))

                                    # 对于每个在 memory 中声明完成但没有在 action 中标记的任务，自动标记
                                    for task_id in task_ids_from_match:
                                        if task_id not in action_task_ids:
                                            # 检查任务是否已经处于完成状态
                                            task_already_completed = False
                                            for task in planned_tasks:
                                                if task.get('id') == task_id and task.get('status') in ['completed',
                                                                                                        'failed',
                                                                                                        'skipped']:
                                                    task_already_completed = True
                                                    break

                                            if not task_already_completed:
                                                # 自动添加标记任务完成的动作
                                                action_dict = {'mark_task_complete': {'task_id': task_id}}

                                                class _InferredAction:
                                                    def __init__(self, action_dict):
                                                        self._action_dict = action_dict

                                                    def model_dump(self, **kwargs):
                                                        return self._action_dict

                                                    def get_index(self):
                                                        for action_params in self._action_dict.values():
                                                            if isinstance(action_params, dict) and 'index' in action_params:
                                                                return action_params['index']
                                                        return None

                                                # 将推断的动作添加到 actions 列表的末尾，确保所有推断动作都能被处理
                                                actions.append(_InferredAction(action_dict))
                                                logger.info(
                                                    f"🔧 从 memory 推断并添加任务状态动作: {action_dict} "
                                                    f"(step {i + 1}) - LLM声明了任务完成但未在action中标记"
                                                )
                                                # 更新 action_task_ids 以避免重复添加
                                                action_task_ids.add(task_id)

                        current_active_task = get_next_active_task()
                        current_active_task_id = current_active_task.get('id') if current_active_task else None
                        current_active_task_desc = str(
                            current_active_task.get('description', '')) if current_active_task else ''
                        if current_active_task_id and any(
                                keyword in current_active_task_desc.lower() for keyword in ['登录', 'login']):
                            signal_text_parts = []
                            model_output = getattr(step, 'model_output', None)
                            for field_name in ['thinking', 'evaluation_previous_goal', 'memory', 'next_goal']:
                                value = getattr(model_output, field_name, None)
                                if value:
                                    signal_text_parts.append(str(value))

                            if _contains_auth_failure_signal(" ".join(signal_text_parts)):
                                if getattr(agent_instance, '_auth_failure_task_id', None) == current_active_task_id:
                                    agent_instance._auth_failure_count += 1
                                else:
                                    agent_instance._auth_failure_task_id = current_active_task_id
                                    agent_instance._auth_failure_count = 1

                                if agent_instance._auth_failure_count >= 3:
                                    logger.warning(
                                        f"⚠️ Login/auth failure threshold reached for task {current_active_task_id}; marking task failed"
                                    )
                                    await emit_callback({
                                        'type': 'log',
                                        'content': (
                                            f"\n[System]\n检测到登录连续失败 3 次，已自动将子任务 {current_active_task_id} 标记为失败并停止执行。\n"
                                        )
                                    })
                                    await emit_callback({
                                        'task_id': int(current_active_task_id),
                                        'status': 'failed'
                                    })
                                    raise KeyboardInterrupt("Repeated authentication failure")
                            elif getattr(agent_instance, '_auth_failure_task_id', None) == current_active_task_id:
                                agent_instance._auth_failure_count = 0

                        # ============================================================
                        # 任务状态动作检测和处理（使用新的辅助函数）
                        # ============================================================
                        step_has_terminal_action = False
                        step_marked_task_id = None
                        step_marked_task_status = None
                        detected_status_actions = []

                        for action in actions:
                            action_info = _extract_action_info(action)

                            # 检查是否是任务状态动作
                            if action_info['action_name'] in ActionType.TERMINAL_ACTIONS:
                                step_has_terminal_action = True
                                task_id = action_info['task_id']
                                task_status = action_info['status']

                                # 记录检测到的状态动作
                                detected_status_actions.append({
                                    'action': action_info['action_name'],
                                    'task_id': task_id,
                                    'status': task_status
                                })

                                # 验证 task_id
                                if task_id is not None and planned_tasks:
                                    is_valid, task, error_msg = _validate_task_id(task_id, planned_tasks)
                                    if not is_valid:
                                        logger.warning(f"⚠️ 任务状态动作验证失败: {error_msg}")

                                    # 对于 update_task_status，额外验证 status 值
                                    if action_info['action_name'] == ActionType.UPDATE_TASK_STATUS:
                                        status_params = action_info['action_params']
                                        if isinstance(status_params, list):
                                            status_params = status_params[0] if status_params and isinstance(
                                                status_params[0], dict) else {}
                                        if not isinstance(status_params, dict):
                                            status_params = {}
                                        status_valid, normalized_status, status_error = _validate_task_status_value(
                                            status_params.get('status'),
                                            ActionType.UPDATE_TASK_STATUS
                                        )
                                        if not status_valid:
                                            logger.warning(f"⚠️ {status_error}")

                                # 记录当前步骤标记的任务ID和状态，用于后续处理
                                step_marked_task_id = task_id
                                step_marked_task_status = task_status

                                # 不再 break，而是处理所有终端状态动作

                        # 如果检测到任务状态动作，记录日志并更新状态
                        if step_has_terminal_action and step_marked_task_id is not None:
                            # 使用 TaskStateManager 记录状态变更
                            if task_manager:
                                # 确定新状态值
                                new_status = step_marked_task_status
                                if new_status is None:
                                    # 根据动作类型推断状态
                                    action_name = detected_status_actions[0]['action']
                                    if action_name == ActionType.MARK_TASK_FAILED:
                                        new_status = 'failed'
                                    elif action_name == ActionType.MARK_TASK_SKIPPED:
                                        new_status = 'skipped'
                                    else:
                                        new_status = 'completed'

                                task_manager.update_status(
                                    task_id=step_marked_task_id,
                                    new_status=new_status,
                                    step_number=i + 1,
                                    trigger_action=detected_status_actions[0]['action']
                                )

                                # 发送状态更新事件到回调
                                if callback:
                                    status_payload = {
                                        'type': 'task_status_update',
                                        'task_id': step_marked_task_id,
                                        'status': new_status,
                                        'step_number': i + 1,
                                        'trigger_action': detected_status_actions[0]['action']
                                    }
                                    if asyncio.iscoroutinefunction(callback):
                                        await callback(status_payload)
                                    else:
                                        callback(status_payload)

                            logger.info(
                                f"📋 检测到任务状态动作: action={detected_status_actions[0]['action']}, "
                                f"task_id={step_marked_task_id}, status={step_marked_task_status or 'completed/failed/skipped'}"
                            )

                            # 检查是否重复标记已完成的任务
                            if planned_tasks:
                                for task in planned_tasks:
                                    if task['id'] == step_marked_task_id and task.get('status') in ['completed',
                                                                                                    'failed',
                                                                                                    'skipped']:
                                        next_expected = last_marked_task_id + 1
                                        logger.warning(
                                            f"⚠️ Task {step_marked_task_id} is already terminal ({task.get('status')})! "
                                            f"You should mark task {next_expected} instead."
                                        )
                                        break

                                # ============================================================
                                # 自动补全中间任务逻辑已移除
                                # 原有逻辑过于激进，可能导致非必填项被错误标记完成
                                # 现在采用更温和的策略：如果后续任务被标记，仅更新指针，不强制修改中间任务状态
                                # ============================================================

                            last_marked_task_id = step_marked_task_id

                            # 清除待处理状态
                            if getattr(agent_instance, '_pending_status_task_id', None) == step_marked_task_id:
                                logger.info(f"🔄 清除待处理任务状态: task_id={step_marked_task_id}")
                                agent_instance._pending_status_task_id = None
                                agent_instance._pending_status_task_description = None

                            # 重要修复：更新 last_marked_task_id 时，如果 AI 回溯标记了之前的任务（如先标4再标3），
                            # 不能简单覆盖，而是应该确保 last_marked_task_id 总是记录已完成的"最大"任务ID，
                            # 或者是当前正在执行的最前沿任务ID，防止后续告警逻辑（next_expected_task_id = last_marked_task_id + 1）混乱。
                            # 更好的做法是：遍历 planned_tasks 找到所有状态为 completed/failed/skipped 的任务中的最大 ID。
                            if planned_tasks:
                                max_marked_id = 0
                                for task in planned_tasks:
                                    if task.get('status') in ['completed', 'failed', 'skipped'] and task.get('id',
                                                                                                             0) > max_marked_id:
                                        max_marked_id = task.get('id', 0)
                                if max_marked_id > 0:
                                    last_marked_task_id = max_marked_id
                                else:
                                    last_marked_task_id = step_marked_task_id
                            else:
                                last_marked_task_id = step_marked_task_id

                            # ============================================================
                            # 检查是否所有任务都已达到终端状态，如果是则设置完成标志
                            # ============================================================
                            if planned_tasks and step_marked_task_id:
                                all_terminal, completed_count, total_count, terminal_tasks = _all_tasks_in_terminal_status(
                                    planned_tasks)

                                if all_terminal:
                                    logger.info(
                                        f"✅ 所有任务已完成: {completed_count}/{total_count} 任务已达到终端状态"
                                    )
                                    # 设置 _task_was_done 标志，触发停止
                                    _task_was_done = True
                                    logger.info("🏁 设置 _task_was_done = True，将在下一步停止执行")
                                else:
                                    # 记录当前进度
                                    pending_id = _get_pending_task_id(planned_tasks)
                                    logger.info(
                                        f"📊 任务进度: {completed_count}/{total_count} 已完成，"
                                        f"下一个待处理任务: task_id={pending_id}"
                                    )
                                    # 更新 agent 实例上的跟踪变量
                                    if pending_id:
                                        agent_instance._current_task_id = pending_id
                                        # 设置待处理任务状态
                                        agent_instance._pending_status_task_id = pending_id
                                        for task in planned_tasks:
                                            if task.get('id') == pending_id:
                                                agent_instance._pending_status_task_description = task.get(
                                                    'description', '')
                                                break

                        # 检查这一步是否有实际业务操作（非任务状态动作）
                        has_real_action = False
                        has_link_open_action = False

                        # 记录所有真实的业务动作
                        real_business_actions = []

                        for action in actions:
                            action_info = _extract_action_info(action)
                            action_name = action_info['action_name']

                            if action_name and action_name not in ActionType.TERMINAL_ACTIONS:
                                has_real_action = True
                                # 修复：将 action 转换为字典，避免 _ActionWrapper 序列化错误
                                if hasattr(action, 'model_dump'):
                                    real_business_actions.append(action.model_dump())
                                elif hasattr(action, '_action_dict'):
                                    real_business_actions.append(action._action_dict)
                                elif isinstance(action, dict):
                                    real_business_actions.append(action)
                                else:
                                    # Fallback: try to convert to dict or string
                                    try:
                                        real_business_actions.append(dict(action))
                                    except:
                                        real_business_actions.append(str(action))

                                if action_name in ['click', 'open_new_tab', 'navigate', 'go_to_url']:
                                    has_link_open_action = True
                                    # 注意：这里不再 break，因为我们需要收集所有业务动作

                            if has_real_action:
                                # 保持之前的逻辑：只要有一个真实动作就标记
                                pass

                        action_str = " | ".join([self._format_action(a) for a in actions])
                        log_content = f"\n[Step {i + 1}]\n执行: {action_str}\n"

                        if callback:
                            if asyncio.iscoroutinefunction(callback):
                                await callback({'type': 'log', 'content': log_content})
                            else:
                                callback({'type': 'log', 'content': log_content})

                        browser_session = getattr(agent_instance, 'browser_session', None)
                        if browser_session is not None:
                            try:
                                tabs = await browser_session.get_tabs()
                                current_tab_ids = {tab.target_id for tab in tabs}
                                if not known_tab_ids:
                                    known_tab_ids = current_tab_ids
                                else:
                                    new_tabs = [tab for tab in tabs if tab.target_id not in known_tab_ids]
                                    if new_tabs and has_link_open_action:
                                        newest_tab = new_tabs[-1]
                                        if browser_session.agent_focus_target_id != newest_tab.target_id:
                                            _, _, _, SwitchTabEvent, _ = _get_browser_use_imports()
                                            await browser_session.event_bus.dispatch(
                                                SwitchTabEvent(target_id=newest_tab.target_id)
                                            )
                                            logger.info(
                                                f"🔀 Auto-switched to newly opened tab {newest_tab.target_id[-4:]} after link click"
                                            )
                                            if callback:
                                                auto_switch_log = (
                                                    f"\n[System]\n检测到新标签页，已自动切换到 {newest_tab.target_id[-4:]}\n"
                                                )
                                                if asyncio.iscoroutinefunction(callback):
                                                    await callback({'type': 'log', 'content': auto_switch_log})
                                                else:
                                                    callback({'type': 'log', 'content': auto_switch_log})
                                    known_tab_ids = current_tab_ids
                            except Exception as tab_error:
                                logger.warning(f"⚠️ Failed to inspect/switch tabs after step {i + 1}: {tab_error}")

                        # ============================================================
                        # 智能任务状态推断：基于动作匹配的任务状态更新
                        # 如果当前步骤有业务动作，但没有显式标记任务完成，
                        # 尝试将这些动作匹配到当前待处理的任务上
                        # ============================================================
                        if has_real_action and not step_has_terminal_action and planned_tasks:
                            # 获取下一个预期任务
                            next_expected_task_id = last_marked_task_id + 1

                            # 查找该任务的描述
                            target_task = None
                            for task in planned_tasks:
                                if task.get('id') == next_expected_task_id and task.get('status') == 'pending':
                                    target_task = task
                                    break

                            if target_task:
                                task_desc = target_task.get('description', '')

                                # 检查当前动作是否匹配任务描述
                                # 1. 提取任务描述中的关键词/字面量
                                task_literals = _extract_task_literals(task_desc)

                                # 2. 检查动作是否包含这些字面量
                                action_matches_task = False
                                matched_literal = None

                                for action in real_business_actions:
                                    try:
                                        if isinstance(action, str):
                                            action_payload = action
                                        else:
                                            action_payload = json.dumps(action, ensure_ascii=False)
                                    except:
                                        action_payload = str(action)

                                    for literal in task_literals:
                                        if literal in action_payload:
                                            action_matches_task = True
                                            matched_literal = literal
                                            break

                                    # 增强推断：如果动作是 click，且任务描述包含 "点击" 或 "click"，并且没有其他更好的匹配
                                    # 我们可以尝试放宽匹配（但这有风险，所以只在没有任何字面量匹配时使用）
                                    if not action_matches_task and 'click' in action_payload:
                                        # 从 step.model_output 获取 thinking
                                        model_output = getattr(step, 'model_output', None)
                                        thinking_text = getattr(model_output, 'thinking', '') if model_output else ''

                                        # 检查 thinking 中是否提到了任务描述中的关键词
                                        # 1. 任务描述中的字面量匹配
                                        for literal in task_literals:
                                            if literal in thinking_text:
                                                action_matches_task = True
                                                matched_literal = f"thinking_match:{literal}"
                                                break

                                        # 2. 如果任务描述包含 "选择"、"下拉" 等词，且 Thinking 中也有，则匹配
                                        if not action_matches_task:
                                            keywords = ['选择', 'select', '下拉', 'dropdown', 'project', '项目']
                                            task_has_keyword = any(k in task_desc.lower() for k in keywords)
                                            thinking_has_keyword = any(k in thinking_text.lower() for k in keywords)
                                            if task_has_keyword and thinking_has_keyword:
                                                # 还需要确保 Thinking 中包含任务描述中的其他核心词（如“项目名”）
                                                # 简单的交叉检查：提取任务描述中的连续2个以上中文字符
                                                import re
                                                cn_phrases = re.findall(r'[\u4e00-\u9fa5]{2,}', task_desc)
                                                for phrase in cn_phrases:
                                                    if phrase in thinking_text:
                                                        action_matches_task = True
                                                        matched_literal = f"thinking_context_match:{phrase}"
                                                        break

                                    # 增强推断2：如果动作是 input，提取输入的 text
                                    # 检查 text 是否包含在任务描述中（反向匹配）
                                    if not action_matches_task and 'input' in action_payload and isinstance(action,
                                                                                                            dict) and 'input' in action:
                                        input_text = action['input'].get('text', '')
                                        # 1. 反向匹配：输入文本在任务描述中
                                        if input_text and len(str(input_text)) > 2 and str(input_text) in task_desc:
                                            action_matches_task = True
                                            matched_literal = f"reverse_match:{input_text}"

                                        # 2. Thinking 匹配：如果任务描述包含 "填写"、"输入"，且 Thinking 包含任务描述中的关键词
                                        if not action_matches_task:
                                            model_output = getattr(step, 'model_output', None)
                                            thinking_text = getattr(model_output, 'thinking',
                                                                    '') if model_output else ''

                                            keywords = ['填写', '输入', 'fill', 'enter', 'input', 'type']
                                            task_has_keyword = any(k in task_desc.lower() for k in keywords)

                                            if task_has_keyword:
                                                import re
                                                cn_phrases = re.findall(r'[\u4e00-\u9fa5]{2,}', task_desc)
                                                for phrase in cn_phrases:
                                                    if phrase in thinking_text:
                                                        action_matches_task = True
                                                        matched_literal = f"thinking_input_match:{phrase}"
                                                        break

                                    if action_matches_task:
                                        break

                                if action_matches_task:
                                    logger.info(
                                        f"🤖 智能推断: 动作匹配到任务 {next_expected_task_id} "
                                        f"(匹配关键词: '{matched_literal}')，自动标记为 completed"
                                    )

                                    # 自动标记任务完成
                                    if task_manager:
                                        task_manager.update_status(
                                            task_id=next_expected_task_id,
                                            new_status='completed',
                                            step_number=i + 1,
                                            trigger_action='auto_inferred_from_action'
                                        )

                                        # 发送状态更新事件
                                        if callback:
                                            status_payload = {
                                                'type': 'task_status_update',
                                                'task_id': next_expected_task_id,
                                                'status': 'completed',
                                                'step_number': i + 1,
                                                'trigger_action': 'auto_inferred_from_action'
                                            }
                                            if asyncio.iscoroutinefunction(callback):
                                                await callback(status_payload)
                                            else:
                                                callback(status_payload)

                                    # 更新 last_marked_task_id
                                    last_marked_task_id = next_expected_task_id

                                    # 清除待处理状态
                                    if getattr(agent_instance, '_pending_status_task_id',
                                               None) == next_expected_task_id:
                                        agent_instance._pending_status_task_id = None
                                        agent_instance._pending_status_task_description = None

                        # 记录未标记任务的步骤（不自动修复，仅警告）
                        # 修改条件：只有在智能推断也没有生效的情况下才警告
                        current_step_marked = (step_marked_task_id is not None) or \
                                              (has_real_action and last_marked_task_id == next_expected_task_id)

                        if has_real_action and not current_step_marked and planned_tasks:
                            next_expected_task_id = last_marked_task_id + 1
                            if next_expected_task_id <= len(planned_tasks):
                                # 检查这个任务是否还没有被标记
                                task_already_marked = False
                                for task in planned_tasks:
                                    if task['id'] == next_expected_task_id and task.get('status') in ['completed',
                                                                                                      'failed',
                                                                                                      'skipped']:
                                        task_already_marked = True
                                        last_marked_task_id = next_expected_task_id
                                        break

                                if not task_already_marked:
                                    # 记录警告，提示 AI 标记当前任务
                                    agent_instance._pending_status_task_id = next_expected_task_id
                                    pending_task_description = None
                                    if planned_tasks:
                                        for task in planned_tasks:
                                            if task.get('id') == next_expected_task_id:
                                                pending_task_description = task.get('description')
                                                break
                                    agent_instance._pending_status_task_description = pending_task_description
                                    logger.warning(
                                        f"⚠️ Step {i + 1} had actions but no task status update. "
                                        f"Please mark task {next_expected_task_id} as completed, failed, or skipped.")

                    except Exception as e:
                        logger.warning(f"⚠️ Error in on_step_end processing: {e}")
                last_processed_step = len(history)

        try:
            # Try to pass callback
            import inspect
            sig = inspect.signature(agent.run)
            if 'on_step_end' in sig.parameters:
                await agent.run(max_steps=100, on_step_end=on_step_end)
            else:
                await agent.run(max_steps=100)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error(f"Agent execution error: {e}")
            raise

        # 在任务结束时检查不一致的任务状态
        history = getattr(agent, 'history', [])
        if history:
            logger.info("🔍 Performing final task status consistency check")
            # 检查是否有任务执行了但未标记完成，并进行最终结算
            # 注意：这里的 planned_tasks 参数必须是最新的任务列表（包含当前状态）
            # 我们需要从 task_manager 获取最新的任务状态，或者传入正确的 planned_tasks

            # 如果 task_manager 存在，我们优先使用它里面的最新任务列表
            latest_tasks = planned_tasks
            if task_manager and hasattr(task_manager, 'tasks'):
                latest_tasks = task_manager.tasks
            latest_tasks = _sanitize_planned_tasks(latest_tasks)

            try:
                executed_tasks_info = self._find_executed_tasks(history, latest_tasks)
                if not isinstance(executed_tasks_info, dict):
                    executed_tasks_info = {
                        'marked_tasks': [],
                        'inferred_completed_tasks': [],
                        'executed_actions': 0,
                        'unmarked_actions': []
                    }
            except Exception as settlement_error:
                logger.error(f"❌ Final consistency settlement failed: {settlement_error}", exc_info=True)
                executed_tasks_info = {
                    'marked_tasks': [],
                    'inferred_completed_tasks': [],
                    'executed_actions': 0,
                    'unmarked_actions': []
                }

                has_done_success = False
                for step in getattr(history, 'steps', []):
                    for action in getattr(step, 'actions', []):
                        action_dict = _extract_action_dict(action)
                        if not isinstance(action_dict, dict):
                            continue
                        done_params = action_dict.get('done')
                        if isinstance(done_params, dict) and done_params.get('success') is True:
                            has_done_success = True
                            break
                    if has_done_success:
                        break

                if has_done_success and latest_tasks:
                    fallback_inferred = []
                    for task in latest_tasks:
                        if task.get('status') in {'pending', 'in_progress'}:
                            task_id = task.get('id')
                            if task_id is not None:
                                fallback_inferred.append(task_id)
                    if fallback_inferred:
                        logger.warning(
                            f"⚠️ Settlement fallback enabled due to exception; "
                            f"marking pending tasks as completed because done(success=True) exists: {fallback_inferred}"
                        )
                        executed_tasks_info['inferred_completed_tasks'] = fallback_inferred

            # 将推断出的完成任务同步到任务管理器
            if executed_tasks_info.get('inferred_completed_tasks') and task_manager:
                for task_id in executed_tasks_info['inferred_completed_tasks']:
                    logger.info(f"🔄 自动同步结算状态: Task {task_id} -> completed")
                    task_manager.update_status(
                        task_id=task_id,
                        new_status='completed',
                        step_number=len(history.steps) if hasattr(history, 'steps') else 0,
                        trigger_action='final_consistency_settlement'
                    )
                    if callback:
                        status_payload = {
                            'type': 'task_status_update',
                            'task_id': task_id,
                            'status': 'completed',
                            'step_number': len(history.steps) if hasattr(history, 'steps') else 0,
                            'trigger_action': 'final_consistency_settlement'
                        }
                        if asyncio.iscoroutinefunction(callback):
                            await callback(status_payload)
                        else:
                            callback(status_payload)

            if (
                    executed_tasks_info
                    and executed_tasks_info.get('executed_actions', 0) > len(
                executed_tasks_info.get('marked_tasks', []))
                    and executed_tasks_info.get('unmarked_actions')
            ):
                logger.warning(
                    f"⚠️ Found {executed_tasks_info['executed_actions']} executed actions, but only {len(executed_tasks_info['marked_tasks'])} tasks were explicitly marked complete")
                logger.warning(f"⚠️ Unmarked actions: {executed_tasks_info['unmarked_actions']}")
                logger.warning("⚠️ This indicates the AI agent did not follow the 'mark_task_complete' rule properly.")

        return history

    def _find_executed_tasks(self, history, planned_tasks=None):
        """
        通过分析执行历史找出已执行但未标记完成的任务，并进行最终一致性结算
        """
        if not history or not hasattr(history, 'steps'):
            return {
                'marked_tasks': [],
                'inferred_completed_tasks': [],
                'executed_actions': 0,
                'unmarked_actions': []
            }

        executed_actions = {}  # 已执行的操作类型和索引，以及对应的步骤
        marked_tasks = set()  # 已标记完成的任务ID
        action_footprints = []  # 记录所有动作的文本足迹

        # 分析执行历史
        for step_idx, step in enumerate(getattr(history, 'steps', [])):
            # 提取 thinking 作为足迹的一部分
            model_output = getattr(step, 'model_output', None)
            thinking = getattr(model_output, 'thinking', '') if model_output else ''
            if thinking:
                action_footprints.append(thinking.lower())

            # 检查每一步中的actions
            actions = getattr(step, 'actions', [])
            for action in actions:
                # 提取动作相关的文本作为足迹
                action_text = ""

                # 处理 action 是字典的情况 (兼容性增强)
                try:
                    action_dict = action if isinstance(action, dict) else (
                        action.model_dump() if hasattr(action, 'model_dump') else {})
                    if isinstance(action_dict, list):
                        logger.warning(f"⚠️ action_dict is a list, converting to dict: {action_dict}")
                        # 尝试提取第一个元素，如果它是字典
                        action_dict = action_dict[0] if action_dict and isinstance(action_dict[0], dict) else {}
                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse action_dict: {e}")
                    action_dict = {}

                # 记录已执行的操作
                # 兼容对象访问和字典访问
                if hasattr(action, 'input') and action.input:
                    action_key = f"input_{action.input.index}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'input',
                        'index': action.input.index,
                        'text': getattr(action.input, 'text', '')
                    }
                    action_text = getattr(action.input, 'text', '')
                elif 'input' in action_dict:
                    input_params = action_dict['input']
                    if isinstance(input_params, list):
                        input_params = input_params[0] if input_params else {}
                    if not isinstance(input_params, dict):
                        input_params = {}

                    idx = input_params.get('index', 0)
                    text = input_params.get('text', '')
                    action_key = f"input_{idx}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'input',
                        'index': idx,
                        'text': text
                    }
                    action_text = text

                elif hasattr(action, 'click') and action.click:
                    action_key = f"click_{action.click.index}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'click',
                        'index': action.click.index
                    }
                elif 'click' in action_dict:
                    click_params = action_dict['click']
                    if isinstance(click_params, list):
                        click_params = click_params[0] if click_params else {}
                    if not isinstance(click_params, dict):
                        click_params = {'index': click_params} if isinstance(click_params, int) else {}

                    idx = click_params.get('index', 0)
                    action_key = f"click_{idx}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'click',
                        'index': idx
                    }

                elif hasattr(action, 'switch_tab') and action.switch_tab:
                    action_key = f"switch_tab_{action.switch_tab.tab_id}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'switch_tab',
                        'tab_id': action.switch_tab.tab_id
                    }
                elif 'switch_tab' in action_dict:
                    switch_params = action_dict['switch_tab']
                    if isinstance(switch_params, list):
                        switch_params = switch_params[0] if switch_params else {}
                    if not isinstance(switch_params, dict):
                        # Handle raw string/int tab_id
                        switch_params = {'tab_id': switch_params} if switch_params else {}

                    tab_id = switch_params.get('tab_id', 0)
                    action_key = f"switch_tab_{tab_id}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'switch_tab',
                        'tab_id': tab_id
                    }

                # 处理 done 动作
                if hasattr(action, 'done') and action.done:
                    # 如果有 done 动作，认为任务已全部完成
                    pass
                elif 'done' in action_dict:
                    pass

                if action_text:
                    action_footprints.append(action_text.lower())

                # 记录已标记完成的任务
                task_id_marked = None
                if hasattr(action, 'mark_task_complete') and action.mark_task_complete:
                    task_id_marked = action.mark_task_complete.task_id
                elif 'mark_task_complete' in action_dict:
                    mtc_params = action_dict['mark_task_complete']
                    if isinstance(mtc_params, list):
                        mtc_params = mtc_params[0] if mtc_params else {}
                    if not isinstance(mtc_params, dict):
                        mtc_params = {'task_id': mtc_params} if isinstance(mtc_params, int) else {}

                    task_id_marked = mtc_params.get('task_id')
                elif hasattr(action, 'update_task_status') and action.update_task_status:
                    if str(getattr(action.update_task_status, 'status', '')).lower() == 'completed':
                        task_id_marked = action.update_task_status.task_id
                elif 'update_task_status' in action_dict:
                    uts_params = action_dict['update_task_status']
                    if isinstance(uts_params, list):
                        uts_params = uts_params[0] if uts_params else {}
                    if not isinstance(uts_params, dict):
                        uts_params = {}

                    if str(uts_params.get('status', '')).lower() == 'completed':
                        task_id_marked = uts_params.get('task_id')

                if task_id_marked is not None:
                    marked_tasks.add(task_id_marked)

        # 理想情况下应该有一个映射机制来关联操作和任务，但由于我们没有这个映射，
        # 我们只能记录未标记完成的执行操作作为调试信息
        unmarked_actions = []
        for action_key, action_info in executed_actions.items():
            unmarked_actions.append({
                'action': action_info['action'],
                'step': action_info['step'],
                'details': action_key
            })

        # =====================================================================
        # 最终一致性结算 (Final Consistency Settlement)
        # 如果提供了 planned_tasks，则根据动作足迹进行状态修正
        # =====================================================================
        planned_tasks = _sanitize_planned_tasks(planned_tasks)
        inferred_completed_tasks = set()
        if planned_tasks:
            # 获取最大已标记任务ID，用于判断是否到达终点
            max_marked_id = max(marked_tasks) if marked_tasks else 0

            # 如果存在 done 动作，或者 max_marked_id > 1，开始结算
            # 检查是否有 done 动作
            has_done_action = False
            for step in getattr(history, 'steps', []):
                actions = getattr(step, 'actions', [])
                for action in actions:
                    try:
                        action_dict = action if isinstance(action, dict) else (
                            action.model_dump() if hasattr(action, 'model_dump') else {})
                        if isinstance(action_dict, list):
                            action_dict = action_dict[0] if action_dict and isinstance(action_dict[0], dict) else {}
                    except Exception:
                        action_dict = {}

                    if hasattr(action, 'done') and action.done:
                        has_done_action = True
                        break
                    elif 'done' in action_dict:
                        has_done_action = True
                        break
                if has_done_action: break

            # 如果有 done 动作，将 max_marked_id 视为无穷大（或最后一个任务ID）
            if has_done_action:
                max_planned_id = 0
                try:
                    # 安全地计算 max_planned_id，防止 planned_tasks 中包含非字典元素
                    for t in planned_tasks:
                        if isinstance(t, dict):
                            tid = t.get('id', 0)
                            if tid > max_planned_id:
                                max_planned_id = tid
                        # 兼容对象访问
                        elif hasattr(t, 'id'):
                            tid = getattr(t, 'id', 0)
                            if tid > max_planned_id:
                                max_planned_id = tid
                        elif isinstance(t, list):
                            logger.warning(f"⚠️ planned_tasks 包含 list 元素: {t}")
                except Exception as e:
                    logger.error(f"❌ 计算 max_planned_id 失败: {e}")

                max_marked_id = max(max_marked_id, max_planned_id + 1)  # 确保覆盖所有任务
                logger.info("✅ 检测到 done 动作，启动全量最终一致性结算")

            # 如果 AI 标记了 done 或者最大的 task_id，说明流程结束，开始结算
            # (这里的判断比较简单，假设只要有 marked_tasks 就可能需要结算中间的)
            if max_marked_id > 1:
                import re
                combined_footprint = " ".join(action_footprints)

                for task in planned_tasks:
                    # 确保 task 是字典
                    if not isinstance(task, dict):
                        if hasattr(task, 'model_dump'):
                            task = task.model_dump()
                        elif hasattr(task, '__dict__'):
                            task = task.__dict__
                        else:
                            # 如果是列表或其他无法转换的类型，跳过
                            continue

                    task_id = task.get('id')
                    task_status = task.get('status', 'pending')
                    task_desc = task.get('description', '').lower()

                    # 只处理未标记的中间任务
                    if task_id < max_marked_id and task_status == 'pending':
                        is_matched = False

                        # 策略1：使用之前强大的字面量提取逻辑
                        literals = _extract_task_literals(task_desc)
                        for literal in literals:
                            if literal.lower() in combined_footprint:
                                is_matched = True
                                logger.info(f"✅ [最终一致性结算] 任务 {task_id} 匹配到字面量: '{literal}'")
                                break

                        # 策略2：提取核心中文词组，过滤掉常见动词/名词
                        if not is_matched:
                            # 过滤掉常见的导致误判或匹配失败的词
                            stop_words = ['点击', '按钮', '填写', '输入', '选择', '下拉框', '验证', '是否', '页面',
                                          '进入', '打开', '当前时间戳', '新增的', '关联项目']
                            clean_desc = task_desc
                            for word in stop_words:
                                clean_desc = clean_desc.replace(word, ' ')

                            # 提取所有包含数字、字母或连续中文的片段，这些更有可能是关键信息
                            key_phrases = re.findall(r'[a-zA-Z0-9.\-_]+|[\u4e00-\u9fa5]{2,}', clean_desc)

                            # 只要有一个核心词组出现在足迹中，就认为匹配成功（降低阈值，因为核心词更有代表性）
                            for phrase in key_phrases:
                                if phrase and len(phrase) >= 2 and phrase in combined_footprint:
                                    is_matched = True
                                    logger.info(f"✅ [最终一致性结算] 任务 {task_id} 匹配到核心词: '{phrase}'")
                                    break

                        # 策略3：非常短的描述直接匹配
                        if not is_matched and 2 < len(task_desc) <= 6 and task_desc in combined_footprint:
                            is_matched = True
                            logger.info(f"✅ [最终一致性结算] 任务 {task_id} 匹配到短描述")

                        if is_matched:
                            inferred_completed_tasks.add(task_id)
                            logger.info(
                                f"✅ [最终一致性结算] 任务 {task_id} 未被显式标记，但足迹匹配成功，推断为 completed")
                        else:
                            # 没有匹配到足迹，说明可能是被跳过的非必填项
                            logger.info(
                                f"⏭️ [最终一致性结算] 任务 {task_id} 未被显式标记，且无足迹 (desc='{task_desc}')，推断为 skipped")
                            # logger.debug(f"   Footprint sample: {combined_footprint[:200]}...")

        return {
            'marked_tasks': list(marked_tasks),
            'inferred_completed_tasks': list(inferred_completed_tasks),
            'executed_actions': len(executed_actions),
            'unmarked_actions': unmarked_actions
        }

    async def run_full_process(self, task_description: str, analysis_callback=None, step_callback=None,
                               should_stop=None):
        planned_tasks = await self.analyze_task(task_description)
        if analysis_callback:
            if asyncio.iscoroutinefunction(analysis_callback):
                await analysis_callback(planned_tasks)
            else:
                analysis_callback(planned_tasks)

        return await self.run_task(task_description, planned_tasks, step_callback, should_stop)
