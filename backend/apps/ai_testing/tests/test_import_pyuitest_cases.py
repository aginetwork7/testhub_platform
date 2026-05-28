from django.test import SimpleTestCase

from apps.ai_testing.management.commands.import_pyuitest_cases import Command


class ImportPyuitestCasesCommandTests(SimpleTestCase):
    def setUp(self) -> None:
        self.command = Command()

    def test_convert_plain_text_step_to_ai_step(self) -> None:
        steps = self.command._convert_step('点击登录按钮')

        self.assertEqual(
            steps,
            [
                {
                    'step_mode': 'ai',
                    'description': '点击登录按钮',
                    'timeout_ms': 10000,
                }
            ],
        )

    def test_convert_supported_playwright_actions_to_direct_steps(self) -> None:
        steps = self.command._convert_step(
            'playwright:[{"action":"key","param":"Enter"},{"action":"wait","param":"5"}]'
        )

        self.assertEqual(steps[0]['step_mode'], 'direct')
        self.assertEqual(steps[0]['action'], 'press')
        self.assertEqual(steps[0]['selector'], 'body')
        self.assertEqual(steps[0]['value'], 'Enter')
        self.assertEqual(steps[1]['step_mode'], 'direct')
        self.assertEqual(steps[1]['action'], 'wait')
        self.assertEqual(steps[1]['timeout_ms'], 5000)

    def test_convert_unsupported_playwright_action_to_ai_fallback(self) -> None:
        steps = self.command._convert_step(
            'playwright:[{"action":"unknown_action","param":"Saved successfully"}]'
        )

        self.assertEqual(steps[0]['step_mode'], 'ai')
        self.assertIn('Saved successfully', steps[0]['description'])

    def test_convert_assert_popup_to_direct_runtime_step(self) -> None:
        steps = self.command._convert_step(
            'playwright:[{"action":"assert_popup","param":"Saved successfully"}]'
        )

        self.assertEqual(steps[0]['step_mode'], 'direct')
        self.assertEqual(steps[0]['action'], 'assert_popup_contains')
        self.assertEqual(steps[0]['expected'], 'Saved successfully')

    def test_convert_media_assertions_to_direct_runtime_steps(self) -> None:
        video_steps = self.command._convert_step(
            'playwright:[{"action":"assert_video","param":"video_demo.mp4","visible":"True"}]'
        )
        media_steps = self.command._convert_step(
            'playwright:[{"action":"assert_media","visible":"True"}]'
        )

        self.assertEqual(video_steps[0]['step_mode'], 'direct')
        self.assertEqual(video_steps[0]['action'], 'assert_video_visible')
        self.assertEqual(video_steps[0]['expected'], 'video_demo.mp4')

        self.assertEqual(media_steps[0]['step_mode'], 'direct')
        self.assertEqual(media_steps[0]['action'], 'assert_media_visible')

    def test_build_task_steps_adds_step_numbers(self) -> None:
        task_steps = self.command._build_task_steps(
            [
                '点击登录按钮',
                'playwright:[{"action":"assert_url","param":"/dashboard"}]',
            ]
        )

        self.assertEqual([step['step_no'] for step in task_steps], [1, 2])
        self.assertEqual(task_steps[0]['step_mode'], 'ai')
        self.assertEqual(task_steps[1]['action'], 'assert_url_contains')

    def test_normalize_cases_prefixes_source_id_in_name(self) -> None:
        normalized_cases = self.command._normalize_cases(
            [
                {
                    'id': 'TC_001',
                    'name': 'dealer dark mode',
                    'module': 'UI自动化测试',
                    'steps': ['点击登录按钮'],
                }
            ],
            set(),
        )

        self.assertEqual(normalized_cases[0]['name'], '[TC_001] dealer dark mode')