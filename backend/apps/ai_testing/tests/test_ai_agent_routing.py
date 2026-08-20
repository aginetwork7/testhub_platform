import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.ai_testing.models import AIExecutionRecord, AiProject
from apps.api_automation.models import ApiAutomationConfiguration, ApiAutomationProject
from apps.ai_testing.ai_testing import BrowserAgent, HermesAgent, PyUICompatAgent, get_agent_class
from apps.unified_projects.models import MetaProject
from apps.users.models import User
from apps.ai_testing.views import (
    AIExecutionRecordViewSet,
    build_step_thinking,
    normalize_planner_artifact_path,
    normalize_step_thinking,
    resolve_api_automation_configuration_from_task,
)


class AIAgentRoutingTests(SimpleTestCase):
    def test_text_mode_hybrid_steps_use_pyui_compat_agent(self) -> None:
        agent_class = get_agent_class(
            execution_mode='text',
            case_mode='hybrid',
            task_steps=[{'step_mode': 'ai', 'description': '示例步骤'}],
        )

        self.assertIs(agent_class, PyUICompatAgent)

    def test_text_mode_freeform_keeps_browser_agent(self) -> None:
        agent_class = get_agent_class(
            execution_mode='text',
            case_mode='freeform',
            task_steps=[],
        )

        self.assertIs(agent_class, BrowserAgent)

    def test_hermes_mode_keeps_hermes_agent(self) -> None:
        agent_class = get_agent_class(
            execution_mode='hermes',
            case_mode='hybrid',
            task_steps=[{'step_mode': 'ai', 'description': '示例步骤'}],
        )

        self.assertIs(agent_class, HermesAgent)

    def test_normalize_step_thinking_filters_empty_planner_placeholder(self) -> None:
        self.assertIsNone(normalize_step_thinking('planner_v2 executed action='))
        self.assertIsNone(normalize_step_thinking(' planner_v2 executed action=   '))
        self.assertEqual(normalize_step_thinking('planner_v2 executed action=click'), 'action=click')
        self.assertEqual(normalize_step_thinking('planned_by=executor'), 'planned_by=executor')

    def test_build_step_thinking_falls_back_to_source_and_action(self) -> None:
        self.assertEqual(
            build_step_thinking({
                'thinking': 'planner_v2 executed action=',
                'source': 'model',
                'action': '点击保存按钮',
                'report_action': 'click',
            }),
            'source=model; action=click',
        )
        self.assertEqual(
            build_step_thinking({'thinking': None, 'source': 'cache', 'action': ''}),
            'source=cache',
        )

    def test_normalize_planner_artifact_path_rewrites_legacy_paths(self) -> None:
        self.assertEqual(
            normalize_planner_artifact_path(
                'ai_testing/planner_v2/TC_004__create_site_manager_role_20260528134604/'
                'TC_004__create_site_manager_role_step_01_completed.png'
            ),
            'ai_testing/planner_v2/TC_004_20260528134604/TC_004_step_01.png',
        )
        self.assertEqual(
            normalize_planner_artifact_path(
                'ai_testing/planner_v2/TC_004__create_site_manager_role_20260528134604/'
                'TC_004__create_site_manager_role_report.jsonl'
            ),
            'ai_testing/planner_v2/TC_004_20260528134604/TC_004_report.jsonl',
        )

    def test_report_step_records_prefers_case_report_action_and_path(self) -> None:
        record = type('Record', (), {
            'steps_completed': [{
                'step': 0,
                'action': '点击页面上方的蓝色加号, 创建新的角色',
                'thinking': 'planner_v2 executed action=',
                'status': 'completed',
            }],
            'planner_trace': {
                'case_report': {
                    'steps': [{
                        'action': 'click',
                        'source': 'model',
                        'step_screenshot': (
                            'ai_testing/planner_v2/TC_004__create_site_manager_role_20260528134604/'
                            'TC_004__create_site_manager_role_step_01_completed.png'
                        ),
                    }]
                }
            },
        })()

        viewset = AIExecutionRecordViewSet()
        steps = viewset._report_step_records(record)

        self.assertEqual(steps[0]['report_action'], 'click')
        self.assertEqual(build_step_thinking(steps[0]), 'source=model; action=click')
        self.assertEqual(
            steps[0]['step_screenshot'],
            'ai_testing/planner_v2/TC_004_20260528134604/TC_004_step_01.png',
        )

    def test_report_step_records_prefers_case_report_description_for_display(self) -> None:
        record = type('Record', (), {
            'steps_completed': [{
                'step': 0,
                'action': 'click',
                'thinking': 'planner_v2 executed action=click',
                'status': 'completed',
            }],
            'planned_tasks': [],
            'status': 'passed',
            'duration': 0,
            'execution_mode': 'text',
            'logs': '',
            'gif_path': None,
            'artifacts': [],
            'cache_stats': {},
            'planner_trace': {
                'case_report': {
                    'steps': [{
                        'step_description': '点击搜索框中的放大镜图标，展开高级搜索面板',
                        'action': 'click',
                        'source': 'model',
                    }]
                }
            },
        })()

        viewset = AIExecutionRecordViewSet()
        report = viewset._build_execution_report(record)

        self.assertEqual(
            report['detailed_steps'][0]['action'],
            '点击搜索框中的放大镜图标，展开高级搜索面板',
        )

    def test_execution_report_includes_device_step_output(self) -> None:
        record = type('Record', (), {
            'steps_completed': [{
                'step': 0,
                'action': 'device_cli',
                'status': 'completed',
                'output': '2360 root /custom/agi7/manager',
            }],
            'planned_tasks': [{'id': 1, 'description': '检查 manager 进程', 'status': 'completed'}],
            'status': 'passed',
            'duration': 1,
            'execution_mode': 'planner_v2',
            'logs': '',
            'gif_path': None,
            'artifacts': [],
            'cache_stats': {},
            'planner_trace': {'case_report': {'steps': []}},
        })()

        report = AIExecutionRecordViewSet()._build_execution_report(record)

        self.assertEqual(report['detailed_steps'][0]['output'], '2360 root /custom/agi7/manager')


