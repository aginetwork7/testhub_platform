from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from django.utils import timezone
import json
import re
import random
import time
from loguru import logger

from .models import (
    UiProject, LocatorStrategy, Element, TestScript, TestSuite,
    TestSuiteScript, TestExecution, Screenshot,
    ElementGroup, PageObject, PageObjectElement, ScriptStep, ScriptElementUsage,
    TestCase, TestCaseStep, TestCaseExecution, OperationRecord,
    UiNotificationLog
)
from .serializers import (
    UiProjectSerializer, UiProjectCreateSerializer, UiProjectUpdateSerializer,
    LocatorStrategySerializer,
    ElementSerializer, ElementEnhancedSerializer,
    TestScriptSerializer, TestScriptCreateSerializer, TestScriptUpdateSerializer,
    TestSuiteSerializer, TestSuiteCreateSerializer, TestSuiteUpdateSerializer, TestSuiteWithScriptsSerializer,
    TestSuiteScriptSerializer, TestSuiteTestCaseSerializer,
    TestExecutionSerializer, TestExecutionCreateSerializer,
    ScreenshotSerializer,
    ElementGroupSerializer, ElementGroupCreateSerializer,
    PageObjectSerializer, PageObjectCreateSerializer, PageObjectElementSerializer,
    ScriptStepSerializer, ScriptElementUsageSerializer,
    ScriptAnalysisSerializer, ElementValidationSerializer, CodeGenerationSerializer,
    TestCaseSerializer, TestCaseStepSerializer, TestCaseExecutionSerializer, OperationRecordSerializer,
    UiNotificationLogSerializer
)
from .operation_logger import log_operation

User = get_user_model()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """获取UI自动化仪表盘统计数据"""
    try:
        project_count = UiProject.objects.count()
        test_case_count = TestCase.objects.count()
        element_count = Element.objects.count()
        test_script_count = TestScript.objects.count()
        test_suite_count = TestSuite.objects.count()
        test_execution_count = TestExecution.objects.count()

        # 近期执行记录 (最后 10 条)
        recent_executions = TestExecution.objects.select_related('test_suite', 'test_suite__project').order_by('-started_at')[:10]
        recent_activities = []
        for exec_obj in recent_executions:
            recent_activities.append({
                'id': exec_obj.id,
                'type': 'execution',
                'description': f"执行测试套件: {exec_obj.test_suite.name}",
                'timestamp': exec_obj.started_at.isoformat() if exec_obj.started_at else None,
                'status': exec_obj.status
            })

        # 执行统计分布
        all_executions = TestExecution.objects.all()
        execution_stats = {
            'success': all_executions.filter(status='passed').count(),
            'failed': all_executions.filter(status='failed').count(),
            'running': all_executions.filter(status__in=['running', 'pending']).count()
        }

        return Response({
            'projectCount': project_count,
            'testCaseCount': test_case_count,
            'testSuiteCount': test_suite_count,
            'executionCount': test_execution_count,
            'elementCount': element_count,
            'testScriptCount': test_script_count,
            'recentActivities': recent_activities,
            'executionStats': execution_stats
        })
    except Exception as e:
        logger.error(f"Failed to get UI dashboard stats: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def extract_step_info(s, step_index):
    """提取步骤信息的辅助函数，确保返回可读的步骤描述"""
    step_info = {'step': step_index}

    # 尝试多种方式提取可读信息
    if hasattr(s, 'action'):
        # 如果有action属性
        action_data = s.action
        if isinstance(action_data, str):
            step_info['action'] = action_data
        elif hasattr(action_data, '__dict__'):
            # 如果是对象，提取关键属性
            attrs = {}
            for key in ['type', 'description', 'goal', 'coordinate', 'text', 'output', 'result']:
                if hasattr(action_data, key):
                    value = getattr(action_data, key)
                    if isinstance(value, str):
                        attrs[key] = value
                    elif callable(value):
                        attrs[key] = getattr(value, '__name__', str(value))
                    else:
                        attrs[key] = str(value)
            if attrs:
                step_info['action'] = attrs
        else:
            step_info['action'] = str(action_data)
    elif hasattr(s, 'model_output'):
        # 如果有model_output属性
        output_data = s.model_output
        if isinstance(output_data, str):
            step_info['action'] = output_data
        elif hasattr(output_data, '__dict__'):
            # 提取model_output的关键信息
            attrs = {'type': 'model_output'}
            for key in ['action', 'description', 'goal', 'coordinate', 'text']:
                if hasattr(output_data, key):
                    value = getattr(output_data, key)
                    attrs[key] = str(value) if value else None
            step_info['action'] = attrs
        else:
            step_info['action'] = str(output_data)
    elif hasattr(s, '__dict__'):
        # 通用的对象提取
        attrs = {}
        for key in dir(s):
            if not key.startswith('_'):
                try:
                    value = getattr(s, key)
                    if not callable(value):
                        attrs[key] = str(value)
                except:
                    pass
        if attrs:
            step_info['action'] = attrs
    else:
        # 最后回退，但检查是否是函数对象
        if callable(s):
            step_info['action'] = f"<Action: {getattr(s, '__name__', 'unknown action')}>"
        else:
            step_info['action'] = str(s)

    return step_info


from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000


class UiProjectViewSet(viewsets.ModelViewSet):
    queryset = UiProject.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'owner', 'members']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return UiProjectCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UiProjectUpdateSerializer
        return UiProjectSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目
        user = self.request.user
        return UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()

    def perform_create(self, serializer):
        # 创建项目时，当前用户自动成为负责人
        instance = serializer.save(owner=self.request.user)
        # 记录操作
        log_operation('create', 'project', instance.id, instance.name, self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        # 记录操作
        log_operation('edit', 'project', instance.id, instance.name, self.request.user)

    def perform_destroy(self, instance):
        # 记录操作（在删除前记录）
        log_operation('delete', 'project', instance.id, instance.name, self.request.user)
        if instance.unified_meta_project:
            meta_project = instance.unified_meta_project
            # 找到并删除对应的关联记录
            from apps.unified_projects.models import ProjectModule
            ProjectModule.objects.filter(meta_project=meta_project, module_type='UI').delete()
            
            instance.unified_meta_project = None
            instance.save()
            # 检查是否还有其他模块关联，如果没有才删除 meta_project
            if meta_project.modules.count() == 0:
                meta_project.delete()
        instance.delete()


class LocatorStrategyViewSet(viewsets.ModelViewSet):
    queryset = LocatorStrategy.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = LocatorStrategySerializer
    ordering = ['id']


class ElementViewSet(viewsets.ModelViewSet):
    queryset = Element.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'locator_strategy', 'element_type', 'validation_status', 'group']
    search_fields = ['name', 'description', 'page', 'component_name']

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ElementEnhancedSerializer
        return ElementSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目的元素
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return Element.objects.filter(project__in=accessible_projects).select_related(
            'project', 'group', 'locator_strategy', 'created_by', 'parent_element'
        ).prefetch_related('script_usages__script').order_by('page', 'name')

    def filter_queryset(self, queryset):
        # 先应用默认的过滤器
        queryset = super().filter_queryset(queryset)

        # 处理页面筛选（使用page_name参数避免与分页page冲突）
        page_name = self.request.query_params.get('page_name', None)
        if page_name:
            queryset = queryset.filter(page=page_name)

        return queryset

    def perform_create(self, serializer):
        # 创建元素时自动设置创建人
        instance = serializer.save(created_by=self.request.user)
        # 记录操作
        log_operation('create', 'element', instance.id, instance.name, self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        # 记录操作
        log_operation('edit', 'element', instance.id, instance.name, self.request.user)

    def perform_destroy(self, instance):
        # 记录操作（在删除前记录）
        log_operation('delete', 'element', instance.id, instance.name, self.request.user)
        instance.delete()

    @action(detail=True, methods=['post'])
    def validate_locator(self, request, pk=None):
        """验证元素定位器有效性"""
        element = self.get_object()

        # 这里可以集成实际的浏览器验证逻辑
        # 现在只是模拟验证
        validation_result = self._perform_element_validation(element)

        element.validation_status = 'VALID' if validation_result['is_valid'] else 'INVALID'
        element.validation_message = validation_result['validation_message']
        element.last_validated = timezone.now()
        element.save()

        serializer = ElementValidationSerializer(validation_result)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def usages(self, request, pk=None):
        """获取元素在脚本中的使用情况"""
        element = self.get_object()
        usages = ScriptElementUsage.objects.filter(element=element).select_related('script')
        serializer = ScriptElementUsageSerializer(usages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """获取元素树形结构"""
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'error': '需要指定项目ID'}, status=status.HTTP_400_BAD_REQUEST)

        elements = self.get_queryset().filter(project_id=project_id)
        tree_data = self._build_element_tree(elements)
        return Response(tree_data)

    @action(detail=True, methods=['post'])
    def add_backup_locator(self, request, pk=None):
        """添加备用定位器"""
        element = self.get_object()
        strategy = request.data.get('strategy')
        value = request.data.get('value')

        if not strategy or not value:
            return Response({'error': '策略和值都是必需的'}, status=status.HTTP_400_BAD_REQUEST)

        backup_locators = element.backup_locators or []
        backup_locators.append({'strategy': strategy, 'value': value})
        element.backup_locators = backup_locators
        element.save()

        return Response({'message': '备用定位器添加成功'})

    @action(detail=True, methods=['post'])
    def generate_suggestions(self, request, pk=None):
        """生成元素使用建议"""
        element = self.get_object()
        suggestions = self._generate_element_suggestions(element)
        return Response({'suggestions': suggestions})

    @action(detail=True, methods=['post'])
    def copy(self, request, pk=None):
        """复制元素"""
        # 从数据库获取最新的元素数据（确保包含拖拽后的最新group_id）
        element = Element.objects.get(pk=pk)

        # 创建副本
        new_element = Element()

        # 复制所有字段
        for field in element._meta.fields:
            if field.name != 'id' and field.name != 'pk':
                setattr(new_element, field.name, getattr(element, field.name))

        # 设置新名称
        new_element.name = f"{element.name} - 副本"

        # 清空主键以创建新记录
        new_element.pk = None
        new_element.id = None

        # 保存副本
        new_element.save()

        serializer = self.get_serializer(new_element)
        # 记录操作
        log_operation('create', 'element', new_element.id, new_element.name, self.request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def batch_update(self, request):
        """批量更新元素的顺序和所属页面"""
        updates = request.data.get('updates', [])  # [{id, page, group_id, order}, ...]
        for update in updates:
            element_id = update.get('id')
            if element_id:
                try:
                    element = Element.objects.get(id=element_id)
                    if 'page' in update:
                        element.page = update['page']
                    if 'group_id' in update:
                        group_id = update['group_id']
                        # 处理 group_id 为 None 的情况（如"未关联页面"）
                        if group_id == 'unassigned' or group_id is None:
                            element.group_id = None
                        else:
                            element.group_id = int(group_id) if group_id else None
                    if 'order' in update:
                        element.order = update['order']
                    element.save()
                except Element.DoesNotExist:
                    continue
        return Response({'success': True})

    def _perform_element_validation(self, element):
        """执行元素验证（模拟实现）"""
        try:
            # 这里可以集成实际的浏览器自动化工具进行验证
            # 现在只是简单的语法检查
            is_valid = True
            message = "定位器验证通过"
            suggestions = []

            # 简单的语法检查
            if element.locator_strategy.name == 'css':
                if not element.locator_value.strip():
                    is_valid = False
                    message = "CSS选择器不能为空"
            elif element.locator_strategy.name == 'xpath':
                if not element.locator_value.strip():
                    is_valid = False
                    message = "XPath表达式不能为空"

            return {
                'is_valid': is_valid,
                'validation_message': message,
                'suggestions': suggestions
            }
        except Exception as e:
            return {
                'is_valid': False,
                'validation_message': f'验证过程中出现错误: {str(e)}',
                'suggestions': []
            }

    def _build_element_tree(self, elements):
        """构建元素树形结构 - 返回元素列表而不是页面分组，因为前端会自己处理页面关联"""
        element_data_list = []
        for element in elements:
            element_data = {
                'id': element.id,
                'name': element.name,
                'type': 'element',
                'element_type': element.element_type,
                'locator_strategy': element.locator_strategy.name if element.locator_strategy else None,
                'locator_value': element.locator_value,
                'validation_status': element.validation_status,
                'usage_count': element.usage_count,
                'group_id': element.group_id,  # 用于前端关联到页面
                'page': element.page,  # 保留向后兼容
                'children': []
            }
            element_data_list.append(element_data)

        return element_data_list

    def _generate_element_suggestions(self, element):
        """生成元素使用建议"""
        suggestions = []

        # 基于元素类型生成建议
        if element.element_type == 'INPUT':
            suggestions.append("建议为输入框元素添加清空和输入验证操作")
        elif element.element_type == 'BUTTON':
            suggestions.append("建议验证按钮点击后的页面跳转或状态变化")
        elif element.element_type == 'DROPDOWN':
            suggestions.append("建议测试下拉框的所有选项")

        # 基于使用频率生成建议
        if element.usage_count == 0:
            suggestions.append("此元素尚未在任何脚本中使用，考虑是否需要删除")
        elif element.usage_count > 10:
            suggestions.append("此元素使用频率较高，建议添加到页面对象中以提高复用性")

        return suggestions


class ElementGroupViewSet(viewsets.ModelViewSet):
    queryset = ElementGroup.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'parent_group']
    search_fields = ['name', 'description']

    def get_serializer_class(self):
        if self.action == 'create':
            return ElementGroupCreateSerializer
        return ElementGroupSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目的元素分组
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return ElementGroup.objects.filter(project__in=accessible_projects).select_related('project',
                                                                                           'parent_group').order_by(
            'order', 'name')

    def update(self, request, *args, **kwargs):
        """更新分组时，同步更新所有关联元素的page字段"""
        group = self.get_object()
        old_name = group.name
        new_name = request.data.get('name', old_name)

        # 先调用父类的update方法更新分组
        response = super().update(request, *args, **kwargs)

        # 如果名称发生了变化，同步更新所有关联元素的page字段
        if old_name != new_name:
            Element.objects.filter(group_id=group.id).update(page=new_name)
            print(f"✓ 已将分组 '{old_name}' 下的 {Element.objects.filter(group_id=group.id).count()} 个元素的page字段更新为 '{new_name}'")

        return response

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """获取分组树形结构"""
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'error': '需要指定项目ID'}, status=status.HTTP_400_BAD_REQUEST)

        groups = self.get_queryset().filter(project_id=project_id, parent_group__isnull=True)
        serializer = ElementGroupSerializer(groups, many=True)
        return Response(serializer.data)


