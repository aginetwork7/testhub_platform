import asyncio
import logging

from .ai_base import BaseBrowserAgent
from .hermes_agent import HermesAgent
from .runtime.pyui_compat import PyUICompatAgent

logger = logging.getLogger('django')


class BrowserAgent(BaseBrowserAgent):
    """
    Standard Browser Agent for Text Mode.
    Inherits all base functionality without applying dangerous visual patches.
    """

    def __init__(self, execution_mode='text', enable_gif=True, case_name=None):
        self.enable_gif = enable_gif
        self.case_name = case_name or 'Adhoc Task'
        super().__init__(execution_mode='text', enable_gif=enable_gif, case_name=self.case_name)


def _should_use_pyui_compat(execution_mode='text', case_mode='freeform', task_steps=None):
    if execution_mode == 'planner_v2':
        return True

    return (
        execution_mode == 'text'
        and case_mode in {'structured', 'hybrid'}
        and isinstance(task_steps, list)
        and bool(task_steps)
    )


def get_agent_class(execution_mode='text', case_mode='freeform', task_steps=None):
    if _should_use_pyui_compat(execution_mode=execution_mode, case_mode=case_mode, task_steps=task_steps):
        return PyUICompatAgent
    if execution_mode == 'hermes':
        return HermesAgent
    return BrowserAgent


def run_ai_task_sync(task_description: str, planned_tasks=None, callback=None, should_stop=None, execution_mode='text', case_mode='freeform', task_steps=None):
    agent_class = get_agent_class(execution_mode, case_mode=case_mode, task_steps=task_steps)
    agent = agent_class(execution_mode=execution_mode)
    return asyncio.run(agent.run_task(task_description, planned_tasks, callback, should_stop))


def analyze_task_sync(task_description: str, execution_mode='text', case_mode='freeform', task_steps=None):
    agent_class = get_agent_class(execution_mode, case_mode=case_mode, task_steps=task_steps)
    agent = agent_class(execution_mode=execution_mode)
    return asyncio.run(agent.analyze_task(task_description, case_mode=case_mode, task_steps=task_steps))


def run_full_process_sync(task_description: str, analysis_callback=None, step_callback=None, should_stop=None, execution_mode='text', enable_gif=True, case_name=None, case_mode='freeform', task_steps=None, use_cache=True, execution_user_id=None, environment_configuration=None, ai_project_id=None, execution_record_id=None, ai_case_id=None):
    logger.info(f'DEBUG: Entering run_full_process_sync with execution_mode={execution_mode}, enable_gif={enable_gif}')

    agent_class = get_agent_class(execution_mode, case_mode=case_mode, task_steps=task_steps)
    agent_kwargs = {
        'execution_mode': execution_mode,
        'enable_gif': enable_gif,
        'case_name': case_name,
    }
    if agent_class is PyUICompatAgent:
        agent_kwargs['execution_user_id'] = execution_user_id
        agent_kwargs['environment_configuration'] = environment_configuration
        agent_kwargs['ai_project_id'] = ai_project_id
        agent_kwargs['execution_record_id'] = execution_record_id
        agent_kwargs['ai_case_id'] = ai_case_id
    agent = agent_class(**agent_kwargs)
    if hasattr(agent, 'use_cache'):
        agent.use_cache = bool(use_cache)

    logger.info(f'DEBUG: Agent created successfully ({type(agent).__name__}), starting asyncio.run')
    return asyncio.run(
        agent.run_full_process(
            task_description,
            analysis_callback,
            step_callback,
            should_stop,
            case_mode=case_mode,
            task_steps=task_steps,
        )
    )