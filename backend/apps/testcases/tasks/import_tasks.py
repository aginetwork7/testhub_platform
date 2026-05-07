import os
import traceback
from django.utils import timezone
from django.db import transaction
import openpyxl

from apps.testcases.models import TestCase, TestCaseImportRecord

def process_test_case_import(record_id):
    try:
        record = TestCaseImportRecord.objects.get(id=record_id)
    except TestCaseImportRecord.DoesNotExist:
        return
        
    record.status = 'running'
    record.started_at = timezone.now()
    record.save(update_fields=['status', 'started_at'])
    
    file_path = record.file.path if record.file else None
    if not file_path or not os.path.exists(file_path):
        record.status = 'failed'
        record.logs = '导入文件不存在'
        record.finished_at = timezone.now()
        record.save()
        return

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        
        # Check headers
        headers = [str(cell.value).strip() if cell.value else '' for cell in sheet[1]]
        
        expected_headers = {
            '用例标题': 'title',
            '前置条件': 'preconditions',
            '操作步骤': 'steps',
            '预期结果': 'expected_result',
            '优先级': 'priority',
            '测试类型': 'test_type',
            '关联版本': 'related_versions'
        }
        
        col_map = {}
        for idx, h in enumerate(headers):
            if h in expected_headers:
                col_map[expected_headers[h]] = idx

        if 'title' not in col_map or 'expected_result' not in col_map:
            raise ValueError("模板错误：缺少必填列 '用例标题' 或 '预期结果'")

        total_rows = sheet.max_row - 1
        record.total_rows = total_rows
        record.save(update_fields=['total_rows'])

        success_count = 0
        failed_count = 0
        duplicate_count = 0
        error_summary = []

        priority_map = {'低': 'low', '中': 'medium', '高': 'high', '紧急': 'critical'}
        type_map = {
            '功能测试': 'functional', '集成测试': 'integration', 'API测试': 'api',
            'UI测试': 'ui', '性能测试': 'performance', '安全测试': 'security'
        }

        # Process rows
        for row_idx in range(2, sheet.max_row + 1):
            row_data = sheet[row_idx]
            
            # Extract data
            def get_val(key, default=''):
                if key in col_map:
                    val = row_data[col_map[key]].value
                    return str(val).strip() if val is not None else default
                return default

            title = get_val('title')
            if not title:
                failed_count += 1
                error_summary.append({'row': row_idx, 'error': '用例标题为空'})
                continue
                
            expected_result = get_val('expected_result')
            if not expected_result:
                failed_count += 1
                error_summary.append({'row': row_idx, 'error': '预期结果为空'})
                continue

            priority_text = get_val('priority', '中')
            type_text = get_val('test_type', '功能测试')

            priority = priority_map.get(priority_text, 'medium')
            # 状态字段已被移除，默认设置为 'draft' (草稿)
            status = 'draft'
            test_type = type_map.get(type_text, 'functional')
            
            # 处理关联版本字段 (逗号分隔的字符串转为列表)
            # 由于 versions 是 ManyToManyField，需要在 TestCase 创建后通过 set() 方法关联
            related_versions_text = get_val('related_versions')
            version_names = [v.strip() for v in related_versions_text.split(',')] if related_versions_text else []

            # Check duplicate (Optional: skip if exists in same project)
            if TestCase.objects.filter(project_id=record.project_id, title=title).exists():
                duplicate_count += 1
                error_summary.append({'row': row_idx, 'error': '用例标题在当前项目中已存在'})
                continue

            try:
                from apps.versions.models import Version
                test_case = TestCase.objects.create(
                    project_id=record.project_id,
                    title=title,
                    preconditions=get_val('preconditions'),
                    steps=get_val('steps'),
                    expected_result=get_val('expected_result'),
                    priority=priority,
                    status=status,
                    test_type=test_type,
                    author=record.created_by
                )
                
                # 关联版本
                if version_names:
                    versions_to_add = []
                    for v_name in version_names:
                        if not v_name:
                            continue
                        # 查找当前项目下的同名版本，如果不存在则自动创建
                        version, created = Version.objects.get_or_create(
                            name=v_name,
                            defaults={
                                'description': f'导入测试用例自动创建的版本',
                                'created_by': record.created_by
                            }
                        )
                        # 将版本与当前项目关联
                        version.projects.add(record.project_id)
                        versions_to_add.append(version)
                        
                    if versions_to_add:
                        test_case.versions.set(versions_to_add)
                
                success_count += 1
            except Exception as e:
                failed_count += 1
                error_summary.append({'row': row_idx, 'error': f'保存失败: {str(e)}'})

            # Update progress every 10 rows
            if (row_idx - 1) % 10 == 0:
                record.progress = int((row_idx - 1) / total_rows * 100)
                record.save(update_fields=['progress'])

        record.progress = 100
        record.success_count = success_count
        record.failed_count = failed_count
        record.duplicate_count = duplicate_count
        record.error_summary = error_summary
        
        if failed_count == 0 and success_count > 0:
            record.status = 'success'
            record.logs = '导入成功'
        elif success_count > 0 and failed_count > 0:
            record.status = 'partial'
            record.logs = '部分导入成功，请查看错误明细'
        else:
            record.status = 'failed'
            record.logs = '全部导入失败'
            
    except Exception as e:
        record.status = 'failed'
        record.logs = f"执行异常: {str(e)}\n{traceback.format_exc()}"
        
    finally:
        record.finished_at = timezone.now()
        record.save()