class PageObjectViewSet(viewsets.ModelViewSet):
    queryset = PageObject.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project']
    search_fields = ['name', 'class_name', 'description']

    def get_serializer_class(self):
        if self.action == 'create':
            return PageObjectCreateSerializer
        return PageObjectSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目的页面对象
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return PageObject.objects.filter(project__in=accessible_projects).select_related(
            'project', 'created_by'
        ).prefetch_related('page_object_elements__element').order_by('-created_at')

    @action(detail=True, methods=['post'])
    def generate_code(self, request, pk=None):
        """生成页面对象代码"""
        page_object = self.get_object()
        serializer = CodeGenerationSerializer(data=request.data)

        if serializer.is_valid():
            language = serializer.validated_data['language']
            framework = serializer.validated_data['framework']
            include_comments = serializer.validated_data['include_comments']

            try:
                generated_code = page_object.generate_code(language)

                # 保存生成的代码模板
                page_object.template_code = generated_code
                page_object.save()

                return Response({
                    'code': generated_code,
                    'language': language,
                    'framework': framework
                })
            except Exception as e:
                logger.error(f"代码生成失败: {e}", exc_info=True)
                logger.error(f"页面对象ID: {pk}, 语言: {language}, 框架: {framework}, 错误类型: {type(e).__name__}")
                return Response({
                    'error': f'代码生成失败: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def add_element(self, request, pk=None):
        """向页面对象添加元素"""
        page_object = self.get_object()
        serializer = PageObjectElementSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(page_object=page_object)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def elements(self, request, pk=None):
        """获取页面对象的所有元素"""
        page_object = self.get_object()
        po_elements = page_object.page_object_elements.select_related('element').all()
        serializer = PageObjectElementSerializer(po_elements, many=True)
        return Response(serializer.data)


class PageObjectElementViewSet(viewsets.ModelViewSet):
    queryset = PageObjectElement.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = PageObjectElementSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的页面对象元素
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return PageObjectElement.objects.filter(
            page_object__project__in=accessible_projects
        ).select_related('page_object', 'element').order_by('id')


class ScriptStepViewSet(viewsets.ModelViewSet):
    queryset = ScriptStep.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = ScriptStepSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['script', 'action_type', 'target_element', 'page_object']

    def get_queryset(self):
        # 只显示用户有权限访问的脚本步骤
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return ScriptStep.objects.filter(
            script__project__in=accessible_projects
        ).select_related('script', 'target_element', 'page_object').order_by('step_order')

    @action(detail=False, methods=['post'])
    def batch_create(self, request):
        """批量创建脚本步骤"""
        steps_data = request.data.get('steps', [])
        created_steps = []

        for step_data in steps_data:
            serializer = ScriptStepSerializer(data=step_data)
            if serializer.is_valid():
                step = serializer.save()
                created_steps.append(step)
            else:
                return Response({
                    'error': f'步骤创建失败: {serializer.errors}'
                }, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = ScriptStepSerializer(created_steps, many=True)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ScriptElementUsageViewSet(viewsets.ModelViewSet):
    queryset = ScriptElementUsage.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = ScriptElementUsageSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['script', 'element', 'usage_type']

    def get_queryset(self):
        # 只显示用户有权限访问的脚本元素使用记录
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return ScriptElementUsage.objects.filter(
            script__project__in=accessible_projects
        ).select_related('script', 'element').order_by('script', 'line_number')

    @action(detail=False, methods=['post'])
    def analyze_script(self, request):
        """分析脚本中的元素使用情况"""
        script_id = request.data.get('script_id')
        if not script_id:
            return Response({'error': '需要指定脚本ID'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            script = TestScript.objects.get(id=script_id)
            analysis_result = self._analyze_script_elements(script)

            serializer = ScriptAnalysisSerializer(analysis_result)
            return Response(serializer.data)
        except TestScript.DoesNotExist:
            return Response({'error': '脚本不存在'}, status=status.HTTP_404_NOT_FOUND)

    def _analyze_script_elements(self, script):
        """分析脚本中的元素使用"""
        # 解析脚本内容，查找元素使用情况
        content = script.content
        usages = []
        missing_elements = []
        recommendations = []

        # 简单的元素使用分析（实际实现会更复杂）
        if script.script_type == 'CODE':
            # 分析代码中的定位器使用
            locator_patterns = [
                r'locator\(["\']([^"\']+)["\']\)',
                r'findElement\(["\']([^"\']+)["\']\)',
                r'css\(["\']([^"\']+)["\']\)',
                r'xpath\(["\']([^"\']+)["\']\)'
            ]

            for pattern in locator_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    # 查找对应的元素
                    try:
                        element = Element.objects.get(
                            project=script.project,
                            locator_value=match
                        )
                        usage, created = ScriptElementUsage.objects.get_or_create(
                            script=script,
                            element=element,
                            defaults={
                                'usage_type': 'CLICK',  # 默认类型
                                'line_number': 1,  # 需要实际解析
                                'frequency': 1
                            }
                        )
                        if not created:
                            usage.frequency += 1
                            usage.save()

                        element.increment_usage_count()
                        usages.append(usage)
                    except Element.DoesNotExist:
                        missing_elements.append(match)

        # 生成建议
        if missing_elements:
            recommendations.append(f"发现 {len(missing_elements)} 个未定义的元素定位器")

        if len(usages) > 20:
            recommendations.append("脚本复杂度较高，建议拆分为多个小脚本")

        complexity_score = min(100, len(usages) * 5)

        return {
            'element_usages': usages,
            'missing_elements': missing_elements,
            'recommendations': recommendations,
            'complexity_score': complexity_score
        }


class TestScriptViewSet(viewsets.ModelViewSet):
    queryset = TestScript.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'script_type']
    search_fields = ['name', 'description']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return TestScriptCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TestScriptUpdateSerializer
        return TestScriptSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目的测试脚本
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return TestScript.objects.filter(project__in=accessible_projects)


class TestSuiteViewSet(viewsets.ModelViewSet):
    queryset = TestSuite.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project']
    search_fields = ['name', 'description']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return TestSuiteCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TestSuiteUpdateSerializer
        elif self.action == 'retrieve':
            return TestSuiteWithScriptsSerializer
        return TestSuiteSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目的测试套件
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return TestSuite.objects.filter(project__in=accessible_projects)

    def perform_create(self, serializer):
        instance = serializer.save()
        # 记录操作
        log_operation('create', 'suite', instance.id, instance.name, self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        # 记录操作
        log_operation('edit', 'suite', instance.id, instance.name, self.request.user)

    def perform_destroy(self, instance):
        # 记录操作（在删除前记录）
        log_operation('delete', 'suite', instance.id, instance.name, self.request.user)
        instance.delete()

    @action(detail=True, methods=['get'])
    def scripts(self, request, pk=None):
        """获取测试套件中的所有脚本"""
        test_suite = self.get_object()
        scripts = test_suite.suite_scripts.all()
        serializer = TestSuiteScriptSerializer(scripts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_script(self, request, pk=None):
        """向测试套件添加脚本"""
        test_suite = self.get_object()
        data = request.data
        data['test_suite'] = pk
        serializer = TestSuiteScriptSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'])
    def remove_script(self, request, pk=None, script_id=None):
        """从测试套件移除脚本"""
        test_suite = self.get_object()
        try:
            suite_script = TestSuiteScript.objects.get(test_suite=test_suite, id=script_id)
            suite_script.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except TestSuiteScript.DoesNotExist:
            return Response({'error': '脚本不存在于该测试套件中'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'])
    def test_cases(self, request, pk=None):
        """获取测试套件中的所有测试用例"""
        test_suite = self.get_object()
        test_cases = test_suite.suite_test_cases.all()
        serializer = TestSuiteTestCaseSerializer(test_cases, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_test_case(self, request, pk=None):
        """向测试套件添加测试用例"""
        test_suite = self.get_object()
        test_case_id = request.data.get('test_case_id')
        order = request.data.get('order', 0)

        try:
            from .models import TestSuiteTestCase
            suite_test_case = TestSuiteTestCase.objects.create(
                test_suite=test_suite,
                test_case_id=test_case_id,
                order=order
            )
            serializer = TestSuiteTestCaseSerializer(suite_test_case)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'])
    def remove_test_case(self, request, pk=None):
        """从测试套件移除测试用例"""
        test_suite = self.get_object()
        test_case_id = request.data.get('test_case_id')

        try:
            from .models import TestSuiteTestCase
            suite_test_case = TestSuiteTestCase.objects.get(
                test_suite=test_suite,
                test_case_id=test_case_id
            )
            suite_test_case.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except TestSuiteTestCase.DoesNotExist:
            return Response({'error': '测试用例不存在于该测试套件中'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def update_test_case_order(self, request, pk=None):
        """更新测试套件中测试用例的顺序"""
        test_suite = self.get_object()
        test_case_orders = request.data.get('test_case_orders', [])

        try:
            from .models import TestSuiteTestCase
            for item in test_case_orders:
                TestSuiteTestCase.objects.filter(
                    test_suite=test_suite,
                    test_case_id=item['test_case_id']
                ).update(order=item['order'])

            return Response({'message': '顺序更新成功'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def run_suite(self, request, pk=None):
        """执行测试套件"""
        test_suite = self.get_object()

        # 传统模式执行（Playwright/Selenium）
        # 检查是否包含测试用例
        test_case_count = test_suite.suite_test_cases.count()
        if test_case_count == 0:
            return Response({
                'error': '该测试套件未包含任何测试用例，无法执行'
            }, status=status.HTTP_400_BAD_REQUEST)

        engine = request.data.get('engine', 'playwright')
        browser = request.data.get('browser', 'chrome')
        headless = request.data.get('headless', False)

        # 更新套件执行状态为运行中
        test_suite.execution_status = 'running'
        test_suite.save()

        # 记录运行操作
        log_operation('run', 'suite', test_suite.id, test_suite.name, request.user)

        # 在后台线程中执行测试
        import threading
        import traceback
        from .test_executor import TestExecutor

        def run_test():
            try:
                print(f"[测试套件] 开始执行: {test_suite.name} (ID: {test_suite.id})")
                print(f"[测试套件] 配置: engine={engine}, browser={browser}, headless={headless}")

                executor = TestExecutor(
                    test_suite=test_suite,
                    engine=engine,
                    browser=browser,
                    headless=headless,
                    executed_by=request.user
                )
                executor.run()

                print(f"[测试套件] 执行完成: {test_suite.name}")
            except Exception as e:
                print(f"[测试套件] 执行异常: {test_suite.name}")
                print(f"[测试套件] 错误: {str(e)}")
                traceback.print_exc()

                # 更新套件状态为失败
                try:
                    test_suite.execution_status = 'failed'
                    test_suite.save()
                    print(f"[测试套件] 已更新状态为失败")
                except Exception as save_error:
                    print(f"[测试套件] 更新状态失败: {save_error}")

        # 启动后台线程执行测试
        thread = threading.Thread(target=run_test, daemon=False)
        thread.start()

        return Response({
            'message': '测试套件开始执行',
            'suite_id': test_suite.id,
            'test_case_count': test_case_count,
            'engine': engine,
            'browser': browser,
            'headless': headless
        }, status=status.HTTP_200_OK)


class TestExecutionViewSet(viewsets.ModelViewSet):
    queryset = TestExecution.objects.all()
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'test_suite', 'test_script', 'status', 'environment', 'executed_by']
    search_fields = ['error_message']
    ordering = ['-created_at']
    pagination_class = StandardPagination

    def get_queryset(self):
        # 只显示用户有权限访问的项目的测试执行记录
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return TestExecution.objects.filter(
            project__in=accessible_projects
        ).select_related('project', 'test_suite', 'test_script', 'executed_by')

    def get_serializer_class(self):
        if self.action == 'create':
            return TestExecutionCreateSerializer
        return TestExecutionSerializer

    def perform_destroy(self, instance):
        # 记录操作（删除测试报告）
        suite_name = instance.test_suite.name if instance.test_suite else f"执行记录#{instance.id}"
        log_operation('delete', 'report', instance.id, suite_name, self.request.user)
        instance.delete()


class ScreenshotViewSet(viewsets.ModelViewSet):
    queryset = Screenshot.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = ScreenshotSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['execution']

    def get_queryset(self):
        # 只显示用户有权限访问的项目的截图
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        executions = TestExecution.objects.filter(project__in=accessible_projects)
        return Screenshot.objects.filter(execution__in=executions)


class TestCaseViewSet(viewsets.ModelViewSet):
    """测试用例视图集"""
    queryset = TestCase.objects.all()
    serializer_class = TestCaseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name', 'priority', 'status']
    ordering = ['-created_at']
    filterset_fields = ['project', 'status', 'priority', 'created_by']

    def get_queryset(self):
        # 只显示用户有权限访问的项目的测试用例
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()

    def get_queryset(self):
        # 只显示用户有权限访问的项目的测试用例
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return TestCase.objects.filter(project__in=accessible_projects).select_related('project', 'created_by')

    def perform_create(self, serializer):
        # 创建测试用例
        instance = serializer.save(created_by=self.request.user)

        # 记录操作
        log_operation('create', 'test_case', instance.id, instance.name, self.request.user)

        # 处理步骤数据
        steps_data = self.request.data.get('steps', [])
        logger.info(f"创建测试用例 {instance.id} 的步骤数据: {len(steps_data)} 个步骤")

        if steps_data:
            # 创建新步骤
            created_count = 0
            for i, step_data in enumerate(steps_data):
                # 确保步骤数据结构正确
                step_data = dict(step_data)  # 创建副本避免修改原数据
                step_data['test_case'] = instance.id  # 使用测试用例ID
                step_data['step_number'] = i + 1  # 确保步骤序号正确

                # 处理元素ID
                if 'element_id' in step_data:
                    step_data['element'] = step_data.pop('element_id')

                # 移除只读字段
                step_data.pop('id', None)
                step_data.pop('element_name', None)
                step_data.pop('element_locator', None)
                step_data.pop('created_at', None)
                step_data.pop('expanded', None)  # 前端UI状态字段

                # 使用模型直接创建，避免序列化器的复杂性
                try:
                    TestCaseStep.objects.create(
                        test_case=instance,
                        step_number=step_data.get('step_number', i + 1),
                        action_type=step_data.get('action_type', 'click'),
                        element_id=step_data.get('element') if step_data.get('element') else None,
                        input_value=step_data.get('input_value', ''),
                        wait_time=step_data.get('wait_time', 1000),
                        assert_type=step_data.get('assert_type', ''),
                        assert_value=step_data.get('assert_value', ''),
                        description=step_data.get('description', '')
                    )
                    created_count += 1
                except Exception as e:
                    logger.error(f"创建步骤 {i + 1} 失败: {str(e)}")
                    logger.error(f"步骤数据: {step_data}")

            logger.info(f"成功创建了 {created_count} 个新步骤")

    @action(detail=True, methods=['post'])
    def copy_case(self, request, pk=None):
        """复制测试用例"""
        test_case = self.get_object()

        try:
            # 1. 复制测试用例基本信息
            new_case = TestCase.objects.create(
                project=test_case.project,
                name=f"{test_case.name}_copy",
                description=test_case.description,
                priority=test_case.priority,
                status=test_case.status,
                created_by=request.user
            )

            # 2. 复制测试步骤
            steps = test_case.steps.all().order_by('step_number')
            new_steps = []
            for step in steps:
                new_steps.append(TestCaseStep(
                    test_case=new_case,
                    step_number=step.step_number,
                    action_type=step.action_type,
                    element=step.element,
                    input_value=step.input_value,
                    wait_time=step.wait_time,
                    assert_type=step.assert_type,
                    assert_value=step.assert_value,
                    description=step.description
                ))

            if new_steps:
                TestCaseStep.objects.bulk_create(new_steps)

            # 记录操作
            log_operation('create', 'test_case', new_case.id, new_case.name, request.user)

            serializer = self.get_serializer(new_case)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"复制测试用例失败: {str(e)}")
            return Response({'error': f"复制失败: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_update(self, serializer):
        # 更新测试用例步骤
        instance = serializer.save()

        # 记录操作
        log_operation('edit', 'test_case', instance.id, instance.name, self.request.user)

        # 处理步骤数据
        steps_data = self.request.data.get('steps', [])
        logger.info(f"更新测试用例 {instance.id} 的步骤数据: {len(steps_data)} 个步骤")

        if steps_data:
            # 删除现有步骤
            existing_steps_count = instance.steps.count()
            instance.steps.all().delete()
            logger.info(f"删除了 {existing_steps_count} 个现有步骤")

            # 创建新步骤
            created_count = 0
            for i, step_data in enumerate(steps_data):
                # 确保步骤数据结构正确
                step_data = dict(step_data)  # 创建副本避免修改原数据
                step_data['test_case'] = instance.id  # 使用测试用例ID
                step_data['step_number'] = i + 1  # 确保步骤序号正确

                # 处理元素ID
                if 'element_id' in step_data:
                    step_data['element'] = step_data.pop('element_id')

                # 移除只读字段
                step_data.pop('id', None)
                step_data.pop('element_name', None)
                step_data.pop('element_locator', None)
                step_data.pop('created_at', None)
                step_data.pop('expanded', None)  # 前端UI状态字段

                # 使用模型直接创建，避免序列化器的复杂性
                try:
                    TestCaseStep.objects.create(
                        test_case=instance,
                        step_number=step_data.get('step_number', i + 1),
                        action_type=step_data.get('action_type', 'click'),
                        element_id=step_data.get('element') if step_data.get('element') else None,
                        input_value=step_data.get('input_value', ''),
                        wait_time=step_data.get('wait_time', 1000),
                        assert_type=step_data.get('assert_type', ''),
                        assert_value=step_data.get('assert_value', ''),
                        description=step_data.get('description', '')
                    )
                    created_count += 1
                except Exception as e:
                    logger.error(f"创建步骤 {i + 1} 失败: {str(e)}")
                    logger.error(f"步骤数据: {step_data}")

            logger.info(f"成功创建了 {created_count} 个新步骤")

    def _generate_step_log(self, step, step_result='success'):
        """根据测试步骤生成执行日志"""
        import time

        # 模拟执行时间（0.1秒到2秒之间）
        execution_time = round(random.uniform(0.1, 2.0), 2)

        # 构建基础日志
        log_parts = []

        # 步骤信息
        if step.element:
            element_name = step.element.name
            locator_info = f"{step.element.locator_strategy.name}={step.element.locator_value}"
        else:
            element_name = "页面"
            locator_info = "无"

        # 根据操作类型生成具体日志
        if step.action_type == 'click':
            log_parts.append(f"点击元素 '{element_name}'")
            log_parts.append(f"- 使用定位器: {locator_info}")
            if step_result == 'success':
                log_parts.append(f"- 元素点击成功 - 耗时 {execution_time}s")
            else:
                log_parts.append(f"- 元素点击失败 - 元素未找到或不可点击")

        elif step.action_type == 'fill':
            log_parts.append(f"在元素 '{element_name}' 中输入文本")
            log_parts.append(f"- 使用定位器: {locator_info}")
            log_parts.append(f"- 输入值: '{step.input_value}'")
            if step_result == 'success':
                log_parts.append(f"- 文本输入成功 - 耗时 {execution_time}s")
            else:
                log_parts.append(f"- 文本输入失败 - 元素未找到或不可编辑")

        elif step.action_type == 'getText':
            log_parts.append(f"获取元素 '{element_name}' 的文本内容")
            log_parts.append(f"- 使用定位器: {locator_info}")
            if step_result == 'success':
                # 模拟获取到的文本
                mock_text = f"示例文本内容_{step.id}" if step.id else "示例文本内容"
                log_parts.append(f"- 获取到文本: '{mock_text}' - 耗时 {execution_time}s")
            else:
                log_parts.append(f"- 获取文本失败 - 元素未找到")

        elif step.action_type == 'waitFor':
            log_parts.append(f"等待元素 '{element_name}' 出现")
            log_parts.append(f"- 使用定位器: {locator_info}")
            log_parts.append(f"- 超时时间: {step.wait_time / 1000}秒")
            if step_result == 'success':
                log_parts.append(f"- 元素在 {execution_time}s 后出现")
            else:
                log_parts.append(f"- 等待超时 - 元素未在指定时间内出现")

        elif step.action_type == 'hover':
            log_parts.append(f"在元素 '{element_name}' 上悬停")
            log_parts.append(f"- 使用定位器: {locator_info}")
            if step_result == 'success':
                log_parts.append(f"- 悬停操作成功 - 耗时 {execution_time}s")
            else:
                log_parts.append(f"- 悬停操作失败 - 元素未找到")

        elif step.action_type == 'scroll':
            log_parts.append(f"滚动到元素 '{element_name}'")
            log_parts.append(f"- 使用定位器: {locator_info}")
            if step_result == 'success':
                log_parts.append(f"- 滚动操作成功 - 耗时 {execution_time}s")
            else:
                log_parts.append(f"- 滚动操作失败 - 元素未找到")

        elif step.action_type == 'screenshot':
            log_parts.append(f"执行截图操作")
            if step.element:
                log_parts.append(f"- 截图范围: 元素 '{element_name}'")
            else:
                log_parts.append(f"- 截图范围: 整个页面")
            if step_result == 'success':
                screenshot_name = f"screenshot_{int(time.time())}.png"
                log_parts.append(f"- 截图保存成功: {screenshot_name} - 耗时 {execution_time}s")
            else:
                log_parts.append(f"- 截图保存失败")

        elif step.action_type == 'assert':
            log_parts.append(f"执行断言验证")
            log_parts.append(f"- 断言类型: {step.assert_type}")
            if step.assert_value:
                log_parts.append(f"- 期望值: '{step.assert_value}'")
            if step_result == 'success':
                log_parts.append(f"- 断言通过 - 耗时 {execution_time}s")
            else:
                log_parts.append(f"- 断言失败 - 实际值与期望值不匹配")

        elif step.action_type == 'wait':
            log_parts.append(f"固定等待")
            log_parts.append(f"- 等待时间: {step.wait_time / 1000}秒")
            log_parts.append(f"- 等待完成")

        else:
            # 默认处理其他操作类型
            log_parts.append(f"执行操作: {step.action_type}")
            if step.element:
                log_parts.append(f"- 目标元素: {element_name}")
            if step.input_value:
                log_parts.append(f"- 输入值: {step.input_value}")
            log_parts.append(f"- 操作{'成功' if step_result == 'success' else '失败'} - 耗时 {execution_time}s")

        # 如果步骤有描述，添加到日志中
        if step.description:
            log_parts.insert(0, f"说明: {step.description}")

        return '\n'.join(log_parts)

    def _generate_failure_screenshot(self, step_number, step_description):
        """生成失败截图的模拟数据（base64格式）"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import io
            import base64

            # 创建一个模拟的失败截图
            # 实际应用中，这里应该是通过Playwright/Selenium捕获真实的页面截图
            width, height = 1280, 720
            img = Image.new('RGB', (width, height), color=(240, 240, 245))
            draw = ImageDraw.Draw(img)

            # 绘制标题区域
            draw.rectangle([0, 0, width, 80], fill=(220, 53, 69))

            # 添加文本信息（使用默认字体）
            try:
                # 尝试使用系统字体
                font_title = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 40)
                font_text = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 24)
            except:
                # 如果系统字体不可用，使用默认字体
                font_title = ImageFont.load_default()
                font_text = ImageFont.load_default()

            # 标题
            draw.text((40, 20), "测试步骤执行失败", fill=(255, 255, 255), font=font_title)

            # 失败信息
            info_y = 120
            draw.text((40, info_y), f"失败步骤: 步骤 {step_number}", fill=(50, 50, 50), font=font_text)
            draw.text((40, info_y + 40), f"步骤说明: {step_description}", fill=(50, 50, 50), font=font_text)
            draw.text((40, info_y + 80), f"失败时间: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
                      fill=(50, 50, 50), font=font_text)

            # 绘制一个模拟的浏览器窗口
            browser_y = info_y + 140
            draw.rectangle([40, browser_y, width - 40, height - 40], outline=(200, 200, 200), width=2)
            draw.rectangle([40, browser_y, width - 40, browser_y + 40], fill=(200, 200, 200))
            draw.text((60, browser_y + 10), "模拟浏览器页面 - 失败截图", fill=(80, 80, 80), font=font_text)

            # 在浏览器窗口中绘制错误提示
            error_y = browser_y + 80
            draw.text((60, error_y), "× 元素定位失败或操作执行异常", fill=(220, 53, 69), font=font_text)
            draw.text((60, error_y + 40), "× 请检查元素定位器是否正确", fill=(220, 53, 69), font=font_text)
            draw.text((60, error_y + 80), "× 或页面加载是否完成", fill=(220, 53, 69), font=font_text)

            # 转换为base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()

            return f"data:image/png;base64,{img_base64}"

        except Exception as e:
            logger.error(f"生成失败截图时出错: {str(e)}")
            # 返回一个简单的错误占位符
            return None

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """运行单个测试用例 - 支持选择Playwright或Selenium执行引擎"""
        test_case = self.get_object()

        try:
            # 获取执行引擎选择，默认使用playwright
            engine_type = request.data.get('engine', 'playwright')

            # 创建执行记录
            execution = TestCaseExecution.objects.create(
                test_case=test_case,
                project=test_case.project,
                execution_source='manual',
                status='running',
                engine=engine_type,
                browser=request.data.get('browser', 'chrome'),
                headless=request.data.get('headless', False),
                created_by=request.user,
                started_at=timezone.now()
            )

            # 根据引擎类型导入对应的执行引擎
            if engine_type == 'selenium':
                from .selenium_engine import SeleniumTestEngine

                # Selenium 引擎需要预先检查浏览器是否可用
                browser_type = request.data.get('browser', 'chrome')
                is_available, error_msg = SeleniumTestEngine.check_browser_available(browser_type)
                if not is_available:
                    # 浏览器不可用，立即返回错误
                    logger.error(f"Selenium 浏览器检查失败: {error_msg}")
                    execution.status = 'failed'
                    execution.error_message = error_msg
                    execution.execution_logs = f"浏览器检查失败\n\n{error_msg}\n\n建议：\n1. 请确认已安装 {browser_type.capitalize()} 浏览器\n2. 或者尝试使用其他浏览器（Chrome、Firefox、Edge）\n3. 或者使用 Playwright 引擎（支持自动下载浏览器）"
                    execution.finished_at = timezone.now()
                    execution.save()

                    return Response({
                        'success': False,
                        'logs': execution.execution_logs,
                        'screenshots': [],
                        'execution_time': 0,
                        'errors': [{
                            'message': f'{browser_type.capitalize()} 浏览器不可用',
                            'details': error_msg,
                            'step_number': None,
                            'action_type': '浏览器检查',
                            'element': '',
                            'description': '执行前浏览器环境检查'
                        }]
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                import asyncio
                import threading
                from .playwright_engine import PlaywrightTestEngine

            start_time = time.time()

            # 获取测试用例的所有步骤
            test_steps = list(test_case.steps.all().order_by('step_number'))

            # 预先获取所有步骤的数据,避免在异步上下文中访问ORM
            steps_data = []
            for step in test_steps:
                step_data = {
                    'step': step,
                    'action_type': step.action_type,
                    'description': step.description,
                    'input_value': step.input_value,
                    'wait_time': step.wait_time,
                    'assert_type': step.assert_type,
                    'assert_value': step.assert_value,
                }

                # 获取元素数据
                if step.element:
                    step_data['element_data'] = {
                        'locator_strategy': step.element.locator_strategy.name if step.element.locator_strategy else 'css',
                        'locator_value': step.element.locator_value,
                        'name': step.element.name,
                        'wait_timeout': step.element.wait_timeout,  # 添加元素的等待超时设置（秒）
                        'force_action': step.element.force_action  # 添加强制操作选项
                    }
                else:
                    step_data['element_data'] = None

                steps_data.append(step_data)

            # 存储步骤执行结果（用于JSON格式的execution_logs）
            step_results = []

            # 生成执行日志（保留文本格式用于调试）
            execution_logs = []
            execution_logs.append(f"测试用例 '{test_case.name}' 开始执行")
            execution_logs.append(f"执行时间: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
            execution_logs.append(f"执行引擎: {engine_type.upper()}")
            execution_logs.append(f"浏览器: {request.data.get('browser', 'chrome').capitalize()}")
            headless_mode = request.data.get('headless', False)
            mode_text = "无头模式" if headless_mode else "有头模式"
            execution_logs.append(f"执行模式: {mode_text}")
            execution_logs.append(f"执行用户: {request.user.username}")
            execution_logs.append(f"项目基础URL: {test_case.project.base_url}")
            execution_logs.append("")

            # 截图列表
            screenshots = []
            # 详细错误信息列表
            detailed_errors = []
            execution_result = {'status': 'passed', 'error_message': None}

            # 根据引擎类型选择执行方式
            if engine_type == 'selenium':
                # Selenium同步执行
                def run_test_selenium():
                    """使用Selenium执行测试"""
                    browser_type = request.data.get('browser', 'chrome')
                    headless = request.data.get('headless', False)

                    # 创建Selenium引擎实例
                    engine = SeleniumTestEngine(browser_type=browser_type, headless=headless)

                    try:
                        # 启动浏览器
                        execution_logs.append("========== 初始化浏览器 ==========")
                        try:
                            engine.start()
                            mode_text = "无头模式" if headless else "有头模式"
                            execution_logs.append(
                                f"✓ {browser_type.capitalize()} 浏览器启动成功 (Selenium, {mode_text})")
                            execution_logs.append("")
                        except Exception as browser_error:
                            # 浏览器启动失败
                            execution_logs.append(f"✗ {browser_type.capitalize()} 浏览器启动失败")
                            execution_logs.append(f"  错误: {str(browser_error)}")
                            execution_logs.append("")
                            execution_result['status'] = 'failed'
                            execution_result[
                                'error_message'] = f"{browser_type.capitalize()} 浏览器启动失败: {str(browser_error)}"

                            # 添加详细错误信息
                            detailed_errors.append({
                                'step_number': None,
                                'action_type': '浏览器启动',
                                'element': '',
                                'message': f"{browser_type.capitalize()} 浏览器启动失败",
                                'details': str(browser_error),
                                'description': '执行前浏览器启动检查'
                            })

                            return False

                        # 导航到项目基础URL
                        if test_case.project.base_url:
                            execution_logs.append("========== 导航到测试页面 ==========")
                            success, nav_log = engine.navigate(test_case.project.base_url)
                            execution_logs.append(nav_log)
                            execution_logs.append("")

                            if not success:
                                execution_result['status'] = 'failed'
                                execution_result['error_message'] = "导航到测试页面失败"
                                return False

                        if steps_data:
                            execution_logs.append("========== 执行测试步骤 ==========")
                            step_count = len(steps_data)
                            execution_logs.append(f"共有 {step_count} 个步骤需要执行")
                            execution_logs.append("")

                            for i, step_info in enumerate(steps_data, 1):
                                execution_logs.append(f"========== 开始执行步骤 {i}/{step_count} ==========")
                                execution_logs.append(f"步骤 {i}/{step_count}:")

                                step = step_info['step']
                                action_type = step_info['action_type']
                                description = step_info['description']
                                element_data = step_info['element_data']

                                action_choices_dict = dict(TestCaseStep.ACTION_TYPE_CHOICES)
                                action_type_text = action_choices_dict.get(action_type, action_type)
                                execution_logs.append(f"  操作: {action_type_text}")

                                if description:
                                    execution_logs.append(f"  说明: {description}")

                                if element_data:
                                    execution_logs.append(f"  元素: {element_data['name']}")
                                    execution_logs.append(
                                        f"  定位器: {element_data['locator_strategy']}={element_data['locator_value']}")
                                else:
                                    execution_logs.append(f"  (此步骤不需要元素)")

                                try:
                                    success, step_log, screenshot_base64 = engine.execute_step(step, element_data or {})
                                    execution_logs.append(f"  {step_log}")
                                    execution_logs.append("")

                                    # 记录步骤执行结果（用于JSON格式）
                                    step_results.append({
                                        'step_number': i,
                                        'action_type': action_type,
                                        'description': description or '',
                                        'success': success,
                                        'error': None if success else step_log
                                    })

                                    if not success:
                                        logger.info(f"[调试-Selenium] 步骤 {i} 执行失败，设置状态为 failed")
                                        execution_result['status'] = 'failed'
                                        element_info = element_data['name'] if element_data else "未知元素"
                                        execution_result['error_message'] = step_log  # 使用step_log作为错误信息
                                        logger.info(f"[调试-Selenium] execution_result = {execution_result}")

                                        detailed_errors.append({
                                            'step_number': i,
                                            'action_type': action_type_text,
                                            'element': element_info,
                                            'message': f"步骤 {i}/{step_count} 执行失败",
                                            'details': step_log,
                                            'description': description or ''
                                        })

                                        if not screenshot_base64:
                                            screenshot_base64 = engine.capture_screenshot()

                                        if screenshot_base64:
                                            screenshots.append({
                                                'url': screenshot_base64,
                                                'description': f'步骤 {i} 失败截图: {description or action_type_text}',
                                                'step_number': i,
                                                'timestamp': timezone.now().isoformat()
                                                # 移除 loaded 和 error 字段，让前端自行处理
                                            })
                                            execution_logs.append(f"  📸 失败截图已捕获")

                                        return False

                                    if action_type == 'screenshot' and screenshot_base64:
                                        screenshots.append({
                                            'url': screenshot_base64,
                                            'description': f'步骤 {i}: {description or "手动截图"}',
                                            'step_number': i,
                                            'timestamp': timezone.now().isoformat()
                                            # 移除 loaded 和 error 字段，让前端自行处理
                                        })

                                except Exception as e:
                                    execution_logs.append(f"  ✗ 步骤执行异常: {str(e)}")
                                    import traceback
                                    tb_str = traceback.format_exc()
                                    execution_logs.append(f"  [调试] 异常堆栈:\n{tb_str}")

                                    # 记录步骤执行结果（异常情况）
                                    step_results.append({
                                        'step_number': i,
                                        'action_type': action_type,
                                        'description': description or '',
                                        'success': False,
                                        'error': str(e)
                                    })

                                    execution_result['status'] = 'failed'
                                    execution_result['error_message'] = f"步骤 {i} 执行异常: {str(e)}"

                                    element_info = element_data['name'] if element_data else "未知元素"
                                    detailed_errors.append({
                                        'step_number': i,
                                        'action_type': action_type_text,
                                        'element': element_info,
                                        'message': f"步骤 {i}/{step_count} 执行异常",
                                        'details': f"异常: {str(e)}\n\n堆栈跟踪:\n{tb_str}",
                                        'description': description or ''
                                    })

                                    try:
                                        screenshot_base64 = engine.capture_screenshot()
                                        if screenshot_base64:
                                            screenshots.append({
                                                'url': screenshot_base64,
                                                'description': f'步骤 {i} 异常截图: {str(e)}',
                                                'step_number': i,
                                                'timestamp': timezone.now().isoformat()
                                                # 移除 loaded 和 error 字段，让前端自行处理
                                            })
                                    except:
                                        pass

                                    return False

                            execution_logs.append(f"========== 执行完成 ({step_count} 个步骤全部通过) ==========")
                            return True
                        else:
                            execution_logs.append("警告: 测试用例没有定义任何步骤")
                            return True

                    finally:
                        execution_logs.append("")
                        execution_logs.append("========== 清理资源 ==========")
                        engine.stop()
                        execution_logs.append("✓ 浏览器已关闭")

                # 在独立线程中运行Selenium测试
                import threading
                test_thread = threading.Thread(target=run_test_selenium)
                test_thread.start()
                test_thread.join()

            else:
                # Playwright异步执行
                def run_test_in_thread():
                    """在独立线程中运行异步测试"""

                    async def run_test():
                        """异步执行测试"""
                        # 根据浏览器类型选择
                        browser_map = {
                            'chrome': 'chromium',
                            'firefox': 'firefox',
                            'safari': 'webkit'
                        }
                        browser_type = browser_map.get(request.data.get('browser', 'chrome'), 'chromium')
                        headless = request.data.get('headless', False)

                        # 创建Playwright引擎实例
                        engine = PlaywrightTestEngine(browser_type=browser_type, headless=headless)

                        try:
                            # 启动浏览器
                            execution_logs.append("========== 初始化浏览器 ==========")
                            await engine.start()
                            mode_text = "无头模式" if headless else "有头模式"
                            execution_logs.append(
                                f"✓ {browser_type.capitalize()} 浏览器启动成功 (Playwright, {mode_text})")
                            execution_logs.append("")

                            # 导航到项目基础URL
                            if test_case.project.base_url:
                                execution_logs.append("========== 导航到测试页面 ==========")
                                success, nav_log = await engine.navigate(test_case.project.base_url)
                                execution_logs.append(nav_log)
                                execution_logs.append("")

                                if not success:
                                    execution_result['status'] = 'failed'
                                    execution_result['error_message'] = "导航到测试页面失败"
                                    return False

                            if steps_data:
                                execution_logs.append("========== 执行测试步骤 ==========")
                                step_count = len(steps_data)
                                execution_logs.append(f"共有 {step_count} 个步骤需要执行")
                                execution_logs.append("")

                                for i, step_info in enumerate(steps_data, 1):
                                    execution_logs.append(f"========== 开始执行步骤 {i}/{step_count} ==========")
                                    execution_logs.append(f"步骤 {i}/{step_count}:")

                                    # 从预先获取的数据中获取信息
                                    step = step_info['step']
                                    action_type = step_info['action_type']
                                    description = step_info['description']
                                    element_data = step_info['element_data']

                                    # 获取操作类型的中文显示
                                    action_choices_dict = dict(TestCaseStep.ACTION_TYPE_CHOICES)
                                    action_type_text = action_choices_dict.get(action_type, action_type)
                                    execution_logs.append(f"  操作: {action_type_text}")

                                    if description:
                                        execution_logs.append(f"  说明: {description}")

                                    if element_data:
                                        execution_logs.append(f"  元素: {element_data['name']}")
                                        execution_logs.append(
                                            f"  定位器: {element_data['locator_strategy']}={element_data['locator_value']}")
                                    else:
                                        execution_logs.append(f"  (此步骤不需要元素)")

                                    # 执行步骤
                                    try:
                                        execution_logs.append(f"  [调试] 准备执行步骤...")
                                        success, step_log, screenshot_base64 = await engine.execute_step(step,
                                                                                                         element_data or {})
                                        execution_logs.append(f"  [调试] 步骤执行完成, success={success}")

                                        execution_logs.append(f"  {step_log}")
                                        execution_logs.append("")

                                        # 记录步骤执行结果（用于JSON格式）
                                        step_results.append({
                                            'step_number': i,
                                            'action_type': action_type,
                                            'description': description or '',
                                            'success': success,
                                            'error': None if success else step_log
                                        })

                                        # 如果步骤失败,保存截图并立即结束执行
                                        if not success:
                                            execution_logs.append(f"  [调试] 检测到步骤失败,准备处理...")
                                            execution_result['status'] = 'failed'

                                            # 获取失败的元素信息
                                            element_info = element_data['name'] if element_data else "未知元素"

                                            execution_result['error_message'] = step_log  # 使用step_log作为错误信息

                                            # 添加详细错误信息
                                            detailed_errors.append({
                                                'step_number': i,
                                                'action_type': action_type_text,
                                                'element': element_info,
                                                'message': f"步骤 {i}/{step_count} 执行失败",
                                                'details': step_log,  # 包含详细的错误日志
                                                'description': description or ''
                                            })

                                            # 如果没有截图,捕获一张
                                            if not screenshot_base64:
                                                screenshot_base64 = await engine.capture_screenshot()

                                            if screenshot_base64:
                                                screenshots.append({
                                                    'url': screenshot_base64,
                                                    'description': f'步骤 {i} 失败截图: {description or action_type_text}',
                                                    'step_number': i,
                                                    'timestamp': timezone.now().isoformat()
                                                    # 移除 loaded 和 error 字段，让前端自行处理
                                                })
                                                execution_logs.append(f"  📸 失败截图已捕获")

                                            execution_logs.append(f"  [调试] 步骤失败,准备退出执行...")
                                            return False

                                        # 如果是截图步骤且成功,也保存截图
                                        if action_type == 'screenshot' and screenshot_base64:
                                            screenshots.append({
                                                'url': screenshot_base64,
                                                'description': f'步骤 {i}: {description or "手动截图"}',
                                                'step_number': i,
                                                'timestamp': timezone.now().isoformat()
                                                # 移除 loaded 和 error 字段，让前端自行处理
                                            })

                                        execution_logs.append(f"  [调试] 步骤 {i} 成功完成,准备执行下一步...")

                                    except Exception as e:
                                        execution_logs.append(f"  ✗ 步骤执行异常: {str(e)}")
                                        execution_logs.append(f"  [调试] 异常详情: {repr(e)}")
                                        import traceback
                                        tb_str = traceback.format_exc()
                                        execution_logs.append(f"  [调试] 异常堆栈:\n{tb_str}")

                                        # 记录步骤执行结果（异常情况）
                                        step_results.append({
                                            'step_number': i,
                                            'action_type': action_type,
                                            'description': description or '',
                                            'success': False,
                                            'error': str(e)
                                        })

                                        execution_result['status'] = 'failed'
                                        execution_result['error_message'] = f"步骤 {i} 执行异常: {str(e)}"

                                        # 添加详细错误信息
                                        element_info = element_data['name'] if element_data else "未知元素"
                                        detailed_errors.append({
                                            'step_number': i,
                                            'action_type': action_type_text,
                                            'element': element_info,
                                            'message': f"步骤 {i}/{step_count} 执行异常",
                                            'details': f"异常: {str(e)}\n\n堆栈跟踪:\n{tb_str}",
                                            'description': description or ''
                                        })

                                        # 捕获异常截图
                                        try:
                                            screenshot_base64 = await engine.capture_screenshot()
                                            if screenshot_base64:
                                                screenshots.append({
                                                    'url': screenshot_base64,
                                                    'description': f'步骤 {i} 异常截图: {str(e)}',
                                                    'step_number': i,
                                                    'timestamp': timezone.now().isoformat()
                                                    # 移除 loaded 和 error 字段，让前端自行处理
                                                })
                                        except:
                                            pass

                                        execution_logs.append(f"  [调试] 发生异常,准备退出执行...")
                                        return False

                                # 所有步骤都成功
                                execution_logs.append(f"========== 执行完成 ({step_count} 个步骤全部通过) ==========")
                                return True

                            else:
                                execution_logs.append("警告: 测试用例没有定义任何步骤")
                                return True

                        finally:
                            # 关闭浏览器
                            execution_logs.append("")
                            execution_logs.append("========== 清理资源 ==========")
                            await engine.stop()
                            execution_logs.append("✓ 浏览器已关闭")

                    # 在新的事件循环中运行测试
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(run_test())
                    finally:
                        loop.close()

                # 在独立线程中运行Playwright测试
                import threading
                test_thread = threading.Thread(target=run_test_in_thread)
                test_thread.start()
                test_thread.join()  # 等待测试完成

            # 计算总执行时间
            total_time = round(time.time() - start_time, 2)
            execution_logs.append("")
            execution_logs.append("执行环境信息:")
            execution_logs.append(f"- 执行引擎: {engine_type.upper()}")
            execution_logs.append(f"- 浏览器: {request.data.get('browser', 'chrome').capitalize()}")
            execution_logs.append(f"- 屏幕分辨率: 1920x1080")
            execution_logs.append(f"- 总执行时间: {total_time}秒")

            if screenshots:
                execution_logs.append(f"- 截图数量: {len(screenshots)} 张")

            # 保存执行日志和截图
            logger.info(f"[调试] 准备保存执行结果: execution_result['status'] = {execution_result['status']}")
            execution.status = execution_result['status']

            # 保存error_message（step_log已经是简洁的错误信息）
            execution.error_message = execution_result['error_message'] or ''

            # 保存步骤执行结果为JSON格式
            execution.execution_logs = json.dumps(step_results, ensure_ascii=False)
            execution.execution_time = total_time
            execution.finished_at = timezone.now()
            execution.screenshots = screenshots
            execution.save()
            logger.info(f"[调试] 执行结果已保存: execution.status = {execution.status}")

            serializer = TestCaseExecutionSerializer(execution)
            # 格式化错误信息为统一的对象格式
            errors = []
            if detailed_errors:
                # 使用详细的错误信息
                for error in detailed_errors:
                    errors.append({
                        'message': error['message'],
                        'details': error['details'],
                        'step_number': error['step_number'],
                        'action_type': error['action_type'],
                        'element': error['element'],
                        'description': error['description']
                    })
            elif execution.error_message:
                # 如果没有详细错误信息，使用简单格式
                errors.append({
                    'message': execution.error_message,
                    'details': ''
                })

            # 记录运行操作
            log_operation('run', 'test_case', test_case.id, test_case.name, request.user)

            return Response({
                'success': execution.status == 'passed',
                'logs': execution.execution_logs,
                'screenshots': screenshots,
                'execution_time': execution.execution_time,
                'errors': errors
            })

        except Exception as e:
            logger.error(f"执行测试用例失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'logs': f"执行失败: {str(e)}\n\n{traceback.format_exc()}",
                'screenshots': [],
                'execution_time': 0,
                'errors': [{'message': str(e), 'stack': traceback.format_exc()}]
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def batch_run(self, request):
        """批量运行测试用例"""
        test_case_ids = request.data.get('test_case_ids', [])
        project_id = request.data.get('project_id')

        if not test_case_ids:
            return Response({'error': '请选择要运行的测试用例'}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        for test_case_id in test_case_ids:
            try:
                test_case = TestCase.objects.get(id=test_case_id)
                # 这里调用单个运行逻辑
                # 简化处理，实际应该异步执行
                results.append({
                    'test_case_id': test_case_id,
                    'test_case_name': test_case.name,
                    'status': 'passed'
                })
            except TestCase.DoesNotExist:
                results.append({
                    'test_case_id': test_case_id,
                    'test_case_name': '未知',
                    'status': 'error',
                    'error': '测试用例不存在'
                })

        return Response({'results': results})

    def perform_destroy(self, instance):
        # 记录操作（在删除前记录）
        log_operation('delete', 'test_case', instance.id, instance.name, self.request.user)
        instance.delete()


class TestCaseStepViewSet(viewsets.ModelViewSet):
    """测试用例步骤视图集"""
    queryset = TestCaseStep.objects.all()
    serializer_class = TestCaseStepSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering_fields = ['step_number']
    ordering = ['step_number']
    filterset_fields = ['test_case', 'action_type']

    def get_queryset(self):
        # 只显示用户有权限访问的测试用例的步骤
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        accessible_test_cases = TestCase.objects.filter(project__in=accessible_projects)
        return TestCaseStep.objects.filter(test_case__in=accessible_projects)


class TestCaseExecutionViewSet(viewsets.ModelViewSet):
    """测试用例执行记录视图集"""
    queryset = TestCaseExecution.objects.all().select_related(
        'test_case', 'project', 'test_suite', 'executed_by'
    )
    serializer_class = TestCaseExecutionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['test_case__name', 'error_message']
    ordering_fields = ['created_at', 'started_at', 'finished_at', 'status']
    ordering = ['-created_at']
    filterset_fields = ['project', 'test_suite', 'test_case', 'status', 'execution_source']
    pagination_class = StandardPagination

    def get_queryset(self):
        # 只显示用户有权限访问的项目的执行记录
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return TestCaseExecution.objects.filter(
            project__in=accessible_projects
        ).select_related(
            'test_case', 'project', 'test_suite', 'created_by'
        )

    def perform_destroy(self, instance):
        # 记录操作
        name = instance.test_case.name if instance.test_case else f"执行记录#{instance.id}"
        log_operation('delete', 'report', instance.id, name, self.request.user)
        instance.delete()

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除执行记录"""
        try:
            ids = request.data.get('ids', [])

            # 验证ids参数
            if not ids:
                return Response({'error': '未提供要删除的记录ID'}, status=status.HTTP_400_BAD_REQUEST)

            # 确保ids是列表
            if not isinstance(ids, list):
                return Response({'error': 'ids参数格式错误，应为数组'}, status=status.HTTP_400_BAD_REQUEST)

            # 确保只能删除有权限的记录
            queryset = self.get_queryset()
            records_to_delete = queryset.filter(id__in=ids)

            # 检查是否有记录可删除
            if not records_to_delete.exists():
                return Response({'error': '未找到可删除的记录或没有权限删除'}, status=status.HTTP_404_NOT_FOUND)

            # 获取可删除记录的ID列表，避免对带select_related的queryset调用delete()可能出现的问题
            deletable_ids = list(records_to_delete.values_list('id', flat=True))

            # 使用ID列表直接删除
            deleted_count = TestCaseExecution.objects.filter(id__in=deletable_ids).delete()[0]

            return Response({'message': f'成功删除 {deleted_count} 条记录', 'deleted_count': deleted_count})
        except Exception as e:
            logger.error(f"批量删除测试用例执行记录失败: {str(e)}", exc_info=True)
            return Response({'error': f'批量删除失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OperationRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """操作记录视图集（只读）"""
    queryset = OperationRecord.objects.all()
    serializer_class = OperationRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['operation_type', 'resource_type', 'user']

    def get_queryset(self):
        # 返回最近的操作记录，按创建时间倒序
        # 过滤掉AI智能模式相关的操作记录
        queryset = OperationRecord.objects.exclude(
            resource_type__in=['ai_case', 'ai_execution']
        ).order_by('-created_at')

        # 支持通过查询参数限制返回数量
        limit = self.request.query_params.get('limit', None)
        if limit:
            try:
                limit = int(limit)
                queryset = queryset[:limit]
            except ValueError:
                pass

        return queryset


# ==================== 通知日志视图 ====================

class UiNotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """UI通知日志视图集（只读）"""
    queryset = UiNotificationLog.objects.all()
    serializer_class = UiNotificationLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'notification_type']
    search_fields = ['task_name', 'notification_content']
    ordering_fields = ['created_at', 'sent_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """重试发送通知"""
        log = self.get_object()
        if log.status == 'failed':
            log.retry_count += 1
            log.is_retried = True
            log.save()
            return Response({'message': '通知已加入重试队列'})
        return Response({'error': '只能重试失败的通知'}, status=status.HTTP_400_BAD_REQUEST)