class AIExecutionRecordViewSetQuerysetTests(TestCase):
    def test_resolve_environment_uses_longest_natural_language_alias(self) -> None:
        user = User.objects.create_user(username='planner_owner', password='pass123')
        api_project = ApiAutomationProject.objects.create(name='Planner API', owner=user)
        test_configuration = ApiAutomationConfiguration.objects.create(
            project=api_project,
            name='test 环境',
            environment='test',
        )
        test_two_configuration = ApiAutomationConfiguration.objects.create(
            project=api_project,
            name='test-2 环境',
            environment='test-2',
        )

        resolved = resolve_api_automation_configuration_from_task(
            '在 test-2 环境连接设备 nvr_5003 并检查 manager 进程',
            user,
        )

        self.assertEqual(resolved.id, test_two_configuration.id)
        self.assertNotEqual(resolved.id, test_configuration.id)

    def test_resolve_environment_uses_default_when_task_has_no_environment(self) -> None:
        user = User.objects.create_user(username='default_env_owner', password='pass123')
        api_project = ApiAutomationProject.objects.create(name='Default API', owner=user)
        default_configuration = ApiAutomationConfiguration.objects.create(
            project=api_project,
            name='test-2 环境',
            environment='test-2',
            is_default=True,
        )

        resolved = resolve_api_automation_configuration_from_task(
            '连接 nvr_5003 并确认 manager 进程存在',
            user,
        )

        self.assertEqual(resolved.id, default_configuration.id)

    def test_get_queryset_only_returns_accessible_project_records(self) -> None:
        owner = User.objects.create_user(username='owner', password='pass123')
        other_user = User.objects.create_user(username='other', password='pass123')

        meta_project = MetaProject.objects.create(name='Owner Meta', owner=owner)
        owner_project = AiProject.objects.create(
            name='Owner Project',
            created_by=owner,
            unified_meta_project=meta_project,
        )
        foreign_unlinked_project = AiProject.objects.create(
            name='Foreign Unlinked Project',
            created_by=other_user,
        )

        visible_record = AIExecutionRecord.objects.create(
            project=owner_project,
            case_name='Visible',
            task_description='visible',
            execution_mode='text',
            status='passed',
            executed_by=owner,
        )
        AIExecutionRecord.objects.create(
            project=foreign_unlinked_project,
            case_name='Hidden',
            task_description='hidden',
            execution_mode='text',
            status='passed',
            executed_by=other_user,
        )

        factory = APIRequestFactory()
        request = factory.get('/api/ai-testing/ai-execution-records/')
        request.user = owner

        viewset = AIExecutionRecordViewSet()
        viewset.request = request

        self.assertEqual(list(viewset.get_queryset().values_list('id', flat=True)), [visible_record.id])

    def test_get_queryset_supports_unarchived_scope(self) -> None:
        owner = User.objects.create_user(username='owner_scope', password='pass123')
        other_user = User.objects.create_user(username='other_scope', password='pass123')

        meta_project = MetaProject.objects.create(name='Owner Scope Meta', owner=owner)
        owner_project = AiProject.objects.create(
            name='Owner Scoped Project',
            created_by=owner,
            unified_meta_project=meta_project,
        )

        unarchived_record = AIExecutionRecord.objects.create(
            project=None,
            case_name='Unarchived Visible',
            task_description='visible',
            execution_mode='text',
            status='passed',
            executed_by=owner,
        )
        AIExecutionRecord.objects.create(
            project=owner_project,
            case_name='Project Visible',
            task_description='visible project',
            execution_mode='text',
            status='passed',
            executed_by=owner,
        )
        AIExecutionRecord.objects.create(
            project=None,
            case_name='Unarchived Hidden',
            task_description='hidden',
            execution_mode='text',
            status='passed',
            executed_by=other_user,
        )

        factory = APIRequestFactory()
        request = factory.get('/api/ai-testing/ai-execution-records/', {'project_scope': 'unarchived'})
        request.user = owner

        viewset = AIExecutionRecordViewSet()
        viewset.request = request

        self.assertEqual(list(viewset.get_queryset().values_list('id', flat=True)), [unarchived_record.id])

    def test_delete_execution_record_artifacts_removes_related_media_files(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            root = Path(media_root)
            gif_path = root / 'ai_recording' / 'demo.gif'
            screenshot_path = root / 'ai_testing' / 'planner_v2' / 'case1' / 'step_01.png'
            report_path = root / 'ai_testing' / 'planner_v2' / 'case1' / 'report.html'
            outside_path = root.parent / 'outside.txt'

            gif_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            gif_path.write_text('gif', encoding='utf-8')
            screenshot_path.write_text('png', encoding='utf-8')
            report_path.write_text('html', encoding='utf-8')
            outside_path.write_text('outside', encoding='utf-8')

            record = type('Record', (), {
                'gif_path': 'ai_recording/demo.gif',
                'screenshots_sequence': ['ai_testing/planner_v2/case1/step_01.png'],
                'artifacts': [
                    {'path': 'ai_testing/planner_v2/case1/report.html'},
                    {'path': str(outside_path)},
                ],
            })()

            viewset = AIExecutionRecordViewSet()

            with override_settings(MEDIA_ROOT=media_root):
                viewset._delete_execution_record_artifacts(record)

            self.assertFalse(gif_path.exists())
            self.assertFalse(screenshot_path.exists())
            self.assertFalse(report_path.exists())
            self.assertTrue(outside_path.exists())