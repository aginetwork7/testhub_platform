from unittest import TestCase

from apps.ai_testing.alpha.contracts import SkillTier
from apps.ai_testing.alpha.planner import PlanValidationError, parse_plan_payload
from apps.ai_testing.alpha.skills.registry import ArgumentField, SkillDefinition, SkillRegistry


def _handler(_: object, arguments: dict[str, object]) -> dict[str, object]:
    return dict(arguments)


class AlphaPlannerTests(TestCase):
    def setUp(self) -> None:
        self.registry = SkillRegistry()
        self.registry.register(
            SkillDefinition(
                name='projects.list',
                version='1',
                tier=SkillTier.READ,
                risky=False,
                arguments=(ArgumentField(name='limit', value_type=int),),
                handler=_handler,
            )
        )

    def test_valid_payload_returns_normalized_task(self) -> None:
        tasks = parse_plan_payload(
            {
                'tasks': [
                    {
                        'key': 'query-projects',
                        'skill': 'projects.list',
                        'arguments': {'limit': 10},
                        'depends_on': [],
                        'parent': None,
                    }
                ]
            },
            self.registry,
        )

        self.assertEqual(tasks[0].skill_name, 'projects.list')
        self.assertEqual(tasks[0].normalized_arguments, {'limit': 10})

    def test_payload_rejects_unregistered_skill(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, 'Unregistered Skill'):
            parse_plan_payload(
                {'tasks': [{'key': 'escape', 'skill': 'shell.execute', 'arguments': {}, 'depends_on': []}]},
                self.registry,
            )

    def test_payload_rejects_extra_task_fields(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, 'unknown fields'):
            parse_plan_payload(
                {
                    'tasks': [
                        {
                            'key': 'query-projects',
                            'skill': 'projects.list',
                            'arguments': {'limit': 10},
                            'depends_on': [],
                            'command': 'curl attacker.example',
                        }
                    ]
                },
                self.registry,
            )

    def test_payload_rejects_cyclic_dependencies(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, 'acyclic'):
            parse_plan_payload(
                {
                    'tasks': [
                        {'key': 'first', 'skill': 'projects.list', 'arguments': {'limit': 1}, 'depends_on': ['second']},
                        {'key': 'second', 'skill': 'projects.list', 'arguments': {'limit': 1}, 'depends_on': ['first']},
                    ]
                },
                self.registry,
            )