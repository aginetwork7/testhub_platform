"""DRF serializers for Alpha workflow runs and immutable revisions."""

from rest_framework import serializers

from apps.ai_testing.alpha.access import accessible_ai_project_queryset
from apps.ai_testing.models import AlphaApprovalRequest, AlphaPlanRevision, AlphaRun, AlphaTaskNode


class AlphaRunCreateSerializer(serializers.Serializer):
    original_request = serializers.CharField(max_length=10_000, trim_whitespace=True)
    project_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_original_request(self, value: str) -> str:
        if not value:
            raise serializers.ValidationError('original_request cannot be empty')
        return value

    def validate_project_id(self, value: int | None) -> int | None:
        if value is None:
            return None
        user = self.context['request'].user
        if not accessible_ai_project_queryset(user).filter(pk=value).exists():
            raise serializers.ValidationError('Project does not exist or is not accessible')
        return value

    def create(self, validated_data: dict[str, object]) -> AlphaRun:
        request = self.context['request']
        return AlphaRun.objects.create(initiated_by=request.user, **validated_data)


class AlphaTaskNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlphaTaskNode
        fields = [
            'id', 'task_key', 'parent', 'display_order', 'skill_name', 'skill_version', 'tier',
            'risk_metadata', 'normalized_arguments', 'status', 'attempts', 'evidence', 'error_message',
        ]
        read_only_fields = fields


class AlphaPlanRevisionSerializer(serializers.ModelSerializer):
    task_nodes = AlphaTaskNodeSerializer(many=True, read_only=True)

    class Meta:
        model = AlphaPlanRevision
        fields = [
            'id', 'revision_number', 'status', 'planner_output', 'content_hash', 'frozen_at',
            'created_at', 'task_nodes',
        ]
        read_only_fields = fields


class AlphaApprovalRequestSerializer(serializers.ModelSerializer):
    task_key = serializers.CharField(source='task.task_key', read_only=True)

    class Meta:
        model = AlphaApprovalRequest
        fields = [
            'id', 'revision', 'task', 'task_key', 'arguments_hash', 'risk_metadata', 'status', 'expires_at',
            'requested_at', 'decided_at', 'decided_by',
        ]
        read_only_fields = fields


class AlphaRunSerializer(serializers.ModelSerializer):
    active_revision = AlphaPlanRevisionSerializer(read_only=True)
    approval_requests = AlphaApprovalRequestSerializer(many=True, read_only=True)

    class Meta:
        model = AlphaRun
        fields = [
            'id', 'project', 'initiated_by', 'original_request', 'status', 'round_count', 'state_version',
            'planner_task_id', 'reflection_task_id', 'active_revision', 'final_output', 'error_message',
            'approval_requests', 'cancelled_at', 'created_at',
            'updated_at',
        ]
        read_only_fields = fields