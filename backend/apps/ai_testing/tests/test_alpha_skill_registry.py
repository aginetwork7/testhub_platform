from unittest import TestCase

from apps.ai_testing.alpha.contracts import SkillTier
from apps.ai_testing.alpha.skills.registry import (
    ArgumentField,
    SkillDefinition,
    SkillRegistry,
    SkillRegistryError,
)
from apps.ai_testing.alpha.skills.catalog import build_phase_one_registry


def _echo_handler(_: object, arguments: dict[str, object]) -> dict[str, object]:
    return dict(arguments)


class AlphaSkillRegistryTests(TestCase):
    def setUp(self) -> None:
        self.registry = SkillRegistry()
        self.registry.register(
            SkillDefinition(
                name='projects.list',
                version='1',
                tier=SkillTier.READ,
                risky=False,
                arguments=(ArgumentField(name='limit', value_type=int),),
                handler=_echo_handler,
            )
        )

    def test_unknown_skill_cannot_dispatch(self) -> None:
        with self.assertRaisesRegex(SkillRegistryError, 'Unregistered Skill'):
            self.registry.dispatch('shell.execute', object(), {})

    def test_free_form_arguments_are_rejected(self) -> None:
        with self.assertRaisesRegex(SkillRegistryError, 'Unexpected Skill arguments'):
            self.registry.normalize_arguments('projects.list', {'limit': 10, 'command': 'whoami'})

    def test_required_argument_type_is_validated(self) -> None:
        with self.assertRaisesRegex(SkillRegistryError, 'Invalid type'):
            self.registry.normalize_arguments('projects.list', {'limit': '10'})

    def test_low_risk_read_skill_does_not_require_confirmation(self) -> None:
        definition = self.registry.get('projects.list')

        self.assertFalse(definition.requires_confirmation)

    def test_risky_run_and_write_skills_require_confirmation(self) -> None:
        run_skill = SkillDefinition(
            name='runs.start',
            version='1',
            tier=SkillTier.RUN,
            risky=True,
            arguments=(),
            handler=_echo_handler,
        )
        write_skill = SkillDefinition(
            name='cases.create',
            version='1',
            tier=SkillTier.WRITE,
            risky=False,
            arguments=(),
            handler=_echo_handler,
        )

        self.assertTrue(run_skill.requires_confirmation)
        self.assertTrue(write_skill.requires_confirmation)

    def test_phase_one_catalogue_exposes_only_the_approved_read_skill(self) -> None:
        registry = build_phase_one_registry()

        self.assertEqual([definition.name for definition in registry.definitions()], ['ai_projects.list'])
        self.assertFalse(registry.get('ai_projects.list').requires_confirmation)