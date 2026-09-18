"""计划契约被拒时附带的合规示例，以及提交类步骤的验证策略校验。"""

import json
import pathlib

from django.test import SimpleTestCase

from apps.ai_testing.execution.plan_contract_examples import (
    all_rule_markers,
    example_steps_for,
    retry_guidance,
)
from apps.ai_testing.global_planner import GlobalPlanError, GlobalTestPlanner


def _normalize(steps, configuration_id=1, goal='goal'):
    response = {'choices': [{'message': {'tool_calls': [{'function': {
        'name': 'submit_execution_plan',
        'arguments': json.dumps({'steps': steps}, ensure_ascii=True),
    }}]}}]}
    return GlobalTestPlanner().normalize_response(
        response, configuration_id, goal, require_transition=True,
    )


class ContractExampleValidityTests(SimpleTestCase):
    """示例是给模型照抄的，自身必须通过契约校验，否则会把模型带偏。"""

    def test_every_example_passes_the_contract_it_illustrates(self) -> None:
        for marker in all_rule_markers():
            with self.subTest(marker=marker):
                steps = example_steps_for(marker)
                self.assertTrue(steps, f'{marker} 没有示例')
                normalized = _normalize(steps)
                self.assertEqual(len(normalized), len(steps))

    def test_guidance_is_returned_only_for_known_rejections(self) -> None:
        guidance = retry_guidance('Planner 浏览器步骤 2 选择下拉选项后未验证所选值；请使用 field_value 验证。')
        self.assertIn('最小合规示例', guidance)
        self.assertIn('"assert_kind": "field_value"', guidance)
        self.assertIn('"kind": "select_option"', guidance)

    def test_examples_do_not_leak_acceptance_case_answers(self) -> None:
        # 示例是教模型「形状」的，不能顺带把验收用例的正确取值递过去。
        import apps.ai_testing.execution.plan_contract_examples as module

        source = pathlib.Path(module.__file__).read_text(encoding='utf-8')
        for leaked in ('Magic Search V2', 'Investigate', 'ai@test.com', '萧山区', '5003_D13'):
            self.assertNotIn(leaked, source, f'契约示例里出现了验收用例的业务取值：{leaked}')

        self.assertEqual(retry_guidance('某个未收录的新错误'), '')
        self.assertEqual(retry_guidance(''), '')
        self.assertEqual(retry_guidance(None), '')

    def test_guidance_covers_the_rejections_seen_in_cold_start_runs(self) -> None:
        # 冷启动实测中真实出现过的两条拒绝，必须都能给出示例。
        tc002 = 'Planner 浏览器步骤 2 选择下拉选项后未验证所选值；请使用 field_value 或 element_state 文本断言验证描述中的目标选项。'
        tc007 = (
            'Planner browser step 7 commits a transaction but only asserts that a layer disappeared. '
            'Assert the committed result itself with a field_value or element_state text assertion.'
        )
        for message in (tc002, tc007):
            with self.subTest(message=message[:40]):
                self.assertIn('最小合规示例', retry_guidance(message))

    def test_retry_message_attaches_the_example(self) -> None:
        import inspect

        source = inspect.getsource(GlobalTestPlanner.create_plan)
        self.assertIn('guidance = retry_guidance(error)', source)
        self.assertIn('+ guidance', source)


