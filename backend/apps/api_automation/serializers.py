from rest_framework import serializers
from urllib.parse import urlparse
import json
from pathlib import Path

from .models import (
    ApiAutomationCase,
    ApiAutomationCoverageSnapshot,
    ApiAutomationCaseResult,
    ApiAutomationConfiguration,
    ApiAutomationEndpoint,
    ApiAutomationNotificationLog,
    ApiAutomationProject,
    ApiAutomationRun,
    ApiAutomationStep,
    ApiAutomationSuite,
)


HTTP_RESPONSE_SCHEMA_PATH = Path(__file__).resolve().parent / 'test_assets' / 'config' / 'schemas' / 'http_response_schemas.json'
_schema_cache: tuple[int, dict[str, object]] | None = None


def _http_response_schemas() -> dict[str, object]:
    global _schema_cache
    try:
        modified_at = HTTP_RESPONSE_SCHEMA_PATH.stat().st_mtime_ns
        if _schema_cache is None or _schema_cache[0] != modified_at:
            document = json.loads(HTTP_RESPONSE_SCHEMA_PATH.read_text(encoding='utf-8'))
            _schema_cache = (modified_at, document.get('schemas', {}))
        return _schema_cache[1]
    except (OSError, json.JSONDecodeError):
        return {}


class ApiAutomationStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiAutomationStep
        fields = '__all__'


class ApiAutomationCaseSerializer(serializers.ModelSerializer):
    steps = ApiAutomationStepSerializer(many=True, read_only=True)

    class Meta:
        model = ApiAutomationCase
        fields = '__all__'


class ApiAutomationCaseListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiAutomationCase
        fields = [
            'id', 'suite', 'name', 'description', 'source_path', 'source_class',
            'source_function', 'node_id', 'priority', 'markers', 'parameter_sets',
            'capabilities', 'execution_mode', 'is_skipped', 'skip_reason',
            'is_active', 'created_at', 'updated_at',
        ]


class ApiAutomationSuiteSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    cases = ApiAutomationCaseListSerializer(many=True, read_only=True)

    class Meta:
        model = ApiAutomationSuite
        fields = ['id', 'name', 'source_path', 'description', 'parent', 'order', 'children', 'cases']

    def get_children(self, instance):
        return ApiAutomationSuiteSerializer(instance.children.all(), many=True).data


class ApiAutomationProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiAutomationProject
        fields = '__all__'
        read_only_fields = ['owner', 'members']


class ApiAutomationEndpointSerializer(serializers.ModelSerializer):
    protocol = serializers.SerializerMethodField()
    schema_status = serializers.SerializerMethodField()
    schema_status_codes = serializers.SerializerMethodField()

    def get_protocol(self, instance):
        return 'HTTP'

    def get_schema_status_codes(self, instance):
        schemas = _http_response_schemas()
        prefix = {f'{method} {instance.path} ' for method in instance.methods}
        return sorted({key.rsplit(' ', 1)[-1] for key in schemas if any(key.startswith(item) for item in prefix)})

    def get_schema_status(self, instance):
        return 'GENERATED' if self.get_schema_status_codes(instance) else 'MISSING'

    class Meta:
        model = ApiAutomationEndpoint
        fields = '__all__'


class ApiAutomationCoverageSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiAutomationCoverageSnapshot
        fields = '__all__'


class ApiAutomationNotificationLogSerializer(serializers.ModelSerializer):
    channel_display = serializers.CharField(source='get_channel_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    execution_status = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    def get_execution_status(self, instance):
        return instance.run.status if instance.run_id else instance.execution_status

    def get_message(self, instance):
        if instance.run_id is None:
            return instance.message
        run = instance.run
        outcome = '完成' if run.status == 'COMPLETED' else '失败'
        return f'运行 #{run.id} 已{outcome}：通过 {run.passed_cases}，失败 {run.failed_cases}，跳过 {run.skipped_cases}。'

    class Meta:
        model = ApiAutomationNotificationLog
        fields = '__all__'


class ApiAutomationConfigurationSerializer(serializers.ModelSerializer):
    websocket_url = serializers.CharField(allow_blank=True, required=False)

    def validate_websocket_url(self, value):
        if not value:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {'ws', 'wss', 'http', 'https'} or not parsed.netloc:
            raise serializers.ValidationError('请输入合法的 HTTP、HTTPS、WebSocket 或 Secure WebSocket 地址。')
        return value

    class Meta:
        model = ApiAutomationConfiguration
        fields = '__all__'
        read_only_fields = ['created_by']


class ApiAutomationCaseResultSerializer(serializers.ModelSerializer):
    case = ApiAutomationCaseSerializer(read_only=True)

    class Meta:
        model = ApiAutomationCaseResult
        fields = '__all__'


class ApiAutomationRunSerializer(serializers.ModelSerializer):
    case_results = ApiAutomationCaseResultSerializer(many=True, read_only=True)

    class Meta:
        model = ApiAutomationRun
        fields = '__all__'
        read_only_fields = [
            'status', 'total_cases', 'passed_cases', 'failed_cases', 'skipped_cases',
            'started_at', 'ended_at', 'log_content', 'report_path', 'executed_by',
        ]