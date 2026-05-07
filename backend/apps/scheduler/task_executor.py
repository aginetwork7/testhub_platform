"""
任务执行器模块
统一管理所有模块的异步任务执行
"""
import re
from django.utils import timezone
from django_q.tasks import async_task
from django_q.models import Schedule
from loguru import logger


def _update_task_stats(schedule_id, success=True):
    """更新任务执行统计"""
    try:
        from apps.scheduler.models import ScheduleConfig
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        config.update_stats(success=success)
    except Exception as e:
        logger.error(f"更新任务统计失败: {e}")


def _generate_dingtalk_sign(secret, timestamp):
    """生成钉钉机器人签名"""
    try:
        import urllib.parse
        import base64
        import hmac
        import hashlib
        
        if secret:
            string_to_sign = f'{timestamp}\n{secret}'
            string_to_sign_enc = string_to_sign.encode('utf-8')
            secret_enc = secret.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            return sign
        return None
    except Exception as e:
        logger.error(f"生成钉钉签名失败: {e}")
        return None


def _build_wechat_message(rendered_content):
    """构建企微消息体"""
    return {
        "msgtype": "markdown",
        "markdown": {
            "content": rendered_content
        }
    }


def _build_feishu_message(rendered_content, status_text, success):
    """构建飞书消息体"""
    import re
    content = rendered_content
    content = re.sub(r'^#{1,6}\s*', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n#{1,6}\s*', '\n', content)
    
    return {
        "msg_type": "interactive",
        "card": {
            "elements": [{
                "tag": "div",
                "text": {
                    "content": content,
                    "tag": "lark_md"
                }
            }],
            "header": {
                "title": {
                    "content": f"定时任务执行{status_text}",
                    "tag": "plain_text"
                },
                "template": "green" if success else "red"
            }
        }
    }


def _build_dingtalk_message(rendered_content, status_text):
    """构建钉钉消息体"""
    if not rendered_content:
        rendered_content = ""

    # 使用正则表达式统一处理所有换行符
    # 先将 \r\n 和 \r 统一为 \n
    rendered_content = re.sub(r'\r\n|\r', '\n', rendered_content)
    # 将连续的多个换行符（2 个以上）替换为两个 \n
    rendered_content = re.sub(r'\n{2,}', '\n\n', rendered_content)
    # 将单个换行符替换为两个 \n（钉钉 Markdown 格式要求）
    rendered_content = re.sub(r'(?<!\n)\n(?!\n)', '\n\n', rendered_content)
    return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"定时任务执行{status_text}",
                "text": rendered_content
            }
        }


def _get_email_template(email_notification_configs, config):
    """获取邮件模板"""
    from apps.core.models import NotificationTemplate
    
    email_template = None
    
    # 优先从邮件通知配置中获取模板
    logger.info(f"开始从通知配置中查找邮件模板，email_notification_configs 数量: {len(email_notification_configs)}")
    for idx, email_config in enumerate(email_notification_configs):
        logger.info(f"检查通知配置 {idx}: id={email_config.id}, name={email_config.name}, config_type={email_config.config_type}")
        logger.info(f"  notification_template: {email_config.notification_template}")
        if email_config.notification_template:
            logger.info(f"  template_type: {email_config.notification_template.template_type}")
            logger.info(f"  template_type 是否匹配: {email_config.notification_template.template_type in ['html', 'text', 'markdown']}")
        if email_config.notification_template and email_config.notification_template.template_type in ['html', 'text', 'markdown']:
            email_template = email_config.notification_template
            logger.info(f"使用通知配置的邮件模板: {email_template.name}")
            break
    else:
        logger.info(f"通知配置中没有找到有效的模板")
    
    # 如果通知配置中没有模板，则从 ScheduleConfig 中获取
    logger.info(f"检查任务配置的模板: config.notification_template={config.notification_template}")
    if not email_template and config.notification_template:
        logger.info(f"  任务配置有模板，检查类型: {config.notification_template.template_type}")
        logger.info(f"  template_type 是否匹配: {config.notification_template.template_type in ['html', 'text', 'markdown']}")
        if config.notification_template.template_type in ['html', 'text', 'markdown']:
            email_template = config.notification_template
            logger.info(f"使用任务配置的邮件模板: {email_template.name}")
    else:
        logger.info(f"任务配置中没有找到有效的模板")
    
    # 如果还是没有模板，则查找默认模板
    if not email_template:
        logger.info("开始查找默认邮件模板")
        email_template = NotificationTemplate.get_default_template('html')
        if email_template:
            logger.info(f"使用默认邮件模板: {email_template.name}")
        else:
            logger.warning("未找到邮件模板，使用默认内容")
    
    return email_template


def execute_task(schedule_id, is_manual_execution=True, executed_by_id=None):
    """
    执行定时任务
    :param schedule_id: Django-Q Schedule ID
    :param is_manual_execution: 是否立即执行（默认为True，表示手动触发）
    :param executed_by_id: 执行用户ID（可选，用于记录实际执行者）
    :return: 任务ID
    """
    logger.info(f"execute_task 被调用: schedule_id={schedule_id}, is_manual_execution={is_manual_execution}, executed_by_id={executed_by_id}")
    
    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        logger.error(f"调度不存在: {schedule_id}")
        return None
    
    # 检查任务是否被暂停（手动执行时跳过此检查）
    try:
        from apps.scheduler.models import ScheduleConfig
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        if not is_manual_execution and (config.status == 'PAUSED' or not schedule.enabled):
            logger.info(f"任务已暂停，跳过执行: {schedule.name}")
            return None
    except ScheduleConfig.DoesNotExist:
        config = None
    
    group_name = schedule.name
    if config:
        group_name = config.get_module_display()
    
    task_id = async_task(
        'apps.scheduler.task_executor.execute_scheduled_task',
        schedule_id,
        is_manual_execution,
        executed_by_id,
        group=group_name
    )
    logger.info(f"任务已提交: {schedule.name}, task_id={task_id}, is_manual_execution={is_manual_execution}, executed_by_id={executed_by_id}")
    return task_id


