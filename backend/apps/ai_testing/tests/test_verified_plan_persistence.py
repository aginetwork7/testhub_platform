"""已验证执行计划：与执行记录解耦，清空报告不影响它。"""

from django.test import TestCase

from apps.ai_testing.execution.verified_plan_persistence import (
    MAX_PLANS_PER_CONTEXT,
    export_verified_plans,
    import_verified_plans,
    load_verified_plan_steps,
    record_verified_plan,
)
from apps.ai_testing.models import AIVerifiedPlan

GOAL = '1. 登录 Customer 账号\n2. 点击 Cameras 按钮'


def _plan(first_step='Click the Cameras icon.', fingerprint='fp-1'):
    return {
        'steps': [
            {'step_key': 'step-1', 'source': {'executor': 'browser', 'description': first_step}},
            {'step_key': 'step-2', 'source': {'executor': 'browser', 'description': 'Search the site.'}},
        ],
        'context_fingerprint': fingerprint,
    }


class RecordAndLoadTests(TestCase):
    def test_a_passing_plan_can_be_loaded_back(self) -> None:
        record_verified_plan(GOAL, _plan(), 1, execution_record_id=42, ai_case_id=7, case_name='TC_005')
        steps = load_verified_plan_steps(GOAL, 1, 'fp-1')
        self.assertEqual([step['description'] for step in steps], ['Click the Cameras icon.', 'Search the site.'])

    def test_passing_twice_accumulates_evidence_rather_than_duplicating(self) -> None:
        for record_id in (1, 2, 3):
            record_verified_plan(GOAL, _plan(), 1, execution_record_id=record_id)
        rows = AIVerifiedPlan.objects.filter(goal_hash__isnull=False)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().verified_count, 3)
        self.assertEqual(rows.first().last_passed_record_id, 3)

    def test_the_better_proven_plan_wins(self) -> None:
        for _ in range(3):
            record_verified_plan(GOAL, _plan('Open cameras the proven way.'), 1)
        record_verified_plan(GOAL, _plan('Open cameras some other way.'), 1)
        steps = load_verified_plan_steps(GOAL, 1, 'fp-1')
        self.assertEqual(steps[0]['description'], 'Open cameras the proven way.')

    def test_another_environment_does_not_share_the_plan(self) -> None:
        record_verified_plan(GOAL, _plan(), 1)
        self.assertEqual(load_verified_plan_steps(GOAL, 2, 'fp-1'), [])

    def test_another_goal_does_not_share_the_plan(self) -> None:
        record_verified_plan(GOAL, _plan(), 1)
        self.assertEqual(load_verified_plan_steps('一个完全不同的目标', 1, 'fp-1'), [])

    def test_an_empty_plan_is_not_stored(self) -> None:
        self.assertIsNone(record_verified_plan(GOAL, {'steps': []}, 1))
        self.assertIsNone(record_verified_plan(GOAL, {}, 1))
        self.assertEqual(AIVerifiedPlan.objects.count(), 0)

    def test_stored_plans_per_context_are_capped(self) -> None:
        for index in range(MAX_PLANS_PER_CONTEXT + 3):
            record_verified_plan(GOAL, _plan(f'Variant {index}.'), 1)
        self.assertEqual(AIVerifiedPlan.objects.count(), MAX_PLANS_PER_CONTEXT)


class PlanningContextTests(TestCase):
    """规划上下文变了要重新规划，但对普通目标，旧指纹的已证明计划仍然可用。"""

    def test_a_matching_fingerprint_is_used(self) -> None:
        record_verified_plan(GOAL, _plan(fingerprint='fp-1'), 1)
        self.assertTrue(load_verified_plan_steps(GOAL, 1, 'fp-1'))

    def test_an_ordinary_goal_accepts_an_older_fingerprint(self) -> None:
        record_verified_plan(GOAL, _plan(fingerprint='fp-old'), 1)
        self.assertTrue(load_verified_plan_steps(GOAL, 1, 'fp-new', allow_legacy=True))

    def test_a_device_goal_replans_when_the_context_moved(self) -> None:
        record_verified_plan(GOAL, _plan(fingerprint='fp-old'), 1)
        self.assertEqual(load_verified_plan_steps(GOAL, 1, 'fp-new', allow_legacy=False), [])


