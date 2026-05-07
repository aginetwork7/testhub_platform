from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import AiProject, AICase, AIExecutionRecord

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
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    task_description = serializers.CharField()
    created_by_name = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else ''
        
    def get_project_name(self, obj):
        return obj.project.name if obj.project else ''

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return AICase.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.project_id = validated_data.get('project_id', instance.project_id)
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.task_description = validated_data.get('task_description', instance.task_description)
        instance.save()
        return instance

class AIExecutionRecordSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    project_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    ai_case_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    project_name = serializers.SerializerMethodField()
    ai_case_name = serializers.SerializerMethodField()
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
    executed_by_name = serializers.SerializerMethodField()
    gif_path = serializers.CharField(read_only=True, allow_null=True)
    screenshots_sequence = serializers.JSONField(read_only=True)

    def get_project_name(self, obj):
        return obj.project.name if obj.project else ''

    def get_ai_case_name(self, obj):
        return obj.ai_case.name if obj.ai_case else ''

    def get_executed_by_name(self, obj):
        return obj.executed_by.username if obj.executed_by else ''
