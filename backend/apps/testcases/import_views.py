import os
from django.http import FileResponse, HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_q.tasks import async_task
import openpyxl
from openpyxl.styles import Font, PatternFill

from .models import TestCaseImportRecord
from .serializers import TestCaseImportRecordSerializer
from apps.projects.models import Project

class TestCaseImportTemplateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "测试用例导入模板"

        # 去掉 '用例描述' 和 '状态'，增加 '关联版本'
        headers = ['用例标题', '前置条件', '操作步骤', '预期结果', '优先级', '测试类型', '关联版本']
        ws.append(headers)

        # Style headers
        header_fill = PatternFill(start_color="F5F5F5", end_color="F5F5F5", fill_type="solid")
        header_font = Font(bold=True)
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = 20

        # Sample data
        sample_data = ['登录成功验证', '账号已注册', '1.输入账号\n2.输入密码\n3.点击登录', '登录成功，跳转首页', '高', '功能测试', 'v1.0.0,v1.1.0']
        ws.append(sample_data)

        # Save to response
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="testcase_import_template.xlsx"'
        wb.save(response)
        return response

class TestCaseImportUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        project_id = request.data.get('project_id')

        if not file_obj:
            return Response({'error': '未提供文件'}, status=status.HTTP_400_BAD_REQUEST)
        if not project_id:
            return Response({'error': '未提供项目ID'}, status=status.HTTP_400_BAD_REQUEST)

        # Check project permissions
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': '项目不存在或无权限'}, status=status.HTTP_404_NOT_FOUND)

        # Create import record
        record = TestCaseImportRecord.objects.create(
            project=project,
            file_name=file_obj.name,
            file=file_obj,
            created_by=request.user,
            status='pending'
        )

        # Trigger async task
        task_id = async_task('apps.testcases.tasks.import_tasks.process_test_case_import', record.id)
        record.task_id = task_id
        record.save(update_fields=['task_id'])

        return Response({
            'message': '文件已上传，正在后台处理',
            'record_id': record.id,
            'task_id': task_id
        }, status=status.HTTP_201_CREATED)

class TestCaseImportRecordListView(generics.ListAPIView):
    serializer_class = TestCaseImportRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_id = self.request.query_params.get('project_id')
        queryset = TestCaseImportRecord.objects.all()
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset
