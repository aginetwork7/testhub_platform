from rest_framework import serializers
from django.db import transaction
from .models import Project, ProjectMember, ProjectEnvironment
from apps.users.serializers import UserSerializer


class ProjectSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ('id', 'name')


class ProjectEnvironmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectEnvironment
        fields = '__all__'


class ProjectMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ProjectMember
        fields = ['id', 'user', 'user_id', 'role', 'joined_at']


class ProjectSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    members = ProjectMemberSerializer(source='projectmember_set', many=True, read_only=True)
    environments = ProjectEnvironmentSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'status', 'owner', 'members',
                 'environments', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProjectCreateSerializer(serializers.ModelSerializer):
    create_unified = serializers.BooleanField(write_only=True, default=True, required=False)

    class Meta:
        model = Project
        fields = ['name', 'description', 'status', 'create_unified']

    @transaction.atomic
    def create(self, validated_data):
        create_unified = validated_data.pop('create_unified', True)
        validated_data['owner'] = self.context['request'].user
        project = super().create(validated_data)

        if create_unified:
            self._sync_to_unified(project)

        return project

    @transaction.atomic
    def update(self, instance, validated_data):
        create_unified = validated_data.pop('create_unified', True)
        project = super().update(instance, validated_data)

        self._sync_to_unified(project)

        return project

    def _sync_to_unified(self, project):
        from apps.unified_projects.models import MetaProject, ProjectModule

        if project.unified_meta_project:
            meta_project = project.unified_meta_project
            meta_project.name = project.name
            meta_project.description = project.description
            meta_project.status = project.status
            meta_project.save()

            try:
                project_module = meta_project.modules.get(module_type='AI')
                project_module.config = {
                    'owner': project.owner.id if project.owner else None,
                    'member_ids': list(project.members.values_list('id', flat=True)),
                }
                project_module.save()
            except ProjectModule.DoesNotExist:
                pass
        else:
            meta_project = MetaProject.objects.create(
                name=project.name,
                description=project.description,
                status=project.status,
                owner=project.owner
            )
            project.unified_meta_project = meta_project
            project.save()

            ProjectModule.objects.create(
                meta_project=meta_project,
                module_type='AI',
                config={
                    'owner': project.owner.id if project.owner else None,
                    'member_ids': list(project.members.values_list('id', flat=True)),
                }
            )
