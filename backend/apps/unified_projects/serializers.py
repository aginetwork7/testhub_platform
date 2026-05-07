from rest_framework import serializers
from django.db import models, transaction
from .models import MetaProject, MetaProjectMember, ProjectModule
from apps.users.serializers import UserSerializer
from apps.projects.models import Project, ProjectMember
from apps.api_testing.models import ApiProject
from apps.ui_automation.models import UiProject
from apps.app_automation.models import AppProject


def resolve_module_owner(meta_project, config):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    owner_id = config.get('owner')
    if owner_id:
        try:
            return User.objects.get(id=owner_id)
        except User.DoesNotExist:
            return meta_project.owner
    return meta_project.owner


def sync_ai_generation_project(project, meta_project, config):
    project.name = meta_project.name
    project.description = meta_project.description
    project.status = meta_project.status
    project.owner = resolve_module_owner(meta_project, config)
    project.unified_meta_project = meta_project
    project.save()

    member_ids = config.get('member_ids') or []
    member_ids = [member_id for member_id in member_ids if member_id and member_id != project.owner_id]
    valid_member_ids = set(
        project.owner.__class__.objects.filter(id__in=member_ids).values_list('id', flat=True)
    )

    project.projectmember_set.exclude(user_id__in=valid_member_ids).delete()

    existing_member_ids = set(project.projectmember_set.values_list('user_id', flat=True))
    for member_id in valid_member_ids - existing_member_ids:
        ProjectMember.objects.create(
            project=project,
            user_id=member_id,
            role='tester'
        )