def execute_scheduled_task(*args, **kwargs):
    """
    执行定时任务的入口函数，根据任务类型调用对应的执行器
    :param args:
    :param kwargs:
    :return:
    """
    from apps.scheduler.models import ScheduleConfig
    
    schedule_id = None
    is_manual_execution = False
    executed_by_id = None
    
    logger.info(f"execute_scheduled_task: args={args}, kwargs={kwargs}")
    
    try:
        # 优先使用 kwargs 中的参数
        schedule_id = kwargs.get('schedule_id')
        is_manual_execution = kwargs.get('is_manual_execution', False)
        executed_by_id = kwargs.get('executed_by_id', None)
        
        # 兼容处理：如果 kwargs 中没有参数，尝试从 args 获取
        if not schedule_id and args:
            schedule_id = args[0]
            if len(args) > 1:
                is_manual_execution = args[1]
            if len(args) > 2:
                executed_by_id = args[2]
        
        # 兼容处理：如果 schedule_id 是列表，取第一个元素
        if isinstance(schedule_id, list):
            schedule_id = schedule_id[0] if schedule_id else None
        
        if not schedule_id:
            logger.error("schedule_id 为空")
            return
        
        schedule = Schedule.objects.get(id=schedule_id)
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        
        # 检查任务是否被暂停（手动执行时跳过此检查）
        if not is_manual_execution and (config.status == 'PAUSED' or not schedule.enabled):
            logger.info(f"任务已暂停，跳过执行: {schedule.name}")
            return
    except (Schedule.DoesNotExist, ScheduleConfig.DoesNotExist) as e:
        logger.error(f"获取任务配置失败: {e}")
        return
    
    task_type = config.task_type
    
    logger.info(f"execute_scheduled_task: task_type={task_type}, is_manual_execution={is_manual_execution}, executed_by_id={executed_by_id}")
    
    if task_type == 'API_TEST_SUITE':
        execute_api_test_suite(schedule_id=schedule_id, is_manual_execution=is_manual_execution, executed_by_id=executed_by_id)
    elif task_type == 'API_REQUEST':
        execute_api_request(schedule_id=schedule_id, is_manual_execution=is_manual_execution, executed_by_id=executed_by_id)
    elif task_type == 'UI_TEST_SUITE':
        execute_ui_test_suite(schedule_id=schedule_id, is_manual_execution=is_manual_execution, executed_by_id=executed_by_id)
    elif task_type == 'UI_TEST_CASE':
        execute_ui_test_cases(schedule_id=schedule_id, is_manual_execution=is_manual_execution, executed_by_id=executed_by_id)
    elif task_type == 'APP_TEST_SUITE':
        execute_app_test_suite(schedule_id=schedule_id, is_manual_execution=is_manual_execution, executed_by_id=executed_by_id)
    elif task_type == 'APP_TEST_CASE':
        execute_app_test_cases(schedule_id=schedule_id, is_manual_execution=is_manual_execution, executed_by_id=executed_by_id)
    else:
        logger.error(f"未知的任务类型: {task_type}")


def execute_api_test_suite(*args, **kwargs):
    """执行API测试套件"""
    from apps.scheduler.models import ScheduleConfig
    from apps.api_testing.models import TestSuite, Environment
    
    # 获取 is_manual_execution 参数
    is_manual_execution = kwargs.get('is_manual_execution', False)
    executed_by_id = kwargs.get('executed_by_id', None)
    
    schedule_id = None
    try:
        # 优先使用 kwargs 中的 schedule_id（新数据）
        schedule_id = kwargs.get('schedule_id')
        
        # 兼容旧数据：如果 kwargs 中没有 schedule_id，尝试从 args 获取
        if not schedule_id and args:
            schedule_id = args[0]
        
        # 兼容处理：如果 schedule_id 是列表，取第一个元素
        if isinstance(schedule_id, list):
            schedule_id = schedule_id[0] if schedule_id else None
        
        if not schedule_id:
            logger.error("schedule_id 为空")
            return
        
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        test_suite = TestSuite.objects.get(id=config.target_id)
        
        environment = None
        if config.environment_id:
            from apps.api_testing.models import Environment
            environment = Environment.objects.get(id=config.environment_id)
        
        logger.info(f"开始执行API测试套件: {test_suite.name}")
        
        from apps.api_testing.utils import execute_test_suite as execute_test_suite_util
        result = execute_test_suite_util(test_suite, environment, config.created_by)
        
        logger.info(f"API测试套件执行完成: {test_suite.name}, 结果: {result}")
        
        # 更新执行统计
        _update_task_stats(schedule_id, success=result.get('success', False))
        
        if config.notify_on_success or config.notify_on_failure:
            send_notification(config, result.get('success', False), result, is_manual_execution, executed_by_id)
        
        # 返回结果以便 Django-Q 记录到 Success 表
        return result
        
    except Exception as e:
        logger.error(f"执行API测试套件失败: {e}", exc_info=True)
        logger.error(f"任务ID: {schedule_id}, 错误类型: {type(e).__name__}")
        # 更新执行统计（失败）
        if schedule_id:
            _update_task_stats(schedule_id, success=False)
        try:
            config = ScheduleConfig.objects.get(schedule__id=schedule_id)
            logger.error(f"任务配置: {config.schedule.name}, 模块: {config.get_module_display()}")
            if config.notify_on_failure:
                send_notification(config, False, {'error': str(e)})
        except Exception as notify_error:
            logger.error(f"发送失败通知时出错: {notify_error}", exc_info=True)
        # 重新抛出异常以便 Django-Q 记录到 Failure 表
        raise


