"""Curated phase-one Alpha Skill catalogue."""

from collections.abc import Mapping

from apps.ai_testing.alpha.contracts import SkillTier
from apps.ai_testing.alpha.skills.registry import SkillDefinition, SkillRegistry


def build_phase_one_registry() -> SkillRegistry:
    """Create the intentionally small, no-mutation phase-one Skill catalogue."""
    registry = SkillRegistry()
    registry.register(
        SkillDefinition(
            name='ai_projects.list',
            version='1',
            tier=SkillTier.READ,
            risky=False,
            arguments=(),
            handler=list_accessible_ai_projects,
        )
    )
    return registry


def list_accessible_ai_projects(user: object, _: Mapping[str, object]) -> Mapping[str, object]:
    """Return a minimal, permission-filtered project summary without sensitive metadata."""
    from apps.ai_testing.alpha.access import accessible_ai_project_queryset

    projects = accessible_ai_project_queryset(user).order_by('id').values('id', 'name', 'description')[:100]
    return {'projects': list(projects)}