from datetime import datetime
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.requirement_analysis.models import (
    normalize_prd_directory_name,
    requirement_docs_upload_path,
    sync_testcase_generation_task_artifacts,
    write_prd_text_artifact,
)


class RequirementDocumentPathTests(SimpleTestCase):
    def test_requirement_docs_upload_path_uses_yyyymmdd_and_document_title_directory(self) -> None:
        expected_prefix = datetime.now().strftime('%Y%m%d')
        instance = type('DocumentStub', (), {'title': '用户登录 PRD'})()

        path = requirement_docs_upload_path(instance=instance, filename='demo.pdf')

        self.assertEqual(path, f'{expected_prefix}/用户登录 PRD/demo.pdf')

    def test_requirement_docs_upload_path_sanitizes_directory_name(self) -> None:
        expected_prefix = datetime.now().strftime('%Y%m%d')
        instance = type('DocumentStub', (), {'title': '用户登录/PRD:V1'})()

        path = requirement_docs_upload_path(instance=instance, filename='demo.pdf')

        self.assertEqual(path, f'{expected_prefix}/用户登录_PRD_V1/demo.pdf')

    def test_normalize_prd_directory_name_falls_back_to_untitled(self) -> None:
        self.assertEqual(normalize_prd_directory_name('  ///  '), 'untitled')

    def test_write_prd_text_artifact_stores_content_in_document_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('apps.requirement_analysis.models.requirement_docs_storage.location', temp_dir):
                created_at = datetime(2026, 5, 29, 12, 0, 0)

                target_path = write_prd_text_artifact('用户登录 PRD', created_at, 'analysis_report.md', 'report body')

                self.assertEqual(
                    target_path,
                    Path(temp_dir) / '20260529' / '用户登录 PRD' / 'analysis_report.md',
                )
                self.assertEqual(target_path.read_text(encoding='utf-8'), 'report body')

    def test_sync_testcase_generation_task_artifacts_writes_generation_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('apps.requirement_analysis.models.requirement_docs_storage.location', temp_dir):
                task = type('TaskStub', (), {
                    'title': '用户登录 PRD',
                    'created_at': datetime(2026, 5, 29, 12, 0, 0),
                    'requirement_text': '需求描述',
                    'generated_test_cases': '生成内容',
                    'review_feedback': '评审意见',
                    'final_test_cases': '最终用例',
                    'generation_log': '日志内容',
                    'error_message': '',
                })()

                sync_testcase_generation_task_artifacts(task)

                base_dir = Path(temp_dir) / '20260529' / '用户登录 PRD'
                self.assertEqual((base_dir / 'requirement_text.txt').read_text(encoding='utf-8'), '需求描述')
                self.assertEqual((base_dir / 'generated_test_cases.md').read_text(encoding='utf-8'), '生成内容')
                self.assertEqual((base_dir / 'review_feedback.md').read_text(encoding='utf-8'), '评审意见')
                self.assertEqual((base_dir / 'final_test_cases.md').read_text(encoding='utf-8'), '最终用例')
                self.assertEqual((base_dir / 'generation_log.txt').read_text(encoding='utf-8'), '日志内容')