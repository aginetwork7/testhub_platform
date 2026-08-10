from unittest import TestCase

from apps.ai_testing.alpha.contracts import (
    MAX_WORKFLOW_ROUNDS,
    AlphaDomainError,
    PlanTask,
    WorkflowStatus,
    assert_revision_mutable,
    record_completed_planning_cycle,
    validate_plan_tasks,
    validate_transition,
)


class AlphaContractsTests(TestCase):
    def test_valid_transition_allows_planning_to_execution(self) -> None:
        validate_transition(WorkflowStatus.PLANNING, WorkflowStatus.EXECUTING)

    def test_terminal_status_rejects_transition(self) -> None:
        with self.assertRaisesRegex(AlphaDomainError, "Invalid workflow transition"):
            validate_transition(WorkflowStatus.COMPLETED, WorkflowStatus.PLANNING)

    def test_plan_rejects_cyclic_dependencies(self) -> None:
        tasks = (
            PlanTask(task_key="collect", dependency_keys=("report",)),
            PlanTask(task_key="report", dependency_keys=("collect",)),
        )

        with self.assertRaisesRegex(AlphaDomainError, "acyclic"):
            validate_plan_tasks(tasks)

    def test_plan_rejects_unknown_dependencies(self) -> None:
        with self.assertRaisesRegex(AlphaDomainError, "unknown dependencies"):
            validate_plan_tasks((PlanTask(task_key="collect", dependency_keys=("missing",)),))

    def test_frozen_revision_rejects_mutation(self) -> None:
        with self.assertRaisesRegex(AlphaDomainError, "not mutable"):
            assert_revision_mutable(WorkflowStatus.EXECUTING, is_frozen=True)

    def test_planning_revision_remains_mutable_before_execution(self) -> None:
        assert_revision_mutable(WorkflowStatus.PLANNING, is_frozen=False)

    def test_round_cap_rejects_thirty_first_cycle(self) -> None:
        self.assertEqual(record_completed_planning_cycle(MAX_WORKFLOW_ROUNDS - 1), MAX_WORKFLOW_ROUNDS)

        with self.assertRaisesRegex(AlphaDomainError, "cannot exceed"):
            record_completed_planning_cycle(MAX_WORKFLOW_ROUNDS)