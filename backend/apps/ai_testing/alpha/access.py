"""Shared permission-scoped query helpers for Alpha Skills."""

from django.db import models

from apps.ai_testing.models import AiProject


def accessible_ai_project_queryset(user: object):
    """Return only AI projects visible to the authenticated initiating user."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return AiProject.objects.none()
    return AiProject.objects.filter(
        models.Q(unified_meta_project__owner=user)
        | models.Q(unified_meta_project__members__user=user)
        | models.Q(unified_meta_project__isnull=True, created_by=user)
    ).distinct()