class CommitStepAssertionTests(SimpleTestCase):
    """提交类步骤只断言弹层消失时应被拒绝。"""

    @staticmethod
    def _step(description, assertions):
        return [{
            'executor': 'browser',
            'allowed_capabilities': ['browser.act', 'browser.inspect'],
            'description': description,
            'transition': {'kind': 'generic'},
            'assertions': assertions,
        }]

    VALUE_ASSERTION = {
        'action': 'assert',
        'assert_kind': 'field_value', 'operator': 'starts_with',
        'expected': {'value': 'Investigate'},
        'target': {'intent': 'status control showing the committed value'},
        'required': True,
    }
    DIALOG_GONE = {
        'action': 'assert',
        'assert_kind': 'popup', 'operator': 'not_exists', 'expected': {'value': True},
        'target': {'intent': 'reason dialog that was confirmed'}, 'required': True,
    }

    def test_confirm_step_asserting_only_a_vanished_dialog_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlobalPlanError, 'only asserts that a layer disappeared'):
            _normalize(self._step('Click Confirm in the dialog to commit the Investigate action.', [self.DIALOG_GONE]))

    def test_confirm_step_is_accepted_once_it_asserts_the_committed_value(self) -> None:
        steps = self._step(
            'Click Confirm in the dialog to commit the Investigate action.',
            [self.VALUE_ASSERTION, {**self.DIALOG_GONE, 'required': False}],
        )
        self.assertEqual(len(_normalize(steps)), 1)

    def test_closing_a_layer_is_not_a_commit_step(self) -> None:
        # TC_005 的关闭直播流步骤：描述里没有提交动词，只断言播放器消失是正当的。
        steps = self._step(
            'Click the video stream close control at the bottom center of the page to close the live stream.',
            [{
                'action': 'assert',
                'assert_kind': 'element_state', 'operator': 'not_exists', 'expected': {'value': True},
                'target': {'intent': 'live video stream player for the opened camera'}, 'required': True,
            }],
        )
        self.assertEqual(len(_normalize(steps)), 1)

    def test_confirming_a_deletion_may_prove_it_by_content_absence(self) -> None:
        # 确认删除后记录从列表消失，是内容层面的证据而非弹层消失，应当放行。
        steps = self._step(
            'Confirm the deletion in the dialog.',
            [{
                'action': 'assert',
                'assert_kind': 'text', 'operator': 'not_contains', 'expected': {'value': 'ai@test.com'},
                'target': {'intent': 'user list after the deletion'}, 'required': True,
            }],
        )
        self.assertEqual(len(_normalize(steps)), 1)

    def test_download_confirmation_keeps_its_task_assertion(self) -> None:
        # TC_006 第 7 步：描述含 confirm，但断言是 download_task，不受该规则影响。
        steps = self._step(
            'Confirm the download in the dialog and wait for the download task to complete.',
            [{
                'action': 'assert',
                'assert_kind': 'download_task', 'operator': 'equals', 'expected': {'status': 'completed'},
                'target': {'intent': 'download task for the opened camera'}, 'required': True,
            }],
        )
        self.assertEqual(len(_normalize(steps)), 1)

    def test_planner_prompt_states_the_commit_rule(self) -> None:
        import inspect

        source = inspect.getsource(GlobalTestPlanner._build_messages)
        self.assertIn('confirms, submits or saves a pending change', source)
        self.assertIn('asserting only that the confirmation dialog disappeared is not accepted', source)


class DropdownDisplayValueTests(SimpleTestCase):
    """下拉控件常把所选项显示为缩写，用例目标里声明的显示文本应被接受。"""

    GOAL = (
        "1. 登录Customer账号\n2. 点击Magic下拉框\n"
        "3. 点击下拉框列表中的'Magic Search V2'选项，断言Magic下拉框标签显示为'Magic V2'"
    )

    @staticmethod
    def _step(expected_value):
        return [{
            'executor': 'browser',
            'allowed_capabilities': ['browser.act', 'browser.inspect'],
            'description': "Select the 'Magic Search V2' option from the Magic dropdown.",
            'transition': {'kind': 'select_option', 'value': 'Magic Search V2'},
            'assertions': [{
                'action': 'assert',
                'assert_kind': 'field_value', 'operator': 'starts_with',
                'expected': {'value': expected_value},
                'target': {'intent': 'Magic dropdown showing the committed selected value'},
                'required': True,
            }],
        }]

    def test_abbreviated_label_declared_in_the_goal_is_accepted(self) -> None:
        # 步骤描述里没有 "Magic V2"，只有用例目标里有；此前这会被拒绝。
        self.assertEqual(len(_normalize(self._step('Magic V2'), goal=self.GOAL)), 1)

    def test_full_option_name_is_still_accepted(self) -> None:
        self.assertEqual(len(_normalize(self._step('Magic Search V2'), goal=self.GOAL)), 1)

    def test_a_value_declared_nowhere_is_still_rejected(self) -> None:
        with self.assertRaisesRegex(GlobalPlanError, '选择下拉选项后未验证所选值'):
            _normalize(self._step('Something Else'), goal=self.GOAL)
