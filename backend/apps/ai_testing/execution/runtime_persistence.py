"""Persistence adapter that binds runtime facts to immutable execution plans."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.ai_testing.models import (
    AIExecutionEvidenceArtifact,
    AIExecutionPlanRevision,
    AIExecutionStepAttempt,
)


def persist_step_attempt(
    execution_record_id: int,
    step_order: int,
    action: Mapping[str, Any],
    action_output: Mapping[str, Any],
    status: str,
    error_message: str,
    environment_fingerprint: str,
    permission_fingerprint: str,
    artifacts: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    """Append a concrete step attempt and its raw evidence to the active plan revision."""
    with transaction.atomic():
        revision = (
            AIExecutionPlanRevision.objects.select_for_update()
            .filter(execution_record_id=execution_record_id)
            .order_by('-revision_number')
            .first()
        )
        if revision is None:
            raise ValueError('Execution plan revision does not exist.')
        step = revision.steps.select_for_update().filter(display_order=step_order).first()
        if step is None:
            raise ValueError(f'Execution step {step_order} does not exist.')

        last_attempt = step.attempts.aggregate(last_attempt=Max('attempt_number'))['last_attempt'] or 0
        completed_at = timezone.now() if status in {'completed', 'failed', 'stopped'} else None
        attempt = AIExecutionStepAttempt.objects.create(
            step=step,
            attempt_number=last_attempt + 1,
            action=_json_object(action),
            action_output=_json_object(action_output),
            status=status,
            error_message=error_message,
            environment_fingerprint=environment_fingerprint,
            permission_fingerprint=permission_fingerprint,
            completed_at=completed_at,
        )
        AIExecutionEvidenceArtifact.objects.bulk_create([
            AIExecutionEvidenceArtifact(
                attempt=attempt,
                artifact_type=_artifact_type(artifact),
                storage_path=_storage_path(artifact),
                content_hash=_content_hash(artifact),
                metadata={
                    **_json_object(artifact),
                    'environment_fingerprint': environment_fingerprint,
                    'permission_fingerprint': permission_fingerprint,
                },
            )
            for artifact in artifacts
        ])
        if status == 'completed':
            step.status = 'action_completed'
        elif status == 'failed':
            step.status = 'failed'
        step.save(update_fields=['status', 'updated_at'])
        return {
            'plan_revision': revision.revision_number,
            'attempt_number': attempt.attempt_number,
            'evidence_hashes': list(attempt.evidence_artifacts.values_list('content_hash', flat=True)),
        }


def _artifact_type(artifact: Mapping[str, Any]) -> str:
    value = artifact.get('type')
    return str(value).strip() if value else 'runtime_fact'


def _storage_path(artifact: Mapping[str, Any]) -> str:
    value = artifact.get('path')
    return str(value).strip() if value else ''


def _content_hash(artifact: Mapping[str, Any]) -> str:
    storage_path = _storage_path(artifact)
    artifact_file = _media_file(storage_path)
    hasher = hashlib.sha256()
    if artifact_file is not None and artifact_file.is_file():
        with artifact_file.open('rb') as stream:
            for chunk in iter(lambda: stream.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    hasher.update(_canonical_json(_json_object(artifact)).encode('utf-8'))
    return hasher.hexdigest()


def _media_file(storage_path: str) -> Path | None:
    if not storage_path:
        return None
    media_root = Path(settings.MEDIA_ROOT).resolve()
    candidate = (media_root / storage_path).resolve()
    try:
        candidate.relative_to(media_root)
    except ValueError:
        return None
    return candidate


def _json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_canonical_json(dict(value)))


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), sort_keys=True, default=str)