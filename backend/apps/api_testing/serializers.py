from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone


class NullableDateField(serializers.DateField):
    """允许空字符串的日期字段"""
    def to_internal_value(self, value):
        # 如果是空字符串，返回 None
        if value == '' or value is None:
            return None
        # 否则使用父类的正常处理
        return super().to_internal_value(value)
from .models import (
    ApiProject, ApiCollection, ApiRequest, Environment,
    RequestHistory, TestSuite, TestExecution, TestSuiteRequest,
    NotificationLog, OperationLog, AIServiceConfig,
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class ApiProjectSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    members = UserSerializer(many=True, read_only=True)
    member_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)
    start_date = NullableDateField(required=False, allow_null=True)
    end_date = NullableDateField(required=False, allow_null=True)

    class Meta:
        model = ApiProject
        fields = [
            'id', 'name', 'description', 'project_type', 'status',
            'owner', 'members', 'member_ids', 'start_date', 'end_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        # 将空字符串转换为 None
        if 'start_date' in attrs and attrs['start_date'] == '':
            attrs['start_date'] = None
        if 'end_date' in attrs and attrs['end_date'] == '':
            attrs['end_date'] = None
        return attrs

    def create(self, validated_data):
        member_ids = validated_data.pop('member_ids', [])
        validated_data['owner'] = self.context['request'].user
        project = super().create(validated_data)

        if member_ids:
            members = User.objects.filter(id__in=member_ids)
            project.members.set(members)

        self._sync_to_unified(project)
        return project

    def update(self, instance, validated_data):
        member_ids = validated_data.pop('member_ids', None)
        project = super().update(instance, validated_data)

        if member_ids is not None:
            members = User.objects.filter(id__in=member_ids)
            project.members.set(members)

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
                project_module = meta_project.modules.get(module_type='API')
                project_module.config = {
                    'project_type': project.project_type,
                    'owner': project.owner.id if project.owner else None,
                    'member_ids': list(project.members.values_list('id', flat=True)),
                    'start_date': str(project.start_date) if project.start_date else None,
                    'end_date': str(project.end_date) if project.end_date else None,
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
                module_type='API',
                config={
                    'project_type': project.project_type,
                    'owner': project.owner.id if project.owner else None,
                    'member_ids': list(project.members.values_list('id', flat=True)),
                }
            )


class ApiCollectionSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = ApiCollection
        fields = [
            'id', 'name', 'description', 'project', 'parent',
            'order', 'children', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_children(self, obj):
        children = obj.children.all()
        return ApiCollectionSerializer(children, many=True).data


class ApiRequestSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    collection = serializers.PrimaryKeyRelatedField(
        queryset=ApiCollection.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = ApiRequest
        fields = [
            'id', 'name', 'description', 'request_type', 'method', 'url',
            'headers', 'params', 'body', 'auth', 'pre_request_script',
            'post_request_script', 'assertions', 'collection', 'order', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        # 根据集合所属项目的类型设置接口类型
        collection = validated_data.get('collection')
        if collection and collection.project:
            if collection.project.project_type == 'WEBSOCKET':
                validated_data['request_type'] = 'WEBSOCKET'
            else:
                validated_data['request_type'] = 'HTTP'

        return super().create(validated_data)


class EnvironmentSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    project = serializers.PrimaryKeyRelatedField(
        queryset=ApiProject.objects.all(),
        required=False,
        allow_null=True
    )
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = Environment
        fields = [
            'id', 'name', 'scope', 'project', 'project_name', 'variables', 'is_active',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'project_name']

    def validate(self, attrs):
        if attrs.get('scope') == 'GLOBAL':
            attrs['project'] = None
        elif attrs.get('scope') == 'LOCAL' and not attrs.get('project'):
            raise serializers.ValidationError({'project': '局部环境变量必须关联项目'})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return data

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class RequestHistorySerializer(serializers.ModelSerializer):
    request = ApiRequestSerializer(read_only=True)
    environment = EnvironmentSerializer(read_only=True)
    executed_by = UserSerializer(read_only=True)

    class Meta:
        model = RequestHistory
        fields = [
            'id', 'request', 'environment', 'request_data', 'response_data',
            'status_code', 'response_time', 'error_message', 'assertions_results',
            'executed_by', 'executed_at'
        ]


class TestSuiteRequestSerializer(serializers.ModelSerializer):
    request = ApiRequestSerializer(read_only=True)

    class Meta:
        model = TestSuiteRequest
        fields = ['id', 'request', 'order', 'assertions', 'enabled']


class TestSuiteSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    suite_requests = TestSuiteRequestSerializer(source='testsuiterequest_set', many=True, read_only=True)

    class Meta:
        model = TestSuite
        fields = [
            'id', 'name', 'description', 'project', 'environment',
            'suite_requests', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class TestExecutionSerializer(serializers.ModelSerializer):
    test_suite = TestSuiteSerializer(read_only=True)
    executed_by = UserSerializer(read_only=True)

    class Meta:
        model = TestExecution
        fields = [
            'id', 'test_suite', 'status', 'start_time', 'end_time',
            'total_requests', 'passed_requests', 'failed_requests',
            'results', 'executed_by', 'created_at'
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # 添加项目名称信息
        if instance.test_suite and instance.test_suite.project:
            data['project_name'] = instance.test_suite.project.name
            data['test_suite_name'] = instance.test_suite.name
        return data


# ================ 通知管理序列化器 ================


class NotificationLogSerializer(serializers.ModelSerializer):
    """通知日志序列化器"""
    recipient_names = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    notification_type_display = serializers.SerializerMethodField()
    task_type_display = serializers.SerializerMethodField()
    retry_status = serializers.SerializerMethodField()
    notification_target_display = serializers.SerializerMethodField()

    class Meta:
        model = NotificationLog
        fields = ['id', 'task_id', 'task_name', 'task_type_display', 'notification_type_display', 'sender_name',
                  'recipient_names', 'notification_target_display', 'status_display', 'created_at', 'sent_at', 'retry_status']
        read_only_fields = ['created_at', 'sent_at']

    def get_recipient_names(self, obj):
        """获取收件人姓名列表"""
        if hasattr(obj, 'get_recipient_names'):
            return obj.get_recipient_names()
        recipient_info = obj.recipient_info or []
        if isinstance(recipient_info, list):
            return [r.get('name', r.get('email', '')) for r in recipient_info if isinstance(r, dict)]
        return []

    def get_status_display(self, obj):
        """获取状态显示"""
        return obj.get_status_display()

    def get_notification_type_display(self, obj):
        """获取通知类型显示"""
        return obj.get_notification_type_display()

    def get_task_type_display(self, obj):
        """获取任务类型显示 - 使用保存的快照值"""
        if obj.task_type:
            task_type_map = {
                'TEST_SUITE': '测试套件执行',
                'API_REQUEST': 'API请求执行',
            }
            return task_type_map.get(obj.task_type, obj.task_type)
        return "未记录"

    def get_retry_status(self, obj):
        """获取重试状态"""
        if obj.retry_count > 0:
            return f"已重试 {obj.retry_count} 次"
        return "未重试"

    def get_notification_target_display(self, obj):
        """获取通知对象显示"""
        targets = []

        # 检查是否有webhook机器人信息
        if obj.webhook_bot_info:
            bot_type = obj.webhook_bot_info.get('bot_type', '')
            bot_name = obj.webhook_bot_info.get('bot_name', '')

            # 根据机器人类型返回友好名称
            type_map = {
                'wechat': '企微机器人',
                'feishu': '飞书机器人',
                'dingtalk': '钉钉机器人'
            }
            bot_display = type_map.get(bot_type, 'Webhook机器人')
            if bot_name:
                targets.append(f"{bot_display}（{bot_name}）")
            else:
                targets.append(bot_display)

        # 检查是否有邮箱收件人
        if obj.recipient_info:
            if isinstance(obj.recipient_info, list) and len(obj.recipient_info) > 0:
                targets.append('邮箱')
            elif isinstance(obj.recipient_info, dict) and obj.recipient_info.get('email'):
                targets.append('邮箱')

        return ', '.join(targets) if targets else '-'


class NotificationLogDetailSerializer(serializers.ModelSerializer):
    """通知日志详情序列化器"""
    notification_type_display = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    task_type_display = serializers.SerializerMethodField()
    formatted_recipients = serializers.SerializerMethodField()
    webhook_bot_info_display = serializers.SerializerMethodField()
    notification_target_display = serializers.SerializerMethodField()

    class Meta:
        model = NotificationLog
        fields = ['id', 'task_id', 'task_name', 'task_type_display', 'notification_type_display', 'sender_name',
                  'sender_email', 'formatted_recipients', 'webhook_bot_info_display', 'notification_target_display',
                  'notification_content', 'status_display', 'error_message',
                  'created_at', 'sent_at', 'retry_count', 'is_retried']
        read_only_fields = ['created_at', 'sent_at']

    def get_notification_type_display(self, obj):
        """获取通知类型显示"""
        return obj.get_notification_type_display()

    def get_status_display(self, obj):
        """获取状态显示"""
        return obj.get_status_display()

    def get_task_type_display(self, obj):
        """获取任务类型显示 - 使用保存的快照值"""
        if obj.task_type:
            task_type_map = {
                'TEST_SUITE': '测试套件执行',
                'API_REQUEST': 'API请求执行',
            }
            return task_type_map.get(obj.task_type, obj.task_type)
        return "未记录"

    def get_formatted_recipients(self, obj):
        """获取格式化的收件人信息"""
        if not obj.recipient_info:
            return []

        recipients = []
        if isinstance(obj.recipient_info, list):
            for rec in obj.recipient_info:
                email = rec.get('email', '')
                if email:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    try:
                        user = User.objects.get(email=email)
                        name = user.first_name or user.username
                        recipients.append({
                            'name': name,
                            'email': email,
                            'display': f"{name}（{email}）"
                        })
                    except User.DoesNotExist:
                        recipients.append({
                            'name': email,
                            'email': email,
                            'display': email
                        })
        elif isinstance(obj.recipient_info, dict):
            email = obj.recipient_info.get('email', '')
            if email:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    user = User.objects.get(email=email)
                    name = user.first_name or user.username
                    recipients.append({
                        'name': name,
                        'email': email,
                        'display': f"{name}（{email}）"
                    })
                except User.DoesNotExist:
                    recipients.append({
                        'name': email,
                        'email': email,
                        'display': email
                    })
        return recipients

    def get_webhook_bot_info_display(self, obj):
        """获取Webhook机器人信息显示"""
        return obj.webhook_bot_info or {}

    def get_notification_target_display(self, obj):
        """获取通知对象显示 - 返回详细信息"""
        targets = []

        if obj.webhook_bot_info:
            bot_type = obj.webhook_bot_info.get('bot_type', '')
            bot_name = obj.webhook_bot_info.get('bot_name', '')

            type_map = {
                'wechat': '企微机器人',
                'feishu': '飞书机器人',
                'dingtalk': '钉钉机器人'
            }
            bot_display = type_map.get(bot_type, 'Webhook机器人')
            targets.append({
                'type': bot_type,
                'display': bot_display,
                'name': bot_name or bot_display
            })

        if obj.recipient_info:
            if isinstance(obj.recipient_info, list) and len(obj.recipient_info) > 0:
                emails = [rec.get('email', '') for rec in obj.recipient_info if rec.get('email')]
                if emails:
                    targets.append({
                        'type': 'email',
                        'display': '邮箱',
                        'name': ', '.join(emails)
                    })
            elif isinstance(obj.recipient_info, dict) and obj.recipient_info.get('email'):
                targets.append({
                    'type': 'email',
                    'display': '邮箱',
                    'name': obj.recipient_info.get('email')
                })

        return targets


class OperationLogSerializer(serializers.ModelSerializer):
    """操作日志序列化器"""
    user_name = serializers.CharField(source='user.username', read_only=True)
    operation_type_display = serializers.CharField(source='get_operation_type_display', read_only=True)
    resource_type_display = serializers.CharField(source='get_resource_type_display', read_only=True)

    class Meta:
        model = OperationLog
        fields = [
            'id', 'operation_type', 'operation_type_display',
            'resource_type', 'resource_type_display', 'resource_id',
            'resource_name', 'description', 'user', 'user_name', 'created_at'
        ]
        read_only_fields = ['created_at']


class AIServiceConfigSerializer(serializers.ModelSerializer):
    """AI服务配置序列化器"""
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = AIServiceConfig
        fields = [
            'id', 'name', 'service_type', 'service_type_display',
            'role', 'role_display', 'api_key', 'base_url', 'model_name',
            'max_tokens', 'temperature', 'is_active', 'created_by',
            'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)
