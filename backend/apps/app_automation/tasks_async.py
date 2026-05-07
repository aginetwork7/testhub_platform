# -*- coding: utf-8 -*-
"""
APP自动化测试异步任务（使用 Django-Q2 替换 Celery）

注意：定时任务通知功能已迁移到 apps.scheduler.task_executor 模块统一处理
"""
from django_q.tasks import async_task, result
from django.utils import timezone
import logging
import os
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def send_execution_update(execution_id, status=None, progress=None, message=None, report_path=None, finished_at=None, result=None):
    """通过 WebSocket 发送执行状态更新"""
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        payload = {
            "type": "execution_update",
            "execution_id": int(execution_id),
            "status": status,
            "result": result,
            "progress": progress,
            "message": message,
            "report_path": report_path,
            "finished_at": finished_at.isoformat() if finished_at else None,
        }
        async_to_sync(channel_layer.group_send)(
            f"app_execution_{execution_id}",
            payload
        )
    except Exception as e:
        logger.debug(f"发送执行状态更新失败: {e}")


def execute_app_test_task(execution_id, package_name: str = None, scheduled_task_id: int = None):
    """
    异步执行APP测试任务（Django-Q2）
    
    Args:
        execution_id: AppTestExecution 的 ID
        package_name: 可选的应用包名
        scheduled_task_id: 可选的定时任务 ID（来自定时调度）
    """
    from django.conf import settings
    from .models import AppTestExecution, AppDevice
    from .executors.test_executor import AppTestExecutor
    
    execution = None
    device = None
    
    try:
        execution = AppTestExecution.objects.get(id=execution_id)
        test_case = execution.test_case
        
        device = execution.device
        
        execution.status = 'running'
        execution.started_at = timezone.now()
        execution.progress = 0
        execution.save()
        send_execution_update(execution_id, status='running', progress=0, message='任务开始执行')
        
        logger.info(f"开始执行APP测试: {test_case.name}")
        
        if device.status == 'locked' and device.locked_by != execution.user:
            raise RuntimeError(f"设备 {device.device_id} 已被其他用户锁定")
        
        if device.status != 'locked':
            device.lock(execution.user)
        
        logger.info(f"设备已锁定: {device.device_id}")
        
        execution.progress = 10
        execution.save()
        send_execution_update(execution_id, status='running', progress=10, message='正在准备测试环境')
        
        if package_name:
            final_package_name = package_name
        else:
            final_package_name = test_case.app_package.package_name if test_case.app_package else ""

        executor = AppTestExecutor()
        report_result = executor.run_tests(
            test_case_id=test_case.id,
            device_id=device.device_id,
            package_name=final_package_name,
            execution_id=execution_id,
            username=execution.user.username if execution.user else 'unknown',
        )
        
        execution.refresh_from_db()
        
        if report_result.get('report_path'):
            execution.report_path = report_result['report_path']
            logger.info(f"报告已生成: {report_result['report_path']}")
        
        test_results = report_result.get('test_results', {})
        execution.total_steps = test_results.get('total', 0)
        execution.passed_steps = test_results.get('passed', 0)
        execution.failed_steps = test_results.get('failed', 0)
        
        execution.progress = 95
        execution.save()
        send_execution_update(
            execution_id,
            status='running',
            progress=95,
            message='正在生成测试报告',
            report_path=execution.report_path
        )
        
        execution.status = 'completed'
        if execution.total_steps == 0:
            execution.result = 'skipped'
        elif execution.failed_steps == 0:
            execution.result = 'passed'
        else:
            execution.result = 'failed'
        execution.finished_at = timezone.now()
        execution.duration = (execution.finished_at - execution.started_at).total_seconds()
        execution.progress = 100
        execution.save()
        send_execution_update(
            execution_id,
            status=execution.status,
            progress=100,
            message='执行完成',
            report_path=execution.report_path,
            finished_at=execution.finished_at,
            result=execution.result,
        )
        
        logger.info(f"APP测试执行完成: {test_case.name}, 状态: {execution.status}, 结果: {execution.result}")

    except AppTestExecution.DoesNotExist:
        logger.error(f"执行记录不存在: {execution_id}")
    except Exception as e:
        logger.error(f"执行APP测试失败: {str(e)}", exc_info=True)
        
        if execution:
            execution.status = 'error'
            execution.result = None
            execution.error_message = str(e)
            execution.finished_at = timezone.now()
            if execution.started_at:
                execution.duration = (execution.finished_at - execution.started_at).total_seconds()
            execution.save()
            send_execution_update(
                execution_id,
                status='error',
                progress=execution.progress or 0,
                message=str(e),
                report_path=execution.report_path,
                finished_at=execution.finished_at,
                result=None,
            )
            
            try:
                executor = AppTestExecutor()
                executor._generate_allure_report(execution_id=execution_id)
            except Exception:
                pass
    finally:
        try:
            if device and device.locked_by == execution.user:
                device.unlock()
                logger.info(f"设备已释放: {device.device_id}")
        except Exception as e:
            logger.error(f"释放设备失败: {str(e)}")