class ProjectModuleSerializer(serializers.ModelSerializer):
    """项目模块序列化器"""

    module_type_display = serializers.CharField(source='get_module_type_display', read_only=True)
    project_info = serializers.SerializerMethodField()
    child_project_id = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()
    jump_url = serializers.SerializerMethodField()

    class Meta:
        model = ProjectModule
        fields = ['id', 'module_type', 'module_type_display', 'config', 'project_info',
                  'child_project_id', 'statistics', 'jump_url', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_project_info(self, obj):
        project = obj.get_project()
        if project:
            return {
                'id': project.id,
                'name': project.name,
                'status': getattr(project, 'status', None),
            }
        return None

    def get_child_project_id(self, obj):
        project = obj.get_project()
        return project.id if project else None

    def get_statistics(self, obj):
        project = obj.get_project()
        if not project:
            return None

        if obj.module_type == 'AI':
            return self._get_ai_stats(project)
        elif obj.module_type == 'AI_TEST':
            return self._get_ai_test_stats(project)
        elif obj.module_type == 'API':
            return self._get_api_stats(project)
        elif obj.module_type == 'UI':
            return self._get_ui_stats(project)
        elif obj.module_type == 'APP':
            return self._get_app_stats(project)
        return None

    def get_jump_url(self, obj):
        if obj.module_type == 'AI':
            return f'/ai-generation/projects/{obj.meta_project.id}'
        elif obj.module_type == 'AI_TEST':
            return f'/ai-intelligent-mode/projects'
        elif obj.module_type == 'API':
            return f'/api-testing/projects/{obj.meta_project.id}'
        elif obj.module_type == 'UI':
            return f'/ui-automation/projects/{obj.meta_project.id}'
        elif obj.module_type == 'APP':
            return f'/app-automation/projects/{obj.meta_project.id}'
        return None

    def _get_ai_test_stats(self, project):
        from apps.ai_testing.models import AICase, AIExecutionRecord

        return {
            'case_count': AICase.objects.filter(project=project).count(),
            'execution_count': AIExecutionRecord.objects.filter(project=project).count(),
        }

    def _get_ai_stats(self, project):
        from apps.testcases.models import TestCase
        from apps.testsuites.models import TestSuite
        from apps.requirement_analysis.models import RequirementDocument

        return {
            'testcase_count': TestCase.objects.filter(project=project).count(),
            'testsuite_count': TestSuite.objects.filter(project=project).count(),
            'requirement_count': RequirementDocument.objects.filter(project=project).count(),
        }

    def _get_api_stats(self, project):
        from apps.api_testing.models import ApiCollection, ApiRequest, TestSuite, TestExecution

        collection_count = ApiCollection.objects.filter(project=project).count()
        request_count = ApiRequest.objects.filter(collection__project=project).count()
        test_suite_count = TestSuite.objects.filter(project=project).count()
        execution_count = TestExecution.objects.filter(test_suite__project=project).count()

        return {
            'collection_count': collection_count,
            'request_count': request_count,
            'test_suite_count': test_suite_count,
            'execution_count': execution_count,
        }

    def _get_ui_stats(self, project):
        from apps.ui_automation.models import ElementGroup, Element, TestScript, PageObject, TestCase

        return {
            'element_group_count': ElementGroup.objects.filter(project=project).count(),
            'element_count': Element.objects.filter(project=project).count(),
            'script_count': TestScript.objects.filter(project=project).count(),
            'page_object_count': PageObject.objects.filter(project=project).count(),
            'test_case_count': TestCase.objects.filter(project=project).count(),
        }

    def _get_app_stats(self, project):
        from apps.app_automation.models import AppElement, AppTestCase

        return {
            'element_count': AppElement.objects.filter(project=project).count(),
            'test_case_count': AppTestCase.objects.filter(project=project).count(),
        }


class ProjectModuleCreateSerializer(serializers.ModelSerializer):
    """创建项目模块序列化器"""

    class Meta:
        model = ProjectModule
        fields = ['module_type', 'config']


class MetaProjectMemberSerializer(serializers.ModelSerializer):
    """元项目成员序列化器"""

    user_info = UserSerializer(source='user', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = MetaProjectMember
        fields = ['id', 'user', 'user_info', 'role', 'role_display', 'joined_at']
        read_only_fields = ['id', 'joined_at']


class MetaProjectListSerializer(serializers.ModelSerializer):
    """元项目列表序列化器"""

    owner_info = UserSerializer(source='owner', read_only=True)
    module_count = serializers.SerializerMethodField()
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    modules = serializers.SerializerMethodField()

    class Meta:
        model = MetaProject
        fields = ['id', 'name', 'description', 'status', 'owner', 'owner_info',
                  'module_count', 'modules', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner']

    def get_module_count(self, obj):
        return obj.modules.count()

    def get_modules(self, obj):
        return ProjectModuleSerializer(obj.modules.all(), many=True).data


class MetaProjectDetailSerializer(serializers.ModelSerializer):
    """元项目详情序列化器"""

    owner_info = UserSerializer(source='owner', read_only=True)
    members = MetaProjectMemberSerializer(source='meta_project_members', many=True, read_only=True)
    modules = ProjectModuleSerializer(many=True, read_only=True)
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = MetaProject
        fields = ['id', 'name', 'description', 'status', 'owner', 'owner_info',
                  'members', 'modules', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner']


class MetaProjectCreateSerializer(serializers.ModelSerializer):
    """创建元项目序列化器"""

    modules = ProjectModuleCreateSerializer(many=True, required=False)

    class Meta:
        model = MetaProject
        fields = ['id', 'name', 'description', 'status', 'modules']

    def validate_modules(self, value):
        module_types = [m['module_type'] for m in value]
        if len(module_types) != len(set(module_types)):
            raise serializers.ValidationError('模块类型不能重复')
        valid_types = ['AI', 'AI_TEST', 'API', 'UI', 'APP']
        for mt in module_types:
            if mt not in valid_types:
                raise serializers.ValidationError(f'无效的模块类型: {mt}')
        return value

    @transaction.atomic
    def create(self, validated_data):
        modules_data = validated_data.pop('modules', [])
        validated_data['owner'] = self.context['request'].user

        if not modules_data:
            modules_data = [{'module_type': 'AI', 'config': {}}]

        meta_project = MetaProject.objects.create(
            name=validated_data['name'],
            description=validated_data.get('description', ''),
            status=validated_data.get('status', 'not_started'),
            owner=validated_data['owner']
        )

        MetaProjectMember.objects.create(
            meta_project=meta_project,
            user=meta_project.owner,
            role='owner'
        )

        for module_data in modules_data:
            module_type = module_data.get('module_type')
            config = module_data.get('config', {})

            project_module = ProjectModule.objects.create(
                meta_project=meta_project,
                module_type=module_type,
                config=config
            )

            self._create_child_project(project_module, config)

        return meta_project

    def _create_child_project(self, project_module, config):
        """为模块类型创建子项目"""
        meta_project = project_module.meta_project
        module_type = project_module.module_type

        if module_type == 'AI':
            project = Project.objects.filter(unified_meta_project=meta_project).first()
            if not project:
                project = Project.objects.create(
                    name=meta_project.name,
                    description=meta_project.description,
                    status=meta_project.status,
                    owner=resolve_module_owner(meta_project, config),
                    unified_meta_project=meta_project
                )
            sync_ai_generation_project(project, meta_project, config)

        elif module_type == 'AI_TEST':
            from apps.ai_testing.models import AiProject

            ai_project = AiProject.objects.create(
                name=meta_project.name,
                description=meta_project.description,
                created_by=meta_project.owner,
                unified_meta_project=meta_project
            )
            # owner_id shouldn't be null if the model has an owner field, but AiProject uses created_by instead
            # so we explicitly set created_by
            project_module.ai_project = ai_project
            project_module.save()

        elif module_type == 'API':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            owner_id = config.get('owner')
            owner_instance = None
            if owner_id:
                try:
                    owner_instance = User.objects.get(id=owner_id)
                except User.DoesNotExist:
                    owner_instance = meta_project.owner
            else:
                owner_instance = meta_project.owner

            api_project = ApiProject.objects.create(
                name=meta_project.name,
                description=meta_project.description,
                project_type='HTTP',
                status=meta_project.status,
                owner=owner_instance,
                unified_meta_project=meta_project
            )
            project_module.api_project = api_project
            project_module.save()

        elif module_type == 'UI':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            owner_id = config.get('owner')
            owner_instance = None
            if owner_id:
                try:
                    owner_instance = User.objects.get(id=owner_id)
                except User.DoesNotExist:
                    owner_instance = meta_project.owner
            else:
                owner_instance = meta_project.owner

            ui_project = UiProject.objects.create(
                name=meta_project.name,
                description=meta_project.description,
                status=meta_project.status,
                base_url=config.get('base_url', 'http://localhost'),
                owner=owner_instance,
                unified_meta_project=meta_project
            )
            project_module.ui_project = ui_project
            project_module.save()

        elif module_type == 'APP':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            owner_id = config.get('owner')
            owner_instance = None
            if owner_id:
                try:
                    owner_instance = User.objects.get(id=owner_id)
                except User.DoesNotExist:
                    owner_instance = meta_project.owner
            else:
                owner_instance = meta_project.owner

            app_project = AppProject.objects.create(
                name=meta_project.name,
                description=meta_project.description,
                status=meta_project.status,
                owner=owner_instance,
                unified_meta_project=meta_project
            )
            project_module.app_project = app_project
            project_module.save()


class MetaProjectUpdateSerializer(serializers.ModelSerializer):
    """更新元项目序列化器"""

    modules = ProjectModuleCreateSerializer(many=True, required=False)

    class Meta:
        model = MetaProject
        fields = ['id', 'name', 'description', 'status', 'modules']

    def validate_modules(self, value):
        module_types = [m['module_type'] for m in value]
        if len(module_types) != len(set(module_types)):
            raise serializers.ValidationError('模块类型不能重复')
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        modules_data = validated_data.pop('modules', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if modules_data is not None:
            self._update_modules(instance, modules_data)

        self._sync_child_projects(instance)

        return instance

    def _update_modules(self, meta_project, modules_data):
        """更新项目模块配置"""
        existing_types = set(meta_project.modules.values_list('module_type', flat=True))
        new_types = set(m['module_type'] for m in modules_data)

        # 删除前端取消勾选的模块
        types_to_delete = existing_types - new_types
        if types_to_delete:
            meta_project.modules.filter(module_type__in=types_to_delete).delete()

        for module_data in modules_data:
            module_type = module_data.get('module_type')
            config = module_data.get('config', {})

            try:
                project_module = meta_project.modules.get(module_type=module_type)
                project_module.config = config
                project_module.save()

                self._sync_module_to_child_project(project_module, config)
            except ProjectModule.DoesNotExist:
                project_module = ProjectModule.objects.create(
                    meta_project=meta_project,
                    module_type=module_type,
                    config=config
                )
                self._create_child_project(project_module, config)
                self._sync_module_to_child_project(project_module, config)

    def _create_child_project(self, project_module, config):
        """复用MetaProjectCreateSerializer的_create_child_project逻辑"""
        meta_project = project_module.meta_project
        module_type = project_module.module_type

        if module_type == 'AI':
            project = Project.objects.filter(unified_meta_project=meta_project).first()
            if not project:
                project = Project.objects.create(
                    name=meta_project.name,
                    description=meta_project.description,
                    status=meta_project.status,
                    owner=resolve_module_owner(meta_project, config),
                    unified_meta_project=meta_project
                )
            sync_ai_generation_project(project, meta_project, config)

        elif module_type == 'AI_TEST':
            from apps.ai_testing.models import AiProject

            # Check if it already exists (e.g. was soft-deleted or just unlinked from module)
            ai_project = AiProject.objects.filter(unified_meta_project=meta_project).first()
            if not ai_project:
                ai_project = AiProject.objects.create(
                    name=meta_project.name,
                    description=meta_project.description,
                    created_by=meta_project.owner,
                    unified_meta_project=meta_project
                )
            
            project_module.ai_project = ai_project
            project_module.save()

        elif module_type == 'API':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            owner_id = config.get('owner')
            owner_instance = None
            if owner_id:
                try:
                    owner_instance = User.objects.get(id=owner_id)
                except User.DoesNotExist:
                    owner_instance = meta_project.owner
            else:
                owner_instance = meta_project.owner

            from apps.api_testing.models import ApiProject
            api_project = ApiProject.objects.filter(unified_meta_project=meta_project).first()
            if not api_project:
                api_project = ApiProject.objects.create(
                    name=meta_project.name,
                    description=meta_project.description,
                    project_type='HTTP',
                    status=meta_project.status,
                    owner=owner_instance,
                    unified_meta_project=meta_project
                )
            project_module.api_project = api_project
            project_module.save()

        elif module_type == 'UI':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            owner_id = config.get('owner')
            owner_instance = None
            if owner_id:
                try:
                    owner_instance = User.objects.get(id=owner_id)
                except User.DoesNotExist:
                    owner_instance = meta_project.owner
            else:
                owner_instance = meta_project.owner

            from apps.ui_automation.models import UiProject
            ui_project = UiProject.objects.filter(unified_meta_project=meta_project).first()
            if not ui_project:
                ui_project = UiProject.objects.create(
                    name=meta_project.name,
                    description=meta_project.description,
                    status=meta_project.status,
                    base_url=config.get('base_url', 'http://localhost'),
                    owner=owner_instance,
                    unified_meta_project=meta_project
                )
            project_module.ui_project = ui_project
            project_module.save()

        elif module_type == 'APP':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            owner_id = config.get('owner')
            owner_instance = None
            if owner_id:
                try:
                    owner_instance = User.objects.get(id=owner_id)
                except User.DoesNotExist:
                    owner_instance = meta_project.owner
            else:
                owner_instance = meta_project.owner

            from apps.app_automation.models import AppProject
            app_project = AppProject.objects.filter(unified_meta_project=meta_project).first()
            if not app_project:
                app_project = AppProject.objects.create(
                    name=meta_project.name,
                    description=meta_project.description,
                    status=meta_project.status,
                    owner=owner_instance,
                    unified_meta_project=meta_project
                )
            project_module.app_project = app_project
            project_module.save()

    def _sync_module_to_child_project(self, project_module, config):
        """同步模块配置到子项目"""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        project = project_module.get_project()
        if not project:
            return

        if project_module.module_type == 'AI':
            sync_ai_generation_project(project, project_module.meta_project, config)
            return

        for key, value in config.items():
            if key in ('module_type', 'id'):
                continue
            if not hasattr(project, key):
                continue

            field = project._meta.get_field(key)
            if field.is_relation:
                if isinstance(field, models.ForeignKey):
                    if key in ['owner', 'created_by']:
                        # owner/created_by are foreign keys, we need the User instance, not just the ID.
                        try:
                            if value:
                                user_obj = User.objects.get(id=value)
                                setattr(project, key, user_obj)
                            else:
                                # fallback to meta_project owner if explicitly set to null
                                setattr(project, key, project_module.meta_project.owner)
                        except User.DoesNotExist:
                            pass
                        continue
                    if value is not None:
                        try:
                            setattr(project, key, value)
                        except (ValueError, field.related_model.DoesNotExist):
                            pass
                elif value is not None:
                    try:
                        setattr(project, key, value)
                    except (ValueError, field.related_model.DoesNotExist):
                        pass
            elif value is not None:
                setattr(project, key, value)

        project.save()

    def _sync_child_projects(self, meta_project):
        """同步子项目状态"""
        for module in meta_project.modules.all():
            project = module.get_project()
            if project:
                project.name = meta_project.name
                project.description = meta_project.description
                if hasattr(project, 'status'):
                    project.status = meta_project.status
                project.save()