class DecouplingFromRecordsTests(TestCase):
    def test_the_table_has_no_foreign_key_to_execution_records(self) -> None:
        # 整张计划表此前挂在执行记录下，清空报告会连带删掉。这里只存 id，删记录不影响。
        relations = [field.name for field in AIVerifiedPlan._meta.get_fields() if field.is_relation]
        self.assertEqual(relations, [])

    def test_the_planner_reads_this_table_before_plan_revisions(self) -> None:
        import inspect

        from apps.ai_testing.global_planner import GlobalTestPlanner

        source = inspect.getsource(GlobalTestPlanner.create_plan)
        self.assertLess(source.index('load_verified_plan_steps'), source.index('_load_cached_plan_steps'))
        self.assertIn("plan_source = 'verified' if cached_steps else 'cache'", source)

    def test_a_passing_run_records_its_plan(self) -> None:
        import inspect

        from apps.ai_testing.execution import dispatch

        source = inspect.getsource(dispatch)
        self.assertIn('_remember_verified_plan(execution_record, payload)', source)
        self.assertIn('record_verified_plan', source)


class ExportImportTests(TestCase):
    def test_plans_survive_a_round_trip(self) -> None:
        record_verified_plan(GOAL, _plan(), 1, ai_case_id=7, case_name='TC_005')
        payload = export_verified_plans()
        AIVerifiedPlan.objects.all().delete()
        self.assertEqual(import_verified_plans(payload), 1)
        self.assertTrue(load_verified_plan_steps(GOAL, 1, 'fp-1'))

    def test_import_can_retarget_another_environment(self) -> None:
        record_verified_plan(GOAL, _plan(), 1, ai_case_id=7, case_name='TC_005')
        payload = export_verified_plans()
        import_verified_plans(payload, environment_configuration_id=9)
        self.assertTrue(load_verified_plan_steps(GOAL, 9, 'fp-1'))
        self.assertTrue(load_verified_plan_steps(GOAL, 1, 'fp-1'))

    def test_malformed_entries_are_skipped(self) -> None:
        self.assertEqual(import_verified_plans([{'plan': 'not a dict'}, 'nonsense', None]), 0)


class BackfillTests(TestCase):
    """部署到已跑热的环境时，既有已通过记录里的计划不能白白丢掉。"""

    def _passed_record(self, case_name='TC_005', goal=GOAL, plan=None, status='passed'):
        from apps.ai_testing.execution.verified_plan_persistence import plan_hash
        from apps.ai_testing.models import AIExecutionPlanRevision, AIExecutionRecord

        record = AIExecutionRecord.objects.create(
            case_name=case_name, task_description=goal, status=status,
            environment_configuration_id=None, execution_mode='planner_v2',
        )
        payload = plan if plan is not None else _plan()
        AIExecutionPlanRevision.objects.create(
            execution_record=record, revision_number=1, source_goal=goal,
            plan=payload, plan_hash=plan_hash(payload), reason='initial',
        )
        return record

    def test_a_passed_record_is_backfilled(self) -> None:
        from apps.ai_testing.execution.verified_plan_persistence import backfill_from_execution_records

        self._passed_record()
        self.assertEqual(backfill_from_execution_records(), 1)
        self.assertTrue(load_verified_plan_steps(GOAL, None, 'fp-1'))

    def test_a_failed_record_is_not_backfilled(self) -> None:
        from apps.ai_testing.execution.verified_plan_persistence import backfill_from_execution_records

        self._passed_record(status='inconclusive')
        self.assertEqual(backfill_from_execution_records(), 0)

    def test_backfilling_twice_accumulates_rather_than_duplicates(self) -> None:
        from apps.ai_testing.execution.verified_plan_persistence import backfill_from_execution_records

        self._passed_record()
        backfill_from_execution_records()
        backfill_from_execution_records()
        self.assertEqual(AIVerifiedPlan.objects.count(), 1)
        self.assertEqual(AIVerifiedPlan.objects.first().verified_count, 2)
