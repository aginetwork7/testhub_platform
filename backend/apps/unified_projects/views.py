from rest_framework import generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import MetaProject, MetaProjectMember, ProjectModule
from .serializers import (
    MetaProjectListSerializer,
    MetaProjectDetailSerializer,
    MetaProjectCreateSerializer,
    MetaProjectUpdateSerializer,
    MetaProjectMemberSerializer,
    ProjectModuleSerializer,
    ProjectModuleCreateSerializer
)


class IsOwnerOrMember(permissions.BasePermission):
    """只有项目所有者或成员可以访问"""

    def has_object_permission(self, request, view, obj):
        if request.user == obj.owner:
            return True
        return obj.members.filter(user=request.user).exists()


class MetaProjectListView(generics.ListCreateAPIView):
    """元项目列表创建"""

    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return MetaProject.objects.filter(
            models.Q(owner=user) | models.Q(members__user=user)
        ).distinct()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MetaProjectCreateSerializer
        return MetaProjectListSerializer


class MetaProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    """元项目详情"""

    permission_classes = [permissions.IsAuthenticated, IsOwnerOrMember]
    serializer_class = MetaProjectDetailSerializer

    def get_queryset(self):
        user = self.request.user
        return MetaProject.objects.filter(
            models.Q(owner=user) | models.Q(members__user=user)
        ).distinct()

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return MetaProjectUpdateSerializer
        return MetaProjectDetailSerializer

    def perform_destroy(self, instance):
        """删除元项目时同步删除子项目"""
        for module in instance.modules.all():
            project = module.get_project()
            if project:
                project.delete()
        instance.delete()


class MetaProjectModulesView(generics.GenericAPIView):
    """元项目模块管理"""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProjectModuleCreateSerializer

    def get(self, request, pk):
        """获取项目的所有模块"""
        try:
            project = MetaProject.objects.get(id=pk)
        except MetaProject.DoesNotExist:
            return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

        modules = project.modules.all()
        serializer = ProjectModuleSerializer(modules, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        """为项目添加模块"""
        try:
            project = MetaProject.objects.get(id=pk)
        except MetaProject.DoesNotExist:
            return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        module_type = serializer.validated_data['module_type']

        if project.modules.filter(module_type=module_type).exists():
            return Response(
                {'error': f'该项目已存在{module_type}模块'},
                status=status.HTTP_400_BAD_REQUEST
            )

        module = serializer.save(meta_project=project)
        return Response(ProjectModuleSerializer(module).data, status=status.HTTP_201_CREATED)


class ProjectModuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """项目模块详情"""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProjectModuleSerializer
    queryset = ProjectModule.objects.all()

    def get_queryset(self):
        return ProjectModule.objects.filter(meta_project_id=self.kwargs['pk'])