def execute_api_request(*args, **kwargs):
    """执行单个API请求"""
    from apps.scheduler.models import ScheduleConfig
    from apps.api_testing.models import ApiRequest, Environment
    
    schedule_id = None
    try:
        # 优先使用 kwargs 中的 schedule_id（新数据）
        schedule_id = kwargs.get('schedule_id')
        
        # 兼容旧数据：如果 kwargs 中没有 schedule_id，尝试从 args 获取
        if not schedule_id and args:
            schedule_id = args[0]
        
        # 兼容处理：如果 schedule_id 是列表，取第一个元素
        if isinstance(schedule_id, list):
            schedule_id = schedule_id[0] if schedule_id else None
        
        if not schedule_id:
            logger.error("schedule_id 为空")
            return
        
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        api_request = ApiRequest.objects.get(id=config.target_id)
        
        environment = None
        if config.environment_id:
            environment = Environment.objects.get(id=config.environment_id)
        
        logger.info(f"开始执行API请求: {api_request.name}")
        
        from apps.api_testing.utils import execute_api_request as execute_api_request_util
        result = execute_api_request_util(api_request, environment, config.created_by)
        
        logger.info(f"API请求执行完成: {api_request.name}")
        logger.info(f"API请求执行结果: {result}")
        
        # 更新执行统计
        _update_task_stats(schedule_id, success=result.get('success', False))
        
        # 检查是否是立即执行
        is_manual_execution = kwargs.get('is_manual_execution', False)
        executed_by_id = kwargs.get('executed_by_id', None)
        
        logger.info(f"execute_api_request: is_manual_execution={is_manual_execution}, executed_by_id={executed_by_id}, kwargs={kwargs}")
        
        if config.notify_on_success or config.notify_on_failure:
            send_notification(config, result.get('success', False), result, is_manual_execution, executed_by_id)
        
        # 返回结果以便 Django-Q 记录到 Success 表
        return result
        
    except Exception as e:
        logger.error(f"执行API请求失败: {e}", exc_info=True)
        logger.error(f"任务ID: {schedule_id}, 错误类型: {type(e).__name__}")
        # 更新执行统计（失败）
        if schedule_id:
            _update_task_stats(schedule_id, success=False)
        # 重新抛出异常以便 Django-Q 记录到 Failure 表
        raise


def execute_ui_test_suite(*args, **kwargs):
    """执行UI自动化测试套件"""
    from apps.scheduler.models import ScheduleConfig
    from apps.ui_automation.models import TestSuite
    
    # 获取 is_manual_execution 参数
    is_manual_execution = kwargs.get('is_manual_execution', False)
    executed_by_id = kwargs.get('executed_by_id', None)
    
    schedule_id = None
    try:
        # 优先使用 kwargs 中的 schedule_id（新数据）
        schedule_id = kwargs.get('schedule_id')
        
        # 兼容旧数据：如果 kwargs 中没有 schedule_id，尝试从 args 获取
        if not schedule_id and args:
            schedule_id = args[0]
        
        # 兼容处理：如果 schedule_id 是列表，取第一个元素
        if isinstance(schedule_id, list):
            schedule_id = schedule_id[0] if schedule_id else None
        
        if not schedule_id:
            logger.error("schedule_id 为空")
            return
        
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        test_suite = TestSuite.objects.get(id=config.target_id)
        
        task_config = config.task_config or {}
        
        logger.info(f"开始执行UI测试套件: {test_suite.name}")
        
        from apps.ui_automation.test_executor import TestExecutor
        executor = TestExecutor(
            test_suite=test_suite,
            engine=task_config.get('engine', 'playwright'),
            browser=task_config.get('browser', 'chrome'),
            headless=task_config.get('headless', True),
            executed_by=config.created_by
        )
        result = executor.run()
        
        logger.info(f"UI测试套件执行完成: {test_suite.name}")
        
        # 更新执行统计
        _update_task_stats(schedule_id, success=result.get('success', True))
        
        if config.notify_on_success or config.notify_on_failure:
            send_notification(config, result.get('success', True), result, is_manual_execution, executed_by_id)
        
        # 返回结果以便 Django-Q 记录到 Success 表
        return result
        
    except Exception as e:
        logger.error(f"执行UI测试套件失败: {e}", exc_info=True)
        logger.error(f"任务ID: {schedule_id}, 错误类型: {type(e).__name__}")
        # 更新执行统计（失败）
        if schedule_id:
            _update_task_stats(schedule_id, success=False)
        try:
            config = ScheduleConfig.objects.get(schedule__id=schedule_id)
            logger.error(f"任务配置: {config.schedule.name}, 模块: {config.get_module_display()}")
            if config.notify_on_failure:
                send_notification(config, False, {'error': str(e)})
        except Exception as notify_error:
            logger.error(f"发送失败通知时出错: {notify_error}", exc_info=True)
        # 重新抛出异常以便 Django-Q 记录到 Failure 表
        raise


