"""冷跑必须可验证是冷的：开关没生效时不能跑出一份看起来通过的报告。"""

import json

from django.test import SimpleTestCase

from apps.ai_testing.management.commands.run_ai_acceptance import Command


class PlanSourceExtractionTests(SimpleTestCase):
    extract = staticmethod(Command._plan_source)

    def test_a_dict_trace_reports_its_source(self) -> None:
        self.assertEqual(self.extract({'planner_trace': {'plan_source': 'verified'}}), 'verified')

    def test_a_json_string_trace_is_parsed(self) -> None:
        self.assertEqual(self.extract({'planner_trace': json.dumps({'plan_source': 'model'})}), 'model')

    def test_unreadable_traces_report_unknown(self) -> None:
        for trace in (None, '', 'not json', 123, {'planner_trace': None}):
            with self.subTest(trace=trace):
                self.assertEqual(self.extract({'planner_trace': trace}), 'unknown')
        self.assertEqual(self.extract(None), 'unknown')


class ColdRunAssertionTests(SimpleTestCase):
    """与 --no-cache --force-replan 同用，任何一次复用都应判失败。"""

    @staticmethod
    def _warm(results):
        # 复刻命令里的判据。
        return [item for item in results if item.get('plan_source') not in {'model', None, ''}]

    def test_a_fully_fresh_run_passes_the_check(self) -> None:
        self.assertEqual(self._warm([{'plan_source': 'model'}, {'plan_source': 'model'}]), [])

    def test_a_reused_verified_plan_is_caught(self) -> None:
        self.assertEqual(len(self._warm([{'plan_source': 'model'}, {'plan_source': 'verified'}])), 1)

    def test_a_reused_revision_or_persisted_plan_is_caught(self) -> None:
        self.assertEqual(len(self._warm([{'plan_source': 'cache'}, {'plan_source': 'persisted'}])), 2)

    def test_an_unprovable_source_is_treated_as_warm(self) -> None:
        # 证不出是冷的，就不能当作冷的。
        self.assertEqual(len(self._warm([{'plan_source': 'unknown'}])), 1)

    def test_the_command_wires_the_flag_and_fails_loudly(self) -> None:
        import inspect

        source = inspect.getsource(Command.handle)
        self.assertIn("options['assert_cold']", source)
        self.assertIn('声明了冷跑', source)
        self.assertIn("'plan_sources': Counter", source)
        self.assertIn('raise CommandError', source)