def execute_app_suite_task(suite_id, execution_ids, package_name=None, scheduled_task_id=None):
    """
    异步执行APP测试套件（顺序执行多个用例）- Django-Q2

    Args:
        suite_id: AppTestSuite 的 ID
        execution_ids: AppTestExecution ID 列表（按执行顺序）
        package_name: 可选的应用包名覆盖
        scheduled_task_id: 可选的定时任务 ID
    """
    from .models import AppTestSuite, AppTestExecution, AppDevice
    from .executors.test_executor import AppTestExecutor

    suite = None
    device = None
    passed = 0
    failed = 0

    try:
        suite = AppTestSuite.objects.get(id=suite_id)
        executions = list(
            AppTestExecution.objects.filter(id__in=execution_ids)
            .select_related('test_case', 'test_case__app_package', 'device', 'user')
            .order_by('id')
        )
        exec_map = {e.id: e for e in executions}
        executions = [exec_map[eid] for eid in execution_ids if eid in exec_map]

        if not executions:
            logger.error(f"套件 {suite_id} 未找到执行记录")
            return

        device = executions[0].device
        user = executions[0].user

        if device.status != 'locked':
            device.lock(user)
        logger.info(f"套件执行开始: {suite.name}, 设备: {device.device_id}, 共 {len(executions)} 个用例")

        for idx, execution in enumerate(executions):
            test_case = execution.test_case
            if not test_case:
                execution.status = 'error'
                execution.result = None
                execution.error_message = '用例不存在'
                execution.finished_at = timezone.now()
                execution.save()
                failed += 1
                continue

            try:
                execution.status = 'running'
                execution.started_at = timezone.now()
                execution.progress = 0
                execution.save()
                send_execution_update(
                    execution.id, status='running', progress=0,
                    message=f'开始执行 ({idx + 1}/{len(executions)})'
                )

                if package_name:
                    final_pkg = package_name
                else:
                    final_pkg = test_case.app_package.package_name if test_case.app_package else ""

                execution.progress = 10
                execution.save()
                send_execution_update(
                    execution.id, status='running', progress=10,
                    message='正在准备测试环境'
                )

                executor = AppTestExecutor()
                report_result = executor.run_tests(
                    test_case_id=test_case.id,
                    device_id=device.device_id,
                    package_name=final_pkg,
                    execution_id=execution.id,
                    username=execution.user.username if execution.user else 'unknown',
                )

                execution.refresh_from_db()

                if report_result.get('report_path'):
                    execution.report_path = report_result['report_path']

                test_results = report_result.get('test_results', {})
                execution.total_steps = test_results.get('total', 0)
                execution.passed_steps = test_results.get('passed', 0)
                execution.failed_steps = test_results.get('failed', 0)

                execution.status = 'completed'
                if execution.total_steps == 0:
                    execution.result = 'skipped'
                elif execution.failed_steps == 0:
                    execution.result = 'passed'
                else:
                    execution.result = 'failed'
                execution.finished_at = timezone.now()
                execution.duration = (execution.finished_at - execution.started_at).total_seconds()
                execution.progress = 100
                execution.save()

                if execution.result == 'passed':
                    passed += 1
                else:
                    failed += 1

                send_execution_update(
                    execution.id, status=execution.status, progress=100,
                    message='执行完成',
                    report_path=execution.report_path,
                    finished_at=execution.finished_at,
                    result=execution.result,
                )

                logger.info(f"用例 {test_case.name} 执行完成: status={execution.status}, result={execution.result}")

            except Exception as e:
                logger.error(f"用例 {test_case.name} 执行失败: {str(e)}", exc_info=True)
                execution.status = 'error'
                execution.result = None
                execution.error_message = str(e)
                execution.finished_at = timezone.now()
                if execution.started_at:
                    execution.duration = (execution.finished_at - execution.started_at).total_seconds()
                execution.save()
                failed += 1
                send_execution_update(
                    execution.id, status='error',
                    progress=execution.progress or 0,
                    message=str(e),
                    finished_at=execution.finished_at,
                    result=None,
                )

        suite.execution_status = 'completed'
        if passed == 0 and failed == 0:
            suite.execution_result = 'skipped'
        elif failed == 0:
            suite.execution_result = 'passed'
        else:
            suite.execution_result = 'failed'
        suite.save(update_fields=['execution_status', 'execution_result'])
        logger.info(f"套件执行完成: {suite.name}, 通过: {passed}, 失败: {failed}")

    except Exception as e:
        logger.error(f"执行APP测试套件失败: {str(e)}", exc_info=True)
        if suite:
            suite.execution_status = 'error'
            suite.execution_result = 'failed'
            suite.save(update_fields=['execution_status', 'execution_result'])
    finally:
        try:
            if device and device.status == 'locked' and device.locked_by == user:
                device.unlock()
                logger.info(f"设备已释放: {device.device_id}")
        except Exception as e:
            logger.error(f"释放设备失败: {str(e)}")