def execute_ui_test_cases(*args, **kwargs):
    """执行UI自动化测试用例"""
    from apps.scheduler.models import ScheduleConfig
    from apps.ui_automation.models import TestCase as UiTestCase, TestSuite
    
    # 获取 is_manual_execution 参数
    is_manual_execution = kwargs.get('is_manual_execution', False)
    executed_by_id = kwargs.get('executed_by_id', None)
    
    schedule_id = None
    try:
        # 优先使用 kwargs 中的 schedule_id（新数据）
        schedule_id = kwargs.get('schedule_id')
        
        # 兼容旧数据：如果 kwargs 中没有 schedule_id，尝试从 args 获取
        if not schedule_id and args:
            schedule_id = args[0]
        
        # 兼容处理：如果 schedule_id 是列表，取第一个元素
        if isinstance(schedule_id, list):
            schedule_id = schedule_id[0] if schedule_id else None
        
        if not schedule_id:
            logger.error("schedule_id 为空")
            return
        
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        task_config = config.task_config or {}
        test_case_ids = task_config.get('test_case_ids', [])
        
        test_cases = UiTestCase.objects.filter(id__in=test_case_ids)
        
        logger.info(f"开始执行UI测试用例: {len(test_case_ids)} 个")
        
        # 收集所有测试用例的执行结果
        all_results = []
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        overall_success = True
        
        for test_case in test_cases:
            temp_suite = TestSuite.objects.create(
                project=test_case.project,
                name=f"[定时任务] {test_case.name}"
            )
            temp_suite.test_cases.add(test_case)
            
            from apps.ui_automation.test_executor import TestExecutor
            executor = TestExecutor(
                test_suite=temp_suite,
                engine=task_config.get('engine', 'playwright'),
                browser=task_config.get('browser', 'chrome'),
                headless=task_config.get('headless', True),
                executed_by=config.created_by
            )
            result = executor.run()
            all_results.append(result)
            
            # 汇总统计
            if result.get('success'):
                total_passed += result.get('passed_cases', 0)
                total_failed += result.get('failed_cases', 0)
                total_skipped += result.get('skipped_cases', 0)
            else:
                overall_success = False
        
        logger.info(f"UI测试用例执行完成")
        
        # 构建汇总结果
        summary_result = {
            'success': overall_success,
            'total_cases': total_passed + total_failed + total_skipped,
            'passed_cases': total_passed,
            'failed_cases': total_failed,
            'skipped_cases': total_skipped,
            'test_results': all_results,
            'message': 'UI测试用例执行完成'
        }
        
        # 更新执行统计
        _update_task_stats(schedule_id, success=overall_success)
        
        if config.notify_on_success or config.notify_on_failure:
            send_notification(config, overall_success, summary_result, is_manual_execution, executed_by_id)
        
        # 返回结果以便 Django-Q 记录到 Success 表
        return summary_result
        
    except Exception as e:
        logger.error(f"执行UI测试用例失败: {e}", exc_info=True)
        logger.error(f"任务ID: {schedule_id}, 错误类型: {type(e).__name__}")
        # 更新执行统计（失败）
        if schedule_id:
            _update_task_stats(schedule_id, success=False)
        # 重新抛出异常以便 Django-Q 记录到 Failure 表
        raise


def execute_app_test_suite(*args, **kwargs):
    """执行APP自动化测试套件"""
    from apps.scheduler.models import ScheduleConfig
    from apps.app_automation.models import AppTestSuite
    
    # 获取 is_manual_execution 参数
    is_manual_execution = kwargs.get('is_manual_execution', False)
    executed_by_id = kwargs.get('executed_by_id', None)
    
    schedule_id = None
    try:
        # 优先使用 kwargs 中的 schedule_id（新数据）
        schedule_id = kwargs.get('schedule_id')
        
        # 兼容旧数据：如果 kwargs 中没有 schedule_id，尝试从 args 获取
        if not schedule_id and args:
            schedule_id = args[0]
        
        # 兼容处理：如果 schedule_id 是列表，取第一个元素
        if isinstance(schedule_id, list):
            schedule_id = schedule_id[0] if schedule_id else None
        
        if not schedule_id:
            logger.error("schedule_id 为空")
            return
        
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        test_suite = AppTestSuite.objects.get(id=config.target_id)
        
        task_config = config.task_config or {}
        
        logger.info(f"开始执行APP测试套件: {test_suite.name}")
        
        from apps.app_automation.executors.test_executor import AppTestExecutor
        executor = AppTestExecutor()
        result = executor.run_tests(
            test_case_id=test_suite.id,
            device_id=task_config.get('device_id'),
            package_name=task_config.get('app_package_name', ''),
            execution_id=None,
            username=config.created_by.username if config.created_by else None
        )
        
        logger.info(f"APP测试套件执行完成: {test_suite.name}")
        
        # 更新执行统计
        _update_task_stats(schedule_id, success=result.get('success', True))
        
        if config.notify_on_success or config.notify_on_failure:
            send_notification(config, result.get('success', True), result, is_manual_execution, executed_by_id)
        
        # 返回结果以便 Django-Q 记录到 Success 表
        return result
        
    except Exception as e:
        logger.error(f"执行APP测试套件失败: {e}", exc_info=True)
        logger.error(f"任务ID: {schedule_id}, 错误类型: {type(e).__name__}")
        # 更新执行统计（失败）
        if schedule_id:
            _update_task_stats(schedule_id, success=False)
        # 重新抛出异常以便 Django-Q 记录到 Failure 表
        raise


def execute_app_test_cases(*args, **kwargs):
    """执行APP自动化测试用例"""
    from apps.scheduler.models import ScheduleConfig
    from apps.app_automation.models import AppTestCase, AppTestSuite
    
    # 获取 is_manual_execution 参数
    is_manual_execution = kwargs.get('is_manual_execution', False)
    executed_by_id = kwargs.get('executed_by_id', None)
    
    schedule_id = None
    try:
        # 优先使用 kwargs 中的 schedule_id（新数据）
        schedule_id = kwargs.get('schedule_id')
        
        # 兼容旧数据：如果 kwargs 中没有 schedule_id，尝试从 args 获取
        if not schedule_id and args:
            schedule_id = args[0]
        
        # 兼容处理：如果 schedule_id 是列表，取第一个元素
        if isinstance(schedule_id, list):
            schedule_id = schedule_id[0] if schedule_id else None
        
        if not schedule_id:
            logger.error("schedule_id 为空")
            return
        
        config = ScheduleConfig.objects.get(schedule__id=schedule_id)
        task_config = config.task_config or {}
        test_case_ids = task_config.get('test_case_ids', [])
        
        test_cases = AppTestCase.objects.filter(id__in=test_case_ids)
        
        logger.info(f"开始执行APP测试用例: {len(test_case_ids)} 个")
        
        # 收集所有测试用例的执行结果
        all_results = []
        overall_success = True
        
        for test_case in test_cases:
            temp_suite = AppTestSuite.objects.create(
                project=test_case.project,
                name=f"[定时任务] {test_case.name}"
            )
            temp_suite.test_cases.add(test_case)
            
            from apps.app_automation.executors.test_executor import AppTestExecutor
            executor = AppTestExecutor()
            result = executor.run_tests(
                test_case_id=temp_suite.id,
                device_id=task_config.get('device_id'),
                package_name=task_config.get('app_package_name', ''),
                execution_id=None,
                username=config.created_by.username if config.created_by else None
            )
            all_results.append(result)
            
            if not result.get('success'):
                overall_success = False
        
        logger.info(f"APP测试用例执行完成")
        
        # 构建汇总结果
        summary_result = {
            'success': overall_success,
            'test_results': all_results,
            'message': 'APP测试用例执行完成'
        }
        
        # 更新执行统计
        _update_task_stats(schedule_id, success=overall_success)
        
        if config.notify_on_success or config.notify_on_failure:
            send_notification(config, overall_success, summary_result, is_manual_execution, executed_by_id)
        
        # 返回结果以便 Django-Q 记录到 Success 表
        return summary_result
        
    except Exception as e:
        logger.error(f"执行APP测试用例失败: {e}", exc_info=True)
        logger.error(f"任务ID: {schedule_id}, 错误类型: {type(e).__name__}")
        # 更新执行统计（失败）
        if schedule_id:
            _update_task_stats(schedule_id, success=False)
        # 重新抛出异常以便 Django-Q 记录到 Failure 表
        raise


