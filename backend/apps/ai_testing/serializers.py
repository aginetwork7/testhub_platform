from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import models
from .models import AiProject, AICase, AIExecutionExperience, AIExecutionRecord

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class AiProjectSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)
    created_by_name = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else ''

    def create(self, validated_data):
        from apps.unified_projects.models import MetaProject, ProjectModule
        
        user = self.context['request'].user
        validated_data['created_by'] = user
        
        # 1. 先创建子项目
        project = AiProject.objects.create(**validated_data)
        
        # 2. 自动创建并关联元项目
        meta_project = MetaProject.objects.create(
            name=project.name,
            description=project.description,
            owner=user,
            status='not_started'
        )
        
        # 3. 创建元项目模块关联
        project_module = ProjectModule.objects.create(
            meta_project=meta_project,
            module_type='AI_TEST',
            ai_project=project,
            config={
                'owner': user.id,
                'member_ids': []
            }
        )
        
        # 4. 反向更新子项目的元项目关联
        project.unified_meta_project = meta_project
        project.save()
        
        return project

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.save()
        return instance

class AICaseSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    project_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    project_name = serializers.SerializerMethodField()
    name = serializers.CharField(max_length=200)
    case_number = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    priority = serializers.ChoiceField(choices=AICase.PRIORITY_CHOICES, required=False, default='P0')
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    task_description = serializers.CharField(required=False, allow_blank=True)
    case_mode = serializers.ChoiceField(choices=AICase.CASE_MODE_CHOICES, required=False, default='freeform')
    task_steps = serializers.JSONField(required=False)
    planned_steps = serializers.JSONField(required=False)
    created_by_name = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else ''
        
    def get_project_name(self, obj):
        return obj.project.name if obj.project else ''

    def validate(self, attrs):
        case_mode = attrs.get('case_mode') or getattr(self.instance, 'case_mode', 'freeform')
        task_description = attrs.get('task_description')
        if task_description is None and self.instance is not None:
            task_description = self.instance.task_description

        task_steps = attrs.get('task_steps')
        if task_steps is None and self.instance is not None:
            task_steps = self.instance.task_steps

        if case_mode in {'structured', 'hybrid'}:
            if not isinstance(task_steps, list) or not task_steps:
                raise serializers.ValidationError({'task_steps': 'structured mode requires a non-empty step list'})
        elif not str(task_description or '').strip():
            raise serializers.ValidationError({'task_description': 'freeform mode requires task_description'})

        return attrs

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return AICase.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.project_id = validated_data.get('project_id', instance.project_id)
        instance.name = validated_data.get('name', instance.name)
        instance.case_number = validated_data.get('case_number', instance.case_number)
        instance.priority = validated_data.get('priority', instance.priority)
        instance.description = validated_data.get('description', instance.description)
        instance.task_description = validated_data.get('task_description', instance.task_description)
        instance.case_mode = validated_data.get('case_mode', instance.case_mode)
        instance.task_steps = validated_data.get('task_steps', instance.task_steps)
        instance.planned_steps = validated_data.get('planned_steps', instance.planned_steps)
        instance.save()
        return instance

class AIExecutionRecordSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    project_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    ai_case_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    project_name = serializers.SerializerMethodField()
    ai_case_name = serializers.SerializerMethodField()
    case_number = serializers.SerializerMethodField()
    case_name = serializers.CharField(max_length=200, required=False)
    task_description = serializers.CharField(required=False, allow_blank=True)
    execution_mode = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    start_time = serializers.DateTimeField(read_only=True)
    end_time = serializers.DateTimeField(read_only=True, allow_null=True)
    duration = serializers.FloatField(read_only=True, allow_null=True)
    logs = serializers.CharField(read_only=True, allow_blank=True)
    steps_completed = serializers.JSONField(read_only=True)
    planned_tasks = serializers.JSONField(read_only=True)
    planner_trace = serializers.JSONField(read_only=True)
    artifacts = serializers.JSONField(read_only=True)
    cache_stats = serializers.JSONField(read_only=True)
    executed_by_name = serializers.SerializerMethodField()
    gif_path = serializers.CharField(read_only=True, allow_null=True)
    screenshots_sequence = serializers.JSONField(read_only=True)

    def get_project_name(self, obj):
        return obj.project.name if obj.project else '未归档'

    def get_ai_case_name(self, obj):
        return obj.ai_case.name if obj.ai_case else ''

    def get_case_number(self, obj):
        return obj.ai_case.case_number if obj.ai_case else ''

    def get_executed_by_name(self, obj):
        return obj.executed_by.username if obj.executed_by else ''


class AIExecutionExperienceSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    ai_case_name = serializers.CharField(source='ai_case.name', read_only=True, default='')

    class Meta:
        model = AIExecutionExperience
        fields = [
            'id', 'project', 'project_name', 'ai_case', 'ai_case_name', 'execution_record',
            'step_description', 'page_url', 'environment_key', 'action_sequence', 'status',
            'review_status', 'review_note', 'success_count', 'failure_count', 'confidence',
            'last_verified_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields
