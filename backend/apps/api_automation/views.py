from pathlib import Path
import os
import hashlib
import io
import json
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Q
from django.utils import timezone
import yaml
from django_q.tasks import async_task
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import (
    ApiAutomationCase,
    ApiAutomationCoverageSnapshot,
    ApiAutomationConfiguration,
    ApiAutomationEndpoint,
    ApiAutomationNotificationLog,
    ApiAutomationProject,
    ApiAutomationSchemaSnapshot,
    ApiAutomationRun,
    ApiAutomationSuite,
)


class ApiAutomationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
from .coverage import collect_endpoint_coverage
from .serializers import HTTP_RESPONSE_SCHEMA_PATH
from .executor import estimate_run_task_timeout
from .swagger_sync import (
    SwaggerSourceNotFoundError,
    SwaggerSyncError,
    SwaggerTokenExpiredError,
    SwaggerTokenPermissionError,
    synchronize_remote_swagger,
)
from .serializers import (
    ApiAutomationCaseSerializer,
    ApiAutomationCaseListSerializer,
    ApiAutomationConfigurationSerializer,
    ApiAutomationCoverageSnapshotSerializer,
    ApiAutomationEndpointSerializer,
    ApiAutomationNotificationLogSerializer,
    ApiAutomationProjectSerializer,
    ApiAutomationRunSerializer,
    ApiAutomationSuiteSerializer,
)
from .device_cli_serializers import DeviceCliExecuteSerializer
from .device_cli_skill import DeviceCliSkill, DeviceCliSkillError


class ProjectAccessMixin:
    def accessible_projects(self):
        return ApiAutomationProject.objects.filter(Q(owner=self.request.user) | Q(members=self.request.user)).distinct()


class ApiAutomationProjectViewSet(ProjectAccessMixin, viewsets.ModelViewSet):
    serializer_class = ApiAutomationProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.accessible_projects()

    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        project.members.add(self.request.user)


class ApiAutomationSuiteViewSet(ProjectAccessMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ApiAutomationSuiteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ApiAutomationSuite.objects.filter(project__in=self.accessible_projects()).prefetch_related('children', 'cases__steps')

    @action(detail=False, methods=['get'])
    def tree(self, request):
        project_id = request.query_params.get('project_id')
        queryset = self.get_queryset().filter(parent__isnull=True)
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return Response(self.get_serializer(queryset, many=True).data)


class ApiAutomationCaseViewSet(ProjectAccessMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ApiAutomationCaseSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filterset_fields = ['suite', 'priority', 'execution_mode', 'is_skipped', 'is_active']
    search_fields = ['name', 'source_path', 'source_class', 'source_function', 'node_id']

    def get_queryset(self):
        queryset = ApiAutomationCase.objects.filter(
            suite__project__in=self.accessible_projects()
        ).prefetch_related('steps')
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(suite__project_id=project_id)
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return ApiAutomationCaseListSerializer
        return ApiAutomationCaseSerializer


class ApiAutomationEndpointViewSet(ProjectAccessMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ApiAutomationEndpointSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ApiAutomationPagination
    filterset_fields = ['project']
    search_fields = ['key', 'path']

    def get_queryset(self):
        queryset = ApiAutomationEndpoint.objects.filter(project__in=self.accessible_projects()).order_by('path', 'key')
        path = self.request.query_params.get('path')
        category = self.request.query_params.get('category', 'frontend')
        if category == 'frontend':
            queryset = queryset.filter(tags__icontains='frontend/')
        elif category == 'others':
            queryset = queryset.exclude(tags__icontains='frontend/')
        else:
            raise ValidationError({'category': '仅支持 frontend 或 others。'})
        return queryset.filter(path__icontains=path) if path else queryset

    @action(detail=False, methods=['get'])
    def schema_status(self, request):
        project = self.accessible_projects().filter(id=request.query_params.get('project')).first()
        if project is None:
            return Response({'error': '项目不存在或无权限访问。'}, status=status.HTTP_404_NOT_FOUND)
        document = _load_http_schema_document()
        snapshot = project.schema_snapshots.first()
        return Response({
            'source_hash': document.get('source_hash', ''),
            'schema_count': document.get('schema_count', 0),
            'missing_schema_count': document.get('missing_schema_count', 0),
            'generated_at': datetime.fromtimestamp(HTTP_RESPONSE_SCHEMA_PATH.stat().st_mtime, tz=timezone.get_current_timezone()) if HTTP_RESPONSE_SCHEMA_PATH.is_file() else None,
            'latest_snapshot': {
                'created_at': snapshot.created_at,
                'change_summary': snapshot.change_summary,
            } if snapshot else None,
        })

    @action(detail=False, methods=['post'])
    def regenerate_schemas(self, request):
        project = self.accessible_projects().filter(id=request.data.get('project')).first()
        if project is None:
            return Response({'error': '项目不存在或无权限访问。'}, status=status.HTTP_404_NOT_FOUND)
        output = io.StringIO()
        try:
            swagger_url = settings.API_AUTOMATION_SWAGGER_URL.strip()
            sync_result = None
            if swagger_url:
                sync_result = synchronize_remote_swagger(
                    project=project,
                    source_url=swagger_url,
                    timeout_seconds=settings.API_AUTOMATION_SWAGGER_TIMEOUT_SECONDS,
                    access_token=settings.API_AUTOMATION_SWAGGER_TOKEN,
                )
                output.write(sync_result['paths_output'])
                output.write(sync_result['schemas_output'])
            else:
                call_command('generate_api_automation_schemas', stdout=output)
        except (SwaggerTokenExpiredError, SwaggerTokenPermissionError, SwaggerSourceNotFoundError) as error:
            return Response(
                {'error': str(error), 'code': error.code},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except (CommandError, SwaggerSyncError) as error:
            return Response({'error': str(error)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        document = _load_http_schema_document()
        fingerprints = {
            key: hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
            for key, value in document.get('schemas', {}).items()
        }
        previous = project.schema_snapshots.first()
        previous_fingerprints = previous.schema_fingerprints if previous else {}
        added = sorted(set(fingerprints) - set(previous_fingerprints))
        removed = sorted(set(previous_fingerprints) - set(fingerprints))
        changed = sorted(key for key in set(fingerprints) & set(previous_fingerprints) if fingerprints[key] != previous_fingerprints[key])
        change_summary = {'added': added, 'removed': removed, 'changed': changed}
        snapshot = ApiAutomationSchemaSnapshot.objects.create(
            project=project,
            source_hash=document.get('source_hash', ''),
            schema_count=document.get('schema_count', 0),
            schema_fingerprints=fingerprints,
            change_summary=change_summary,
        )
        return Response({
            'schema_count': snapshot.schema_count,
            'source_hash': snapshot.source_hash,
            'change_summary': change_summary,
            'output': output.getvalue(),
            'catalog': sync_result['catalog'] if sync_result else None,
            'synced_from_remote': sync_result is not None,
        })


def _load_http_schema_document() -> dict:
    try:
        return json.loads(HTTP_RESPONSE_SCHEMA_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


class ApiAutomationNotificationLogViewSet(ProjectAccessMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ApiAutomationNotificationLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ApiAutomationPagination
    filterset_fields = ['project', 'run', 'status', 'channel']

    def get_queryset(self):
        return ApiAutomationNotificationLog.objects.filter(project__in=self.accessible_projects()).select_related('run')


class ApiAutomationCoverageViewSet(ProjectAccessMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def stats(self, request):
        project_id = request.query_params.get('project')
        project = self.accessible_projects().filter(id=project_id).first()
        if project is None:
            return Response({'error': '项目不存在或无权限访问。'}, status=status.HTTP_404_NOT_FOUND)
        snapshots = ApiAutomationCoverageSnapshot.objects.filter(project=project)
        current_week = snapshots.filter(period='WEEKLY').order_by('-snapshot_date').first()
        current_month = snapshots.filter(period='MONTHLY').order_by('-snapshot_date').first()
        endpoint_total = ApiAutomationEndpoint.objects.filter(project=project).count()
        endpoint_coverage = collect_endpoint_coverage(project)
        covered_count = sum(bool(entry.case_node_ids) for entry in endpoint_coverage.values())
        coverage_rate = round((covered_count / endpoint_total * 100) if endpoint_total else 0, 2)
        serializer = ApiAutomationCoverageSnapshotSerializer
        return Response({
            'total_endpoints': endpoint_total,
            'covered_endpoints': covered_count,
            'uncovered_endpoints': endpoint_total - covered_count,
            'coverage_rate': coverage_rate,
            'endpoint_details': [
                {
                    'key': endpoint.key,
                    'name': endpoint.summary or endpoint.key,
                    'path': endpoint.path,
                    'covered': bool(entry.case_node_ids),
                    'case_count': len(entry.case_node_ids),
                    'sources': sorted(entry.source_files),
                }
                for endpoint in ApiAutomationEndpoint.objects.filter(project=project).order_by('key')
                for entry in [endpoint_coverage[endpoint.key]]
            ],
            'weekly_trend': serializer(snapshots.filter(period='WEEKLY').order_by('snapshot_date'), many=True).data,
            'monthly_trend': serializer(snapshots.filter(period='MONTHLY').order_by('snapshot_date'), many=True).data,
            'updated_at': timezone.now(),
        })


class ApiAutomationConfigurationViewSet(ProjectAccessMixin, viewsets.ModelViewSet):
    serializer_class = ApiAutomationConfigurationSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ['project', 'is_default']

    def get_queryset(self):
        return ApiAutomationConfiguration.objects.all()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        configuration = self.get_object()
        ApiAutomationConfiguration.objects.filter(project=configuration.project).exclude(id=configuration.id).update(is_default=False)
        configuration.is_default = True
        configuration.save(update_fields=['is_default'])
        return Response(ApiAutomationConfigurationSerializer(configuration).data)

    @action(detail=True, methods=['post'], url_path='device-cli')
    def execute_device_cli(self, request, pk=None):
        configuration = self.get_object()
        serializer = DeviceCliExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = DeviceCliSkill().execute(configuration, **serializer.validated_data)
        except DeviceCliSkillError as error:
            return Response({'error': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)

    def _load_template(self):
        template_path = Path(__file__).resolve().parent / 'test_assets' / 'config' / 'config.template.yaml'
        return yaml.safe_load(template_path.read_text(encoding='utf-8')) or {}

    @action(detail=False, methods=['get'])
    def template(self, request):
        try:
            template = self._load_template()
        except (OSError, yaml.YAMLError) as error:
            return Response({'error': f'读取测试配置模板失败: {error}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(template)

    @action(detail=False, methods=['post'])
    def initialize(self, request):
        project = ApiAutomationProject.objects.filter(id=request.data.get('project')).first()
        if project is None:
            return Response({'error': '项目不存在或无权限访问。'}, status=status.HTTP_404_NOT_FOUND)
        try:
            template = self._load_template()
        except (OSError, yaml.YAMLError) as error:
            return Response({'error': f'读取测试配置模板失败: {error}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        ApiAutomationConfiguration.objects.filter(project=project).update(is_default=False)
        configuration, created = ApiAutomationConfiguration.objects.update_or_create(
            project=project,
            name='默认测试环境',
            defaults={
                'base_url': template.get('api', {}).get('base_url', ''),
                'websocket_url': template.get('websocket', {}).get('url', ''),
                'variables': {
                    'data_endpoints': {},
                    'model_images': {},
                    'default_role': 'dealer',
                },
                'auth_profiles': template.get('auth', {}).get('users', {}),
                'payment_config': template.get('payment', {}),
                'model_profiles': template.get('models', {}),
                'runtime_settings': template,
                'timeout_seconds': template.get('api', {}).get('timeout', 30),
                'max_workers': template.get('test', {}).get('max_workers', 1),
                'is_default': True,
                'created_by': request.user,
            },
        )
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(ApiAutomationConfigurationSerializer(configuration).data, status=response_status)


class ApiAutomationRunViewSet(ProjectAccessMixin, viewsets.ModelViewSet):
    serializer_class = ApiAutomationRunSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ApiAutomationPagination
    http_method_names = ['get', 'head', 'options', 'delete', 'post']
    filterset_fields = ['project', 'status', 'configuration']

    def get_queryset(self):
        queryset = ApiAutomationRun.objects.filter(project__in=self.accessible_projects())
        if self.request.query_params.get('has_report') == 'true':
            queryset = queryset.exclude(report_path='')
        if self.action == 'retrieve':
            queryset = queryset.prefetch_related('case_results__case__steps')
        return queryset

    def destroy(self, request, *args, **kwargs):
        run = self.get_object()
        if run.status in {'PENDING', 'RUNNING'}:
            return Response(
                {'error': '待执行或执行中的记录不能删除，请等待执行结束。'},
                status=status.HTTP_409_CONFLICT,
            )
        from apps.scheduler.models import ScheduleConfig, recalculate_api_automation_schedule_stats
        from django_q.models import Success

        affected_schedule_ids = []
        for config in ScheduleConfig.objects.filter(task_type='API_AUTOMATION_SUITE').select_related('schedule'):
            records = Success.objects.filter(func=config.schedule.func)
            if any(isinstance(record.result, dict) and record.result.get('run_id') == run.id for record in records):
                affected_schedule_ids.append(config.schedule_id)
        ApiAutomationNotificationLog.objects.filter(run=run).delete()
        run.delete()
        for schedule_id in affected_schedule_ids:
            recalculate_api_automation_schedule_stats(schedule_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def logs(self, request):
        log_path = Path(settings.API_AUTOMATION_LOG_FILE)
        try:
            content = _filter_accessible_log_lines(
                _read_log_tail(log_path),
                set(self.accessible_projects().values_list('id', flat=True)),
            )
            file_size = log_path.stat().st_size if log_path.exists() else 0
        except OSError as error:
            return Response({'error': f'读取 API 自动化日志失败: {error}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({
            'content': content,
            'file_size': file_size,
            'max_file_size': settings.API_AUTOMATION_LOG_MAX_BYTES,
            'rotated_files': sorted(path.name for path in log_path.parent.glob(f'{log_path.name}.*')),
            'updated_at': timezone.now(),
        })

    @action(detail=False, methods=['post'])
    def start(self, request):
        project_id = request.data.get('project_id')
        configuration_id = request.data.get('configuration_id')
        if not project_id:
            return Response({'error': 'project_id 为必填项。'}, status=status.HTTP_400_BAD_REQUEST)
        project = self.accessible_projects().filter(id=project_id).first()
        if project is None:
            return Response({'error': '项目不存在或无权限访问。'}, status=status.HTTP_404_NOT_FOUND)

        configuration = None
        if configuration_id:
            configuration = ApiAutomationConfiguration.objects.filter(
                id=configuration_id,
                project=project,
            ).first()
            if configuration is None:
                return Response({'error': '执行配置不存在或不属于当前项目。'}, status=status.HTTP_400_BAD_REQUEST)

        run = ApiAutomationRun.objects.create(
            project=project,
            configuration=configuration,
            selection=request.data.get('selection', {}),
            executed_by=request.user,
        )
        task_id = async_task(
            'apps.api_automation.executor.execute_run',
            run.id,
            timeout=estimate_run_task_timeout(run),
        )
        response_data = self.get_serializer(run).data
        response_data['task_id'] = task_id
        return Response(response_data, status=status.HTTP_201_CREATED)


def _read_log_tail(log_path: Path, max_bytes: int = 100_000) -> str:
    if not log_path.exists():
        return ''
    with log_path.open('rb') as log_file:
        log_file.seek(0, os.SEEK_END)
        file_size = log_file.tell()
        log_file.seek(max(0, file_size - max_bytes))
        content = log_file.read().decode('utf-8', errors='replace')
    return content[content.find('\n') + 1:] if file_size > max_bytes else content


def _filter_accessible_log_lines(content: str, project_ids: set[int]) -> str:
    markers = tuple(f'project_id={project_id} ' for project_id in project_ids)
    return '\n'.join(line for line in content.splitlines() if any(marker in line for marker in markers))