def _render_notification_template(template_content, context):
    """
    渲染通知模板
    :param template_content: 模板内容（Markdown格式）
    :param context: 上下文变量字典
    :return: str: 渲染后的内容
    """
    logger.info(f"开始渲染模板，模板内容长度: {len(template_content)}, 上下文变量: {list(context.keys())}")
    # logger.info(f"模板内容前200字符: {template_content[:200]}")
    content = template_content
    for key, value in context.items():
        placeholder = f"{{{{{key}}}}}"
        old_content = content
        content = content.replace(placeholder, str(value) if value is not None else '')
        if old_content != content:
            logger.info(f"  替换变量: {key} = {value}")
    logger.info(f"模板渲染完成，结果长度: {len(content)}")
    # logger.info(f"渲染后内容前200字符: {content[:200]}")
    return content


def _build_notification_context(config, success, result, is_manual_execution=False, executed_by_id=None):
    """构建通知模板上下文变量
    :param config: ScheduleConfig 实例
    :param success: 是否成功
    :param result: 执行结果
    :param is_manual_execution: 是否立即执行（默认为False，表示定时任务触发）
    :param executed_by_id: 执行用户ID（可选，用于记录实际执行者）
    :return: 上下文变量字典
    """
    status_text = '成功' if success else '失败'
    now = timezone.now()
    local_now = timezone.localtime(now)
    
    # 根据是否立即执行设置测试人员
    if is_manual_execution:
        # 优先使用传入的执行用户ID
        if executed_by_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                executed_user = User.objects.get(id=executed_by_id)
                tester = executed_user.username
                if hasattr(executed_user, 'get_full_name') and executed_user.get_full_name():
                    tester = executed_user.get_full_name()
            except User.DoesNotExist:
                tester = config.created_by.username if config.created_by else '系统'
                if hasattr(config.created_by, 'get_full_name') and config.created_by.get_full_name():
                    tester = config.created_by.get_full_name()
        else:
            tester = config.created_by.username if config.created_by else '系统'
            if hasattr(config.created_by, 'get_full_name') and config.created_by.get_full_name():
                tester = config.created_by.get_full_name()
    else:
        tester = '定时任务触发'
    
    context = {
        'title': f'定时任务执行{status_text}',
        'task_name': config.schedule.name if config.schedule else 'Unknown',
        'task_type': config.get_task_type_display(),
        'module': config.get_module_display(),
        'status': status_text,
        'status_text': status_text,
        'status_class': 'success' if success else 'failed',
        'execution_time': local_now.strftime('%Y-%m-%d %H:%M:%S'),
        'success': '是' if success else '否',
        'start_time': local_now.strftime('%Y-%m-%d %H:%M:%S'),
        'end_time': local_now.strftime('%Y-%m-%d %H:%M:%S'),
        'tester': tester,
    }
    
    if result:
        logger.info(f"开始处理执行结果: result类型={type(result)}, result={result}")
        logger.info(f"result 的所有键: {result.keys() if isinstance(result, dict) else 'N/A'}")
        if isinstance(result, dict):
            total_cases = result.get('total_count', result.get('total_cases', 0))
            passed_cases = result.get('passed_count', result.get('passed_cases', 0))
            failed_cases = result.get('failed_count', result.get('failed_cases', 0))
            error_cases = result.get('error_count', result.get('error_cases', 0))
            skipped_cases = result.get('skipped_count', result.get('skipped_cases', 0))
            
            # 如果是单个API请求，没有测试统计数据，则根据success字段设置
            if total_cases == 0 and passed_cases == 0 and failed_cases == 0:
                if 'success' in result:
                    total_cases = 1
                    if result['success']:
                        passed_cases = 1
                    else:
                        failed_cases = 1
                    logger.info(f"单个API请求，根据success字段设置统计数据: total_cases={total_cases}, passed_cases={passed_cases}, failed_cases={failed_cases}")
            
            logger.info(f"提取测试统计数据: total_cases={total_cases}, passed_cases={passed_cases}, failed_cases={failed_cases}")
            
            context['total_cases'] = total_cases
            context['passed_cases'] = passed_cases
            context['failed_cases'] = failed_cases
            context['error_cases'] = error_cases
            context['skipped_cases'] = skipped_cases
            
            # 从 result 中获取 start_time 和 end_time
            if 'start_time' in result:
                context['start_time'] = result['start_time']
            if 'end_time' in result:
                context['end_time'] = result['end_time']
            
            if total_cases > 0:
                pass_rate = (passed_cases / total_cases) * 100
                context['pass_rate'] = f"{pass_rate:.2f}%"
                coverage_rate = ((passed_cases + failed_cases) / total_cases) * 100
                context['coverage_rate'] = f"{coverage_rate:.2f}%"
            else:
                context['pass_rate'] = "0.00%"
                context['coverage_rate'] = "0.00%"
            
            if 'duration' in result:
                duration_seconds = float(result['duration'])
                context['duration'] = f"{duration_seconds:.2f}秒"
            else:
                context['duration'] = "0.00秒"
    
    if config.project_id:
        try:
            from apps.projects.models import Project
            project = Project.objects.get(id=config.project_id)
            context['project_name'] = project.name
        except Exception:
            context['project_name'] = ''
    else:
        context['project_name'] = ''
    
    if config.environment_id:
        try:
            from apps.api_testing.models import Environment
            env = Environment.objects.get(id=config.environment_id)
            context['environment_name'] = env.name
        except Exception:
            context['environment_name'] = ''
    else:
        context['environment_name'] = ''
    
    if config.created_by:
        context['creator'] = config.created_by.username
        if hasattr(config.created_by, 'get_full_name') and config.created_by.get_full_name():
            context['creator'] = config.created_by.get_full_name()
    
    context['executor'] = '系统自动执行'
    
    context['config_name'] = config.schedule.name if config.schedule else 'Unknown'
    
    try:
        from django.conf import settings
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        
        # 根据测试类型生成对应的Allure报告URL
        if config.schedule:
            task_type = config.task_type
            execution_id = None
            
            # 从result中获取execution_id或history_id
            if result and isinstance(result, dict):
                execution_id = result.get('execution_id') or result.get('history_id')
            
            if execution_id:
                if task_type == 'api_test':
                    context['report_url'] = f"{frontend_url}/api-testing-reports/execution_{execution_id}/index.html"
                elif task_type == 'ui_test':
                    context['report_url'] = f"{frontend_url}/ui-testing-reports/execution_{execution_id}/index.html"
                elif task_type == 'app_test':
                    context['report_url'] = f"{frontend_url}/app-testing-reports/execution_{execution_id}/index.html"
                else:
                    context['report_url'] = f"{frontend_url}/reports/schedule/{config.schedule.id}"
            else:
                context['report_url'] = f"{frontend_url}/reports/schedule/{config.schedule.id}"
    except Exception:
        pass
    
    return context


