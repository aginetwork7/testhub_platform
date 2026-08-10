"""Authenticated API endpoints for durable Alpha workflows."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai_testing.alpha.access import accessible_ai_project_queryset
from apps.ai_testing.alpha.orchestrator import AlphaOrchestrationError, AlphaOrchestrator
from apps.ai_testing.alpha.serializers import (
    AlphaPlanRevisionSerializer,
    AlphaRunCreateSerializer,
    AlphaRunSerializer,
)
from apps.ai_testing.alpha.skills.catalog import build_phase_one_registry
from apps.ai_testing.alpha.skills.registry import SkillRegistryError
from apps.ai_testing.alpha.tasks import enqueue_alpha_planning
from apps.ai_testing.models import AlphaDispatchIntent, AlphaRun, AlphaTaskNode


class AlphaRunViewSet(viewsets.ModelViewSet):
    """Create, inspect, start, and cancel owner- or project-scoped Alpha runs."""

    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        accessible_projects = accessible_ai_project_queryset(self.request.user)
        return (
            AlphaRun.objects.filter(Q(initiated_by=self.request.user) | Q(project__in=accessible_projects))
            .select_related('project', 'initiated_by', 'active_revision')
            .prefetch_related('approval_requests__task')
            .distinct()
            .order_by('-created_at')
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return AlphaRunCreateSerializer
        return AlphaRunSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = serializer.save()
        return Response(AlphaRunSerializer(run, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        run = self.get_object()
        if run.status in {'draft', 'collecting_input', 'planning', 'awaiting_confirmation', 'executing', 'reflecting'}:
            return Response({'detail': 'Active runs cannot be deleted'}, status=status.HTTP_409_CONFLICT)
        run.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def revisions(self, request, pk=None):
        run = self.get_object()
        revisions = run.revisions.prefetch_related('task_nodes').order_by('revision_number')
        return Response(AlphaPlanRevisionSerializer(revisions, many=True).data)

    @action(detail=True, methods=['post'])
    def plan(self, request, pk=None):
        with transaction.atomic():
            run = AlphaRun.objects.select_for_update().get(pk=self.get_object().pk)
            if run.status in {'completed', 'failed', 'cancelled'}:
                return Response({'detail': 'Terminal runs cannot be planned'}, status=status.HTTP_409_CONFLICT)
            if run.planner_task_id:
                return Response({'detail': 'Planning is already queued'}, status=status.HTTP_409_CONFLICT)
            run.status = 'planning'
            run.error_message = ''
            run.state_version += 1
            run.save(update_fields=['status', 'error_message', 'state_version', 'updated_at'])
        task_id = enqueue_alpha_planning(run.id)
        return Response({'task_id': task_id, 'status': 'planning'}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        run = self.get_object()
        revision_id = request.data.get('revision_id')
        if not isinstance(revision_id, int):
            return Response({'detail': 'revision_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = AlphaOrchestrator(build_phase_one_registry()).freeze_and_prepare_execution(run.id, revision_id)
        except (AlphaOrchestrationError, SkillRegistryError) as error:
            return Response({'detail': str(error)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {
                'revision_id': result.revision_id,
                'dispatch_intent_ids': result.dispatch_intent_ids,
                'approval_request_ids': result.approval_request_ids,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(
        detail=True,
        methods=['post'],
        url_path=r'approvals/(?P<approval_id>[^/.]+)/decision',
    )
    def approval_decision(self, request, pk=None, approval_id=None):
        approve = request.data.get('approve')
        if not isinstance(approve, bool):
            return Response({'detail': 'approve must be a boolean'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            numeric_approval_id = int(approval_id)
        except (TypeError, ValueError):
            return Response({'detail': 'approval_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        run = self.get_object()
        try:
            result = AlphaOrchestrator(build_phase_one_registry()).decide_approval(
                run.id,
                numeric_approval_id,
                request.user,
                approve,
            )
        except (AlphaOrchestrationError, SkillRegistryError) as error:
            return Response({'detail': str(error)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {
                'approval_id': result.approval_id,
                'approved': approve,
                'dispatch_intent_ids': result.dispatch_intent_ids,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            run = AlphaRun.objects.select_for_update().get(pk=self.get_object().pk)
            if run.status in {'completed', 'failed', 'cancelled'}:
                return Response({'detail': 'Run is already terminal'}, status=status.HTTP_409_CONFLICT)
            run.status = 'cancelled'
            run.cancelled_at = timezone.now()
            run.state_version += 1
            run.save(update_fields=['status', 'cancelled_at', 'state_version', 'updated_at'])
            AlphaDispatchIntent.objects.filter(task__revision__run=run, status__in=['pending', 'claimed']).update(
                status='cancelled',
            )
            AlphaTaskNode.objects.filter(
                revision__run=run,
                status__in=['pending', 'awaiting_confirmation', 'dispatched'],
            ).update(status='cancelled')
        return Response(AlphaRunSerializer(run, context=self.get_serializer_context()).data)