def send_notification(config, success, result, is_manual_execution=False, executed_by_id=None):
    """
    发送任务通知
    :param config: ScheduleConfig 实例
    :param success: 是否成功
    :param result: 执行结果
    :param is_manual_execution: 是否立即执行（默认为False，表示定时任务触发）
    :param executed_by_id: 执行用户ID（可选，用于记录实际执行者）
    :return:
    """
    if success and not config.notify_on_success:
        return
    if not success and not config.notify_on_failure:
        return
    
    status_text = '成功' if success else '失败'
    context = _build_notification_context(config, success, result, is_manual_execution, executed_by_id)
    
    logger.info(f"=== 开始发送任务通知 ===")
    logger.info(f"send_notification: is_manual_execution={is_manual_execution}, executed_by_id={executed_by_id}")
    logger.info(f"任务名称: {config.schedule.name if config.schedule else 'Unknown'}")
    logger.info(f"通知设置 - 成功通知: {config.notify_on_success}, 失败通知: {config.notify_on_failure}")
    logger.info(f"通知类型 - 邮件通知: {config.notify_on_email}, Webhook通知: {config.notify_on_webhook}")
    logger.info(f"通知配置数量: {config.notification_configs.count()}")
    logger.info(f"通知配置列表: {list(config.notification_configs.values_list('id', 'name'))}")
    
    # 从通知配置中获取邮件收件人
    email_recipients = []
    email_notification_configs = config.notification_configs.filter(config_type='email')
    
    logger.info(f"找到 {email_notification_configs.count()} 个邮件通知配置")
    
    for email_config in email_notification_configs:
        logger.info(f"处理邮件配置: {email_config.name}")
        logger.info(f"  email_recipients 原始数据: {email_config.email_recipients}")
        logger.info(f"  email_recipients 数据类型: {type(email_config.email_recipients)}")
        
        # 使用模型的 get_email_recipients() 方法来获取收件人列表
        config_recipients = email_config.get_email_recipients()
        logger.info(f"  从配置获取的收件人: {config_recipients}")
        
        for recipient in config_recipients:
            logger.info(f"  添加收件人: {recipient}")
            if recipient and recipient not in email_recipients:
                email_recipients.append(recipient)
            elif recipient and recipient in email_recipients:
                logger.info(f"    邮箱已存在，跳过: {recipient}")
    
    logger.info(f"从通知配置获取的邮件收件人: {email_recipients}")
    
    # 根据通知类型决定发送哪种通知
    should_send_email = config.notify_on_email and email_recipients and len(email_recipients) > 0
    should_send_webhook = config.notify_on_webhook and config.notification_configs.filter(config_type__startswith='webhook').exists()
    
    logger.info(f"发送邮件通知: {should_send_email}")
    logger.info(f"发送Webhook通知: {should_send_webhook}")
    
    # 发送Webhook通知
    if should_send_webhook:
        try:
            from apps.core.models import UnifiedNotificationConfig
            from services.notification_tasks import send_webhook_notification_task
            
            # 使用配置的通知配置
            configured_webhook_configs = config.notification_configs.filter(
                config_type__in=['webhook_wechat', 'webhook_feishu', 'webhook_dingtalk', 'webhook_generic'],
                is_active=True
            )
            logger.info(f"使用配置的通知配置 (notification_configs), 找到 {configured_webhook_configs.count()} 个webhook配置")
            logger.info(f"webhook配置列表: {list(configured_webhook_configs.values_list('id', 'name', 'config_type'))}")
            
            all_webhook_bots = []
            for webhook_config in configured_webhook_configs:
                bots = webhook_config.get_webhook_bots()
                logger.info(f"配置 {webhook_config.name} 的机器人列表: {bots}")
                if bots:
                    for bot in bots:
                        if bot.get('enabled', True):
                            module = config.module
                            if module == 'API' and bot.get('enable_api_testing', True):
                                all_webhook_bots.append(bot)
                                logger.info(f"添加机器人: {bot.get('name')} (API测试已启用)")
                            elif module == 'UI' and bot.get('enable_ui_automation', True):
                                all_webhook_bots.append(bot)
                                logger.info(f"添加机器人: {bot.get('name')} (UI自动化测试已启用)")
                            elif module == 'APP' and bot.get('enable_app_automation', True):
                                all_webhook_bots.append(bot)
                                logger.info(f"添加机器人: {bot.get('name')} (APP自动化测试已启用)")
                            else:
                                logger.info(f"配置中心机器人 {bot.get('name')} 未启用{module}测试，跳过")
            
            if not all_webhook_bots:
                logger.warning("没有找到任何启用的webhook机器人配置")
            else:
                logger.info(f"找到 {len(all_webhook_bots)} 个启用的webhook机器人配置")
                
                for bot in all_webhook_bots:
                    if not bot.get('enabled', True) or not bot.get('webhook_url'):
                        continue
                    
                    webhook_url = bot['webhook_url'].strip().strip('`').strip()
                    bot_type = bot.get('type', '')
                    template_id = bot.get('notification_template_id')
                    
                    template_content = None
                    if template_id:
                        try:
                            from apps.core.models import NotificationTemplate
                            template = NotificationTemplate.objects.get(id=template_id)
                            template_content = template.content
                            logger.info(f"使用自定义模板: {template.name}")
                        except NotificationTemplate.DoesNotExist:
                            logger.warning(f"模板不存在: {template_id}")
                    
                    if template_content:
                        rendered_content = _render_notification_template(template_content, context)
                    else:
                        rendered_content = f"""### 定时任务执行{status_text}
**任务名称**: {context['task_name']}
**执行状态**: {status_text}
**执行时间**: {context['execution_time']}
**任务类型**: {context['task_type']}"""

                    message_data = None
                    if bot_type == 'wechat':
                        message_data = _build_wechat_message(rendered_content)
                    elif bot_type == 'feishu':
                        message_data = _build_feishu_message(rendered_content, status_text, success)
                    elif bot_type == 'dingtalk':
                        message_data = _build_dingtalk_message(rendered_content, status_text)
                        
                        # 钉钉机器人签名验证
                        secret = bot.get('secret')
                        if secret:
                            import time
                            timestamp = str(round(time.time() * 1000))
                            sign = _generate_dingtalk_sign(secret, timestamp)
                            
                            if sign:
                                # 在URL中添加签名参数
                                if '?' in webhook_url:
                                    webhook_url += f'&timestamp={timestamp}&sign={sign}'
                                else:
                                    webhook_url += f'?timestamp={timestamp}&sign={sign}'
                                
                                logger.info(f"钉钉机器人签名验证 - 时间戳: {timestamp}")
                                logger.info(f"生成的签名: {sign}")
                                logger.info(f"最终URL: {webhook_url}")
                        else:
                            logger.info(f"钉钉机器人未配置签名密钥，使用无签名模式")
                    else:
                        message_data = {
                            "text": rendered_content
                        }
                    
                    try:
                        # 根据模块设置分组
                        group = config.get_module_display()
                        send_webhook_notification_task(
                            webhook_url=webhook_url,
                            message=message_data,
                            bot_type=f'webhook_{bot_type}',
                            group=group
                        )
                        logger.info(f"Webhook通知任务已加入队列: {bot_type} - {webhook_url}")
                    except Exception as e:
                        logger.error(f"发送webhook请求失败: {str(e)}")
                        logger.error(f"Webhook URL: {webhook_url}")
        except ImportError as e:
            logger.error(f"无法导入统一通知配置: {e}")
        except Exception as e:
            logger.error(f"发送Webhook通知失败: {e}")
    
    # 发送邮件通知
    if should_send_email:
        from services.email_tasks import send_task_notification_task
        from apps.core.models import NotificationTemplate
        from backend.utils.modern_email import TestReportEmailSender
        import tempfile
        import os
        
        status = 'success' if success else 'failed'
        task_name = config.schedule.name if config.schedule else 'Unknown'
        task_type = f"{config.get_module_display()}-{config.get_task_type_display()}"
        execution_time = str(timezone.now())
        
        # 检查是否需要附带报告附件
        email_attach_report = False
        for email_config in email_notification_configs:
            if email_config.email_attach_report:
                email_attach_report = True
                break
        
        logger.info(f"邮件附带报告: {email_attach_report}")
        
        # 获取邮件模板
        email_template = _get_email_template(email_notification_configs, config)
        
        # 渲染邮件主题和内容
        if email_template:
            logger.info(f"使用邮件模板: {email_template.name}, 类型: {email_template.template_type}")
            logger.info(f"模板主题: {email_template.subject}")
            logger.info(f"模板内容长度: {len(email_template.content)}")
            # logger.info(f"模板内容前100字符: {email_template.content[:100]}")
            
            # 渲染主题
            subject = email_template.subject or f"[TestHub] {task_type}任务执行{'成功' if success else '失败'}: {task_name}"
            subject = _render_notification_template(subject, context)
            
            # 渲染内容
            message = _render_notification_template(email_template.content, context)
            
            # 如果是HTML模板，使用渲染后的内容作为HTML
            # 如果是Markdown或Text模板，添加HTML样式，渲染为卡片效果
            if email_template.template_type == 'html':
                html_content = message
            else:
                # Markdown 和 Text 模板：添加HTML样式，渲染为卡片效果
                # 移除 ** 标记
                message = message.replace('**', '')
                # 保留 [链接文本](url) 格式，转换为"链接文本：url"格式
                message = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1：\2', message)
                
                # 添加HTML样式，渲染为卡片效果
                status_color = '#52c41a' if success else '#ff4d4f'
                status_text = '成功' if success else '失败'
                
                html_content = f"""
                <html>
                <head>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                        }}
                        .card {{
                            max-width: 600px;
                            margin: 0 auto;
                            border: 1px solid #e0e0e0;
                            border-radius: 8px;
                            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                            overflow: hidden;
                        }}
                        .header {{
                            background-color: {status_color};
                            color: white;
                            padding: 16px 20px;
                            font-size: 18px;
                            font-weight: bold;
                        }}
                        .content {{
                            padding: 20px;
                            background-color: #f9f9f9;
                        }}
                        .content p {{
                            margin: 8px 0;
                            color: #333;
                        }}
                        .footer {{
                            padding: 12px 20px;
                            background-color: #f0f0f0;
                            border-top: 1px solid #e0e0e0;
                            text-align: center;
                            color: #666;
                            font-size: 12px;
                        }}
                        .footer a {{
                            color: #1890ff;
                            text-decoration: none;
                        }}
                    </style>
                </head>
                <body>
                    <div class="card">
                        <div class="header">
                            定时任务执行{status_text}
                        </div>
                        <div class="content">
                            {message.replace('\n', '<p>').replace('\n\n', '<br><br>')}
                        </div>
                        <div class="footer">
                            TestHub 测试平台
                        </div>
                    </div>
                </body>
                </html>
                """
            
            logger.info(f"邮件模板信息: template_type={email_template.template_type}, has_html_content={html_content is not None}")
            if html_content:
                logger.info(f"HTML内容长度: {len(html_content)} 字符")
        else:
            # 使用默认内容
            status_text = '成功' if success else '失败'
            subject = f"[TestHub] {task_type}任务执行{status_text}: {task_name}"
            
            message = f"""任务名称: {task_name}
任务类型: {task_type}
执行状态: {status_text}
执行时间: {context.get('execution_time', execution_time)}

测试用例执行情况:
- 用例总数: {context.get('total_cases', 0)}
- 成功用例: {context.get('passed_cases', 0)}
- 失败用例: {context.get('failed_cases', 0)}
- 错误用例: {context.get('error_cases', 0)}
- 跳过用例: {context.get('skipped_cases', 0)}
- 通过率: {context.get('pass_rate', '0%')}

详细报告: {context.get('report_url', '#')}

此邮件由系统自动发送，请勿回复。"""
            
            html_content = None
        
        # 生成报告附件（在 subject 赋值之后）
        attachments = None
        if email_attach_report:
            try:
                from utils.html_report import html_report_generator
                
                # 构建测试用例列表
                test_cases = []
                
                # 从result中提取测试用例详情
                if isinstance(result, dict):
                    # 优先从result_data中提取
                    if 'result_data' in result and isinstance(result['result_data'], dict):
                        result_data = result['result_data']
                        if 'test_cases' in result_data:
                            for test_result in result_data['test_cases']:
                                test_cases.append({
                                    'name': test_result.get('name', '未知用例'),
                                    'status': test_result.get('status', 'unknown'),
                                    'duration': test_result.get('duration', 0),
                                    'error_message': test_result.get('error_message', '')
                                })
                    
                    # 其次从test_results中提取
                    elif 'test_results' in result:
                        for test_result in result['test_results']:
                            test_cases.append({
                                'name': test_result.get('name', '未知用例'),
                                'status': test_result.get('status', 'unknown'),
                                'duration': test_result.get('duration', 0),
                                'error_message': test_result.get('error_message', '')
                            })
                    
                    # 再次从results中提取（API测试套件）
                    elif 'results' in result:
                        for test_result in result['results']:
                            test_cases.append({
                                'name': test_result.get('name', '未知用例'),
                                'status': 'passed' if test_result.get('passed') else 'failed',
                                'duration': test_result.get('response_time', 0) / 1000 if test_result.get('response_time') else 0,
                                'error_message': test_result.get('error', '')
                            })
                
                # 如果没有测试用例详情，创建一个汇总用例
                if not test_cases:
                    if context.get('failed_cases', 0) > 0:
                        test_cases.append({
                            'name': '测试执行',
                            'status': 'failed',
                            'duration': 0,
                            'error_message': '存在失败的测试用例'
                        })
                    else:
                        test_cases.append({
                            'name': '测试执行',
                            'status': 'passed',
                            'duration': 0,
                            'error_message': ''
                        })
                
                # 构建环境信息
                environment = {
                    '项目': context.get('project_name', 'N/A'),
                    '测试人员': context.get('tester', 'N/A'),
                    '执行时间': context.get('execution_time', 'N/A'),
                    '执行时长': context.get('duration', 'N/A')
                }
                
                # 生成HTML报告
                summary = {
                    'total': context.get('total_cases', 0),
                    'passed': context.get('passed_cases', 0),
                    'failed': context.get('failed_cases', 0),
                    'skipped': context.get('skipped_cases', 0),
                    'error': context.get('error_cases', 0),
                    'duration': result.get('duration', 0) if isinstance(result, dict) else 0
                }
                
                html_report = html_report_generator.generate_report(
                    title=subject,
                    test_type=task_type,
                    summary=summary,
                    test_cases=test_cases,
                    environment=environment,
                    report_url=context.get('report_url', None),
                    execution_time=context.get('execution_time', None)
                )
                
                attachments = [{'filename': f'{subject}.html', 'content': html_report}]
                logger.info(f"已生成报告附件: {subject}.html")
            except Exception as e:
                logger.error(f"生成报告附件失败: {e}")
        
        try:
            send_task_notification_task(
                subject=subject,
                message=message,
                recipients=email_recipients,
                html_content=html_content,
                attachments=attachments
            )
            logger.info(f"邮件通知任务已加入队列: {email_recipients}")
        except Exception as e:
            logger.error(f"发送邮件通知失败: {e